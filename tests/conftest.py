from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def disable_live_vision_by_default(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep unrelated API tests from starting an inference loop."""

    monkeypatch.setenv("TAPBOT_VISION_LIVE_ENABLED", "false")
    yield
