"""Registry for portable, validated mock-screen scenario fixtures."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from tapbot.camera.mock_graph import MockGraphValidationError, MockScreenGraph


SCENARIO_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]*$")


class MockScenarioRegistryError(MockGraphValidationError):
    """Raised when the fixture registry is missing or malformed."""


class MockScenarioNotFoundError(MockScenarioRegistryError):
    """Raised when a requested scenario is not registered."""


@dataclass(frozen=True, slots=True)
class MockScenarioDescriptor:
    id: str
    name: str
    description: str
    screen_width: int
    screen_height: int
    graph_path: Path

    @property
    def directory(self) -> Path:
        return self.graph_path.parent


class MockScenarioRegistry:
    """Resolve scenario IDs to graph fixtures without code-level registration."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.registry_path = self.root / "registry.json"
        self._scenarios = self._load()

    @classmethod
    def default(cls) -> MockScenarioRegistry:
        configured = os.environ.get("TAPBOT_FIXTURES_DIR")
        if configured:
            return cls(configured)

        module_path = Path(__file__).resolve()
        candidates = (
            module_path.parents[2] / "fixtures",
            module_path.parents[1] / "fixtures",
        )
        for candidate in candidates:
            if (candidate / "registry.json").is_file():
                return cls(candidate)
        raise MockScenarioRegistryError(
            "Could not find fixtures/registry.json; set TAPBOT_FIXTURES_DIR"
        )

    def list_scenarios(self) -> tuple[MockScenarioDescriptor, ...]:
        return tuple(self._scenarios.values())

    def get(self, scenario_id: str) -> MockScenarioDescriptor:
        try:
            return self._scenarios[scenario_id]
        except KeyError as error:
            raise MockScenarioNotFoundError(
                f"Mock scenario is not registered: {scenario_id}"
            ) from error

    def validate_all(self) -> tuple[MockScenarioDescriptor, ...]:
        for scenario in self._scenarios.values():
            graph = MockScreenGraph.load(scenario.graph_path)
            if graph.metadata.id != scenario.id:
                raise MockScenarioRegistryError(
                    f"Scenario {scenario.id!r} graph id does not match registry"
                )
            readme = scenario.directory / "README.md"
            if not readme.is_file() or not readme.read_text(
                encoding="utf-8"
            ).strip():
                raise MockScenarioRegistryError(
                    f"Scenario {scenario.id!r} must include a non-empty README.md"
                )
        registered_graphs = {
            scenario.graph_path.resolve() for scenario in self._scenarios.values()
        }
        unregistered_graphs = sorted(
            graph.resolve()
            for graph in self.root.glob("*/graph.json")
            if graph.resolve() not in registered_graphs
        )
        if unregistered_graphs:
            raise MockScenarioRegistryError(
                "Fixture graph is not registered: "
                + ", ".join(str(path) for path in unregistered_graphs)
            )
        return self.list_scenarios()

    def _load(self) -> dict[str, MockScenarioDescriptor]:
        try:
            document = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise MockScenarioRegistryError(
                f"Could not read fixture registry: {self.registry_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise MockScenarioRegistryError(
                f"Fixture registry is not valid JSON: {self.registry_path}"
            ) from error

        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise MockScenarioRegistryError("Fixture registry schema_version must be 1")
        entries = document.get("scenarios")
        if not isinstance(entries, list) or not entries:
            raise MockScenarioRegistryError(
                "Fixture registry scenarios must be a non-empty array"
            )

        scenarios: dict[str, MockScenarioDescriptor] = {}
        for index, raw_entry in enumerate(entries):
            path = f"scenarios[{index}]"
            if not isinstance(raw_entry, dict):
                raise MockScenarioRegistryError(f"{path} must be an object")
            scenario_id = raw_entry.get("id")
            if (
                not isinstance(scenario_id, str)
                or SCENARIO_ID_PATTERN.fullmatch(scenario_id) is None
            ):
                raise MockScenarioRegistryError(
                    f"{path}.id must match {SCENARIO_ID_PATTERN.pattern}"
                )
            if scenario_id in scenarios:
                raise MockScenarioRegistryError(
                    f"Duplicate scenario id in registry: {scenario_id}"
                )
            graph_name = raw_entry.get("graph")
            if not isinstance(graph_name, str) or not graph_name:
                raise MockScenarioRegistryError(
                    f"{path}.graph must be a non-empty string"
                )
            graph_path = self._resolve_graph_path(graph_name, path)
            scenarios[scenario_id] = self._read_descriptor(
                scenario_id, graph_path
            )
        return scenarios

    def _resolve_graph_path(self, graph_name: str, path: str) -> Path:
        relative_path = Path(graph_name)
        if relative_path.is_absolute():
            raise MockScenarioRegistryError(f"{path}.graph must be relative")
        graph_path = (self.root / relative_path).resolve()
        try:
            graph_path.relative_to(self.root)
        except ValueError as error:
            raise MockScenarioRegistryError(
                f"{path}.graph must stay inside the fixture root"
            ) from error
        if not graph_path.is_file():
            raise MockScenarioRegistryError(
                f"Registered scenario graph does not exist: {graph_path}"
            )
        return graph_path

    @staticmethod
    def _read_descriptor(
        scenario_id: str, graph_path: Path
    ) -> MockScenarioDescriptor:
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MockScenarioRegistryError(
                f"Could not read registered scenario graph: {graph_path}"
            ) from error
        if not isinstance(graph, dict):
            raise MockScenarioRegistryError(
                f"Registered scenario graph must be an object: {graph_path}"
            )
        if graph.get("id") != scenario_id:
            raise MockScenarioRegistryError(
                f"Graph id must match registered scenario {scenario_id!r}"
            )
        name = graph.get("name")
        description = graph.get("description")
        screen_width = graph.get("screen_width")
        screen_height = graph.get("screen_height")
        if not isinstance(name, str) or not name:
            raise MockScenarioRegistryError(f"Graph name is required: {graph_path}")
        if not isinstance(description, str) or not description:
            raise MockScenarioRegistryError(
                f"Graph description is required: {graph_path}"
            )
        if (
            isinstance(screen_width, bool)
            or not isinstance(screen_width, int)
            or screen_width <= 0
            or isinstance(screen_height, bool)
            or not isinstance(screen_height, int)
            or screen_height <= 0
        ):
            raise MockScenarioRegistryError(
                f"Graph screen_width/screen_height must be positive integers: "
                f"{graph_path}"
            )
        return MockScenarioDescriptor(
            id=scenario_id,
            name=name,
            description=description,
            screen_width=screen_width,
            screen_height=screen_height,
            graph_path=graph_path,
        )
