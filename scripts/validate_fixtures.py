"""Validate every mock scenario registered in fixtures/registry.json."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tapbot.camera.scenario_registry import MockScenarioRegistry


def main() -> int:
    registry = MockScenarioRegistry.default()
    scenarios = registry.validate_all()
    for scenario in scenarios:
        print(
            f"[fixture] {scenario.id}: {scenario.name} "
            f"({scenario.screen_width}x{scenario.screen_height})"
        )
    print(f"[fixture] validated {len(scenarios)} scenario(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
