"""Composition helpers for concrete PC macro runtimes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from tapbot.android.client import AndroidAgentClient
from tapbot.device.android import AndroidRemoteController
from tapbot.macro.engine import MacroEngine
from tapbot.macro.state import MacroStateMachine, StateClassifier
from tapbot.model.resolver import TargetResolver
from tapbot.screen.android import AndroidRemoteScreenSource
from tapbot.ui_resolution import (
    AndroidAccessibilityUiTreeProvider,
    HybridTargetResolver,
)
from tapbot.vision.canonical import CanonicalVisionPipeline
from tapbot.vision.detector import Detector


def build_android_macro_engine(
    base_url: str,
    token: str,
    *,
    detectors: Sequence[Detector],
    classifier: StateClassifier,
    state_machine: MacroStateMachine,
    target_resolver: TargetResolver | None = None,
    artifact_dir: str | Path | None = None,
    timeout: float = 5.0,
) -> MacroEngine:
    """Wire one no-retry Android client to canonical vision and control."""

    client = AndroidAgentClient(base_url, token, timeout=timeout)
    resolved_target_resolver = target_resolver or TargetResolver()
    return MacroEngine(
        AndroidRemoteScreenSource(client),
        CanonicalVisionPipeline(detectors),
        classifier,
        state_machine,
        resolved_target_resolver,
        AndroidRemoteController(client),
        artifact_dir=artifact_dir,
        ui_tree_provider=AndroidAccessibilityUiTreeProvider(client),
        hybrid_target_resolver=HybridTargetResolver(resolved_target_resolver),
    )
