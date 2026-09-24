import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tapbot.camera.manager import CameraManager
from tapbot.camera.scenario_registry import (
    MockScenarioRegistry,
    MockScenarioRegistryError,
)


def write_fixture_registry(root: Path, scenario_id: str = "checkout-flow") -> Path:
    scenario = root / scenario_id
    scenario.mkdir(parents=True)
    image = np.full((6, 8, 3), 90, dtype=np.uint8)
    assert cv2.imwrite(str(scenario / "start.png"), image)
    (scenario / "README.md").write_text(
        "# Checkout flow\n\nSynthetic fixture without personal data.\n",
        encoding="utf-8",
    )
    (scenario / "graph.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": scenario_id,
                "name": "Checkout flow",
                "description": "Exercises a synthetic checkout screen.",
                "screen_width": 8,
                "screen_height": 6,
                "initial_state": "start",
                "states": {
                    "start": {
                        "image": "start.png",
                        "hotspots": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "registry.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [
                    {
                        "id": scenario_id,
                        "graph": f"{scenario_id}/graph.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return scenario


def test_default_fixture_registry_validates_every_scenario() -> None:
    registry = MockScenarioRegistry.default()

    scenarios = registry.validate_all()

    assert [scenario.id for scenario in scenarios] == ["reservation-flow"]
    assert scenarios[0].name == "Reservation verification flow"
    assert scenarios[0].screen_width == 1280
    assert scenarios[0].screen_height == 720
    assert scenarios[0].graph_path.name == "graph.json"


def test_registry_entry_automatically_becomes_selectable_mock_source(
    tmp_path: Path,
) -> None:
    write_fixture_registry(tmp_path)
    registry = MockScenarioRegistry(tmp_path)

    manager = CameraManager.with_defaults(
        "mock:checkout-flow",
        discovery_max_index=None,
        scenario_registry=registry,
    )

    sources = manager.list_sources()
    assert [(source.id, source.name) for source in sources] == [
        ("mock:checkout-flow", "Checkout flow")
    ]
    assert manager.get_metadata()["width"] == 8
    assert manager.get_metadata()["height"] == 6
    assert manager.read_frame().shape == (6, 8, 3)


def test_registry_validation_requires_scenario_readme(tmp_path: Path) -> None:
    scenario = write_fixture_registry(tmp_path)
    (scenario / "README.md").unlink()
    registry = MockScenarioRegistry(tmp_path)

    with pytest.raises(MockScenarioRegistryError, match="README.md"):
        registry.validate_all()


def test_registry_validation_rejects_unregistered_fixture_graph(
    tmp_path: Path,
) -> None:
    write_fixture_registry(tmp_path)
    orphan = tmp_path / "orphan-flow"
    orphan.mkdir()
    (orphan / "graph.json").write_text("{}", encoding="utf-8")
    registry = MockScenarioRegistry(tmp_path)

    with pytest.raises(MockScenarioRegistryError, match="not registered"):
        registry.validate_all()
