# PC ScreenSource / Macro Engine

The default PC macro path consumes an already-canonical `ScreenSource`:

```text
AndroidRemoteScreenSource -> CanonicalVisionPipeline -> StateClassifier
                          -> MacroStateMachine -> TargetResolver
                          -> AndroidRemoteController
```

No phone detector, screen-corner detector, or homography is constructed on
this path. The physical webcam `CameraSource` pipeline remains available only
as an explicit legacy path.

```python
from tapbot.macro import (
    DetectionStateClassifier,
    DetectionStateRule,
    MacroStateMachine,
    TapTargetAction,
    build_android_macro_engine,
)

classifier = DetectionStateClassifier([
    DetectionStateRule("reservation", frozenset({"verify_photo_button"})),
])
machine = MacroStateMachine({
    "reservation": TapTargetAction("verify_photo_button"),
})

engine = build_android_macro_engine(
    "http://192.168.0.20:8765",
    "agent-token",
    detectors=[ui_detector],
    classifier=classifier,
    state_machine=machine,
    artifact_dir="traces/current/frames",
)

step = engine.step(execute=True)
engine.finish("traces/current/trace.json")
```

`TapTargetAction` contains a semantic label, never an HTTP command or model
generated coordinate. `TargetResolver` selects a trusted detection/ROI, the
geometry layer maps screenshot pixels to device pixels, and only the selected
`DeviceController` can execute input.

`MockGraphScreenSource` + `MockGraphController` and `RobotTapController` use
the same macro engine boundary. Saved trace JSON records frame IDs, screenshot
artifacts, detections, state, decision, resolved target, and controller result.
