"""Model client interface and deterministic mock implementation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import logging
from time import perf_counter
from typing import Protocol, TypeAlias

import numpy as np
from numpy.typing import NDArray

from tapbot.model.decision import Decision, DecisionParser


logger = logging.getLogger(__name__)
ModelContext: TypeAlias = Mapping[str, object]
RawDecision: TypeAlias = str | bytes | dict[str, object] | Decision


class ModelClient(Protocol):
    """Local-model interface consumed by the decision engine."""

    def analyze(
        self,
        image: NDArray[np.uint8],
        context: ModelContext,
    ) -> Decision: ...


class MockModelClient:
    """Return configured structured output without network or model hardware."""

    def __init__(
        self,
        response: RawDecision
        | Callable[[NDArray[np.uint8], ModelContext], RawDecision],
        *,
        parser: DecisionParser | None = None,
        provider: str = "mock",
        model_name: str = "deterministic-structured-decision",
    ) -> None:
        self._response = response
        self._parser = parser or DecisionParser()
        self.provider = provider
        self.model_name = model_name
        self.connected = True
        self.last_raw_response: RawDecision | None = None
        self.calls: list[tuple[NDArray[np.uint8], dict[str, object]]] = []

    def analyze(
        self,
        image: NDArray[np.uint8],
        context: ModelContext,
    ) -> Decision:
        self.calls.append((image.copy(), dict(context)))
        raw = self._response(image, context) if callable(self._response) else self._response
        self.last_raw_response = raw
        logger.info("Model response: %s", self._log_value(raw))
        decision = self._parser.parse(raw)
        logger.info("Decision parser result: %s", decision.to_dict())
        return decision

    @staticmethod
    def _log_value(value: RawDecision) -> str:
        if isinstance(value, Decision):
            value = value.to_dict()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")[:2000]
        if isinstance(value, str):
            return value[:2000]
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:2000]


class TracingModelClient:
    """Capture debug metadata around a ModelClient without changing its contract."""

    def __init__(self, client: ModelClient) -> None:
        self.client = client
        self.provider = str(getattr(client, "provider", type(client).__name__))
        self.model_name = str(getattr(client, "model_name", type(client).__name__))
        self.last_latency_ms: float | None = None
        self.last_raw_response: RawDecision | None = None

    @property
    def connected(self) -> bool:
        return bool(getattr(self.client, "connected", True))

    def analyze(
        self,
        image: NDArray[np.uint8],
        context: ModelContext,
    ) -> Decision:
        started_at = perf_counter()
        try:
            decision = self.client.analyze(image, context)
            self.last_raw_response = getattr(
                self.client, "last_raw_response", decision
            )
            return decision
        except Exception:
            self.last_raw_response = getattr(
                self.client, "last_raw_response", None
            )
            raise
        finally:
            self.last_latency_ms = (perf_counter() - started_at) * 1000
