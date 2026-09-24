"""Safe conversion of structured model decisions into TapBot actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import logging
import math
from numbers import Real

import numpy as np
from numpy.typing import NDArray

from tapbot.core.actions import Action, TapAction, WaitAction
from tapbot.core.executor import ActionExecutor
from tapbot.model.client import ModelClient
from tapbot.model.decision import Decision, DecisionAction, DecisionParser
from tapbot.model.resolver import ResolvedTarget, TargetResolver
from tapbot.vision.calibration import Calibration, CalibrationError
from tapbot.vision.detector import Detection


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    confidence_threshold: float = 0.8
    wait_duration_ms: int = 1000

    def __post_init__(self) -> None:
        if (
            isinstance(self.confidence_threshold, bool)
            or not isinstance(self.confidence_threshold, Real)
            or not math.isfinite(self.confidence_threshold)
            or not 0 <= self.confidence_threshold <= 1
        ):
            raise ValueError("confidence_threshold must be between 0 and 1")
        if (
            isinstance(self.wait_duration_ms, bool)
            or not isinstance(self.wait_duration_ms, int)
            or self.wait_duration_ms < 0
        ):
            raise ValueError("wait_duration_ms must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class DecisionResult:
    image_id: str
    decision: Decision | None
    action: Action | None
    resolved_target: ResolvedTarget | None
    execution_allowed: bool
    executed: bool
    status: str
    error: str | None = None


class DecisionEngine:
    """Analyze a rectified screen and safely resolve a proposed action."""

    def __init__(
        self,
        model_client: ModelClient,
        target_resolver: TargetResolver,
        calibration: Calibration,
        *,
        policy: DecisionPolicy | None = None,
    ) -> None:
        self.model_client = model_client
        self.target_resolver = target_resolver
        self.calibration = calibration
        self.policy = policy or DecisionPolicy()
        self._decision_parser = DecisionParser()

    def decide(
        self,
        image: NDArray[np.uint8],
        context: Mapping[str, object] | None = None,
        detections: Sequence[Detection] = (),
    ) -> DecisionResult:
        self._validate_image(image)
        image_id = self.image_identifier(image)
        height, width = image.shape[:2]
        logger.info("Decision input image: %s (%dx%d)", image_id, width, height)
        expected_size = (
            int(round(self.calibration.phone_width)),
            int(round(self.calibration.phone_height)),
        )
        if (width, height) != expected_size:
            error = (
                f"Rectified image size {width}x{height} does not match calibration "
                f"{expected_size[0]}x{expected_size[1]}"
            )
            logger.error("Decision blocked for %s: %s; executed=false", image_id, error)
            return DecisionResult(
                image_id=image_id,
                decision=None,
                action=None,
                resolved_target=None,
                execution_allowed=False,
                executed=False,
                status="screen_size_mismatch",
                error=error,
            )
        model_context = dict(context or {})
        model_context["screen_size"] = {"width": width, "height": height}
        model_context["detections"] = [item.to_dict() for item in detections]

        try:
            model_decision = self.model_client.analyze(image, model_context)
            decision = self._decision_parser.parse(model_decision)
        except Exception as error:
            logger.error(
                "Decision blocked for %s: parser/model error: %s; executed=false",
                image_id,
                error,
            )
            return DecisionResult(
                image_id=image_id,
                decision=None,
                action=None,
                resolved_target=None,
                execution_allowed=False,
                executed=False,
                status="invalid_model_output",
                error=str(error),
            )

        logger.info("Structured decision for %s: %s", image_id, decision.to_dict())
        if decision.confidence < self.policy.confidence_threshold:
            return self._blocked(
                image_id,
                decision,
                "confidence_below_threshold",
            )
        if decision.action is DecisionAction.NOOP:
            return self._blocked(image_id, decision, "noop")
        if decision.action is DecisionAction.REQUEST_HUMAN:
            return self._blocked(image_id, decision, "human_required")
        if decision.action is DecisionAction.WAIT:
            action = WaitAction(self.policy.wait_duration_ms)
            return self._allowed(image_id, decision, action, None)

        assert decision.action is DecisionAction.TAP_TARGET
        assert decision.target is not None
        resolved = self.target_resolver.resolve(
            decision.target,
            detections,
            screen_width=width,
            screen_height=height,
        )
        if resolved is None:
            return self._blocked(image_id, decision, "target_not_found")
        try:
            robot = self.calibration.screen_to_robot(
                resolved.center.x,
                resolved.center.y,
            )
        except CalibrationError as error:
            logger.error(
                "Decision blocked for %s: target transform failed: %s; executed=false",
                image_id,
                error,
            )
            return DecisionResult(
                image_id=image_id,
                decision=decision,
                action=None,
                resolved_target=resolved,
                execution_allowed=False,
                executed=False,
                status="target_transform_failed",
                error=str(error),
            )
        return self._allowed(
            image_id,
            decision,
            TapAction(robot.x, robot.y),
            resolved,
        )

    @staticmethod
    def image_identifier(image: NDArray[np.uint8]) -> str:
        digest = hashlib.sha256()
        digest.update(str(image.shape).encode("ascii"))
        digest.update(str(image.dtype).encode("ascii"))
        digest.update(np.ascontiguousarray(image).tobytes())
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _validate_image(image: object) -> None:
        if (
            not isinstance(image, np.ndarray)
            or image.dtype != np.uint8
            or image.ndim != 3
            or image.shape[2] != 3
            or image.size == 0
        ):
            raise ValueError("Decision input must be a non-empty uint8 BGR image")

    @staticmethod
    def _blocked(
        image_id: str,
        decision: Decision,
        status: str,
    ) -> DecisionResult:
        logger.info("Decision result for %s: %s; executed=false", image_id, status)
        return DecisionResult(
            image_id=image_id,
            decision=decision,
            action=None,
            resolved_target=None,
            execution_allowed=False,
            executed=False,
            status=status,
        )

    @staticmethod
    def _allowed(
        image_id: str,
        decision: Decision,
        action: Action,
        resolved_target: ResolvedTarget | None,
    ) -> DecisionResult:
        logger.info(
            "Decision result for %s: action=%s; execution_allowed=true; executed=false",
            image_id,
            action,
        )
        return DecisionResult(
            image_id=image_id,
            decision=decision,
            action=action,
            resolved_target=resolved_target,
            execution_allowed=True,
            executed=False,
            status="action_created",
        )


class DecisionCoordinator:
    """Optional orchestration boundary that sends a resolved Action to Executor."""

    def __init__(self, engine: DecisionEngine, executor: ActionExecutor) -> None:
        self.engine = engine
        self.executor = executor

    def run(
        self,
        image: NDArray[np.uint8],
        context: Mapping[str, object] | None = None,
        detections: Sequence[Detection] = (),
        *,
        execute: bool = False,
    ) -> DecisionResult:
        result = self.engine.decide(image, context, detections)
        if not execute or result.action is None:
            logger.info(
                "Decision execution for %s: executed=false",
                result.image_id,
            )
            return result
        try:
            self.executor.execute(result.action)
        except Exception as error:
            logger.error(
                "Decision execution for %s failed: %s; executed=false",
                result.image_id,
                error,
            )
            return replace(
                result,
                execution_allowed=False,
                status="execution_failed",
                error=str(error),
            )
        logger.info("Decision execution for %s: executed=true", result.image_id)
        return replace(result, executed=True, status="executed")
