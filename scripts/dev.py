"""Run the TapBot API and Vite development server together."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BACKEND_IMPORTS = (
    "fastapi",
    "numpy",
    "cv2",
    "serial",
    "ultralytics",
    "uvicorn",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot", choices=("mock", "grbl"), default="mock")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--camera-source", default="mock:reservation-flow")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    return parser.parse_args()


def npm_command() -> str:
    executable = "npm.cmd" if os.name == "nt" else "npm"
    resolved = shutil.which(executable)
    if resolved is None:
        raise RuntimeError("npm을 찾을 수 없습니다. Node.js를 먼저 설치해 주세요.")
    return resolved


def bootstrap(npm: str) -> None:
    missing_imports = [
        name for name in BACKEND_IMPORTS if importlib.util.find_spec(name) is None
    ]
    if missing_imports:
        print("[setup] Python 의존성을 설치합니다.", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(ROOT)],
            cwd=ROOT,
            check=True,
        )

    if not (FRONTEND / "node_modules").is_dir():
        print("[setup] Frontend 의존성을 설치합니다.", flush=True)
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)


def process_options() -> dict[str, object]:
    if os.name == "nt":
        # Keep both children in the current console group so Ctrl+C reaches
        # the launcher, Uvicorn, and Vite together on Windows.
        return {}
    return {"start_new_session": True}


def available_port(preferred: int) -> int:
    for port in range(preferred, preferred + 100):
        candidates: list[socket.socket] = []
        try:
            for family, address in (
                (socket.AF_INET, ("127.0.0.1", port)),
                (socket.AF_INET6, ("::1", port)),
            ):
                candidate = socket.socket(family, socket.SOCK_STREAM)
                candidates.append(candidate)
                if family == socket.AF_INET6:
                    candidate.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                candidate.bind(address)
            return port
        except OSError:
            continue
        finally:
            for candidate in candidates:
                candidate.close()
    raise RuntimeError(f"{preferred}번부터 사용 가능한 포트를 찾지 못했습니다.")


def stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)


def main() -> int:
    args = parse_args()

    try:
        npm = npm_command()
        bootstrap(npm)
        backend_port = available_port(args.backend_port)
        if backend_port != args.backend_port:
            raise RuntimeError(
                f"Backend port {args.backend_port} is already in use. "
                "Stop the existing TapBot server before starting another one; "
                "multiple processes cannot safely share a webcam."
            )
        frontend_port = available_port(args.frontend_port)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"[dev] 준비 실패: {error}", file=sys.stderr)
        return 1

    backend_command = [
        sys.executable,
        "-m",
        "tapbot.ui.app",
        "--robot",
        args.robot,
        "--camera-source",
        args.camera_source,
        "--port",
        str(backend_port),
    ]
    if args.dry_run:
        backend_command.append("--dry-run")

    frontend_url = f"http://localhost:{frontend_port}"
    backend_url = f"http://localhost:{backend_port}"
    print(f"[dev] Dashboard: {frontend_url}/debug", flush=True)
    print(f"[dev] Backend API: {backend_url}/docs", flush=True)
    print("[dev] 종료하려면 Ctrl+C를 누르세요.\n", flush=True)

    options = process_options()
    backend = subprocess.Popen(backend_command, cwd=ROOT, **options)
    frontend_environment = os.environ.copy()
    frontend_environment["VITE_API_BASE_URL"] = f"{backend_url}/api"
    frontend = subprocess.Popen(
        [
            npm,
            "run",
            "dev",
            "--",
            "--port",
            str(frontend_port),
            "--strictPort",
        ],
        cwd=FRONTEND,
        env=frontend_environment,
        **options,
    )

    try:
        while True:
            backend_code = backend.poll()
            frontend_code = frontend.poll()
            if backend_code is not None:
                print(f"[dev] Backend가 종료되었습니다 ({backend_code}).")
                return backend_code
            if frontend_code is not None:
                print(f"[dev] Frontend가 종료되었습니다 ({frontend_code}).")
                return frontend_code
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n[dev] 서버를 종료합니다.")
        return 0
    finally:
        stop_process_tree(frontend)
        stop_process_tree(backend)


if __name__ == "__main__":
    raise SystemExit(main())
