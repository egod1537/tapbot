"""Command-line entry point for hardware-free TapBot scenario simulation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from tapbot.camera import CameraError, MockGraphError
from tapbot.simulation.runner import (
    SimulationOutcome,
    SimulationRunner,
    SimulationTrace,
    SimulationTraceError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or replay a complete hardware-free TapBot pipeline"
    )
    parser.add_argument(
        "--camera",
        default="mock:reservation-flow",
        help="mock camera source ID (default: mock:reservation-flow)",
    )
    parser.add_argument(
        "--robot",
        choices=("mock",),
        default="mock",
        help="simulation only permits the mock robot",
    )
    parser.add_argument(
        "--target-state",
        default="verify-photo",
        help="success state (default: verify-photo)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "step"),
        default="auto",
        help="auto runs to completion; step executes one iteration",
    )
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--same-state-limit", type=int, default=2)
    parser.add_argument("--confidence-threshold", type=float, default=0.8)
    parser.add_argument(
        "--trace",
        type=Path,
        help=(
            "JSON trace output path (defaults to simulation-trace.json or "
            "replay-trace.json)"
        ),
    )
    parser.add_argument(
        "--replay",
        type=Path,
        help="re-run and compare an existing trace instead of starting a new run",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.replay is not None:
        trace_path = args.trace or Path("replay-trace.json")
        try:
            expected = SimulationTrace.load(args.replay)
            replay = SimulationRunner.replay(expected)
        except (
            CameraError,
            MockGraphError,
            SimulationTraceError,
            ValueError,
        ) as error:
            parser.error(str(error))
        replay.actual.save(trace_path)
        if replay.matched:
            print(
                f"[simulation] replay matched: {len(replay.actual.steps)} step(s)"
            )
            print(f"[simulation] trace: {trace_path.resolve()}")
            return 0
        print(
            f"[simulation] replay mismatch at step "
            f"{replay.mismatch_step or 'outcome'}: {replay.detail}"
        )
        print(f"[simulation] actual trace: {trace_path.resolve()}")
        return 1

    camera = str(args.camera)
    if not camera.startswith("mock:") or camera == "mock:":
        parser.error("--camera must be a mock source such as mock:reservation-flow")
    scenario_id = camera.removeprefix("mock:")
    trace_path = args.trace or Path("simulation-trace.json")
    try:
        with SimulationRunner.for_scenario(
            scenario_id,
            args.target_state,
            max_steps=args.max_steps,
            same_state_limit=args.same_state_limit,
            confidence_threshold=args.confidence_threshold,
        ) as runner:
            if args.mode == "step":
                runner.step()
                trace = runner.trace
            else:
                trace = runner.run_auto()
    except (CameraError, MockGraphError, ValueError) as error:
        parser.error(str(error))

    trace.save(trace_path)
    final_state = trace.steps[-1].next_state if trace.steps else args.target_state
    print(
        f"[simulation] {trace.outcome.value}: {scenario_id} -> {final_state} "
        f"({len(trace.steps)} step(s))"
    )
    if trace.failure_reason is not None:
        print(
            f"[simulation] failure: {trace.failure_reason.value}: "
            f"{trace.failure_detail}"
        )
    print(f"[simulation] trace: {trace_path.resolve()}")
    return 1 if trace.outcome is SimulationOutcome.FAILED else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
