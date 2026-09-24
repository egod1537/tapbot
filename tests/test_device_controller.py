from tapbot.android.client import AndroidActionResult
from tapbot.device import AndroidRemoteController, RobotTapController
from tapbot.robot.mock import MockRobotController


class StubAndroidClient:
    def tap(self, x: float, y: float, *, duration_ms: int) -> AndroidActionResult:
        assert (x, y, duration_ms) == (10, 20, 70)
        return AndroidActionResult("request-1", "action-1", "tap", "completed")

    def swipe(self, *args: object, **kwargs: object) -> AndroidActionResult:
        return AndroidActionResult("request-2", "action-2", "swipe", "completed")

    def back(self) -> AndroidActionResult:
        return AndroidActionResult("request-3", "action-3", "back", "dispatched")

    def home(self) -> AndroidActionResult:
        return AndroidActionResult("request-4", "action-4", "home", "dispatched")


class DoubleMapper:
    def screen_to_robot(self, x: float, y: float) -> tuple[float, float]:
        return x * 2, y * 2


class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class PointMapper:
    def screen_to_robot(self, x: float, y: float) -> Point:
        return Point(x + 1, y + 2)


def test_android_controller_only_forwards_primitives() -> None:
    controller = AndroidRemoteController(StubAndroidClient())  # type: ignore[arg-type]

    result = controller.tap(10, 20)

    assert result.action_id == "action-1"
    assert result.metadata == {
        "request_id": "request-1",
        "backend": "android_remote",
    }


def test_robot_controller_is_swappable_behind_same_contract() -> None:
    robot = MockRobotController()
    controller = RobotTapController(robot, DoubleMapper())

    result = controller.tap(10, 20)

    assert robot.commands == [("tap", 20, 40)]
    assert result.metadata["backend"] == "robot_tap"


def test_robot_adapter_accepts_existing_calibration_point_shape() -> None:
    robot = MockRobotController()

    RobotTapController(robot, PointMapper()).tap(10, 20)

    assert robot.commands == [("tap", 11, 22)]
