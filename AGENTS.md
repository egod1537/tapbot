# Agent Guidelines

## Development server ports

- Port `8000` is reserved for the user's TapBot backend. Agents must not start
  validation or preview servers on port `8000`.
- Port `5173` is reserved for the user's frontend when available. Agents should
  avoid occupying it during validation.
- For agent-run manual verification, use dedicated ports such as backend
  `18000` and frontend `15173`:

  ```powershell
  npm run dev -- --backend-port 18000 --frontend-port 15173
  ```

- If those validation ports are occupied, choose other free non-default ports.
  Do not stop or replace a user-owned process merely to claim a preferred port.
- Stop all agent-started development servers after verification unless the user
  explicitly asks to leave them running.
