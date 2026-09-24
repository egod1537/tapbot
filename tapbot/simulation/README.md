# End-to-end simulation

The simulation runner executes the complete mock pipeline without a camera or
GRBL device:

`MockScreenGraph → MockGraphVision → MockModelClient → DecisionEngine →
ActionExecutor → MockRobotController → SimulationBridge → MockScreenGraph`

Run the built-in reservation scenario:

```powershell
npm run simulate
```

Equivalent installed CLI command:

```powershell
tapbot-sim --camera mock:reservation-flow --robot mock `
  --target-state verify-photo --max-steps 5 --trace simulation-trace.json
```

Use `--mode step` to execute one iteration. Auto mode is the default. To verify
that a saved trace remains reproducible:

```powershell
tapbot-sim --replay simulation-trace.json --trace replay-trace.json
```

Python tests can construct `SimulationRunner.for_scenario(...)`, call `step()`
or `run_auto()`, and inspect every frame, detection, decision, action, tap,
transition, and terminal failure in `runner.trace`.
