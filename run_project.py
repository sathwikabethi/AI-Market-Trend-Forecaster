import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests


def wait_for_http(url: str, timeout: int = 20):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code < 500:
                return response
            last_error = RuntimeError(f"HTTP {response.status_code}")
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}. Last error: {last_error}")


def terminate_process(proc: subprocess.Popen | None):
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except Exception:
        proc.kill()


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _pick_available_port(host: str, preferred_port: int, max_scan: int = 20) -> int:
    for offset in range(max_scan):
        candidate = preferred_port + offset
        if _is_port_available(host, candidate):
            return candidate
    return preferred_port


def main():
    root = Path(__file__).parent
    frontend_dir = root / "frontend"

    backend_host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    requested_backend_port = int(os.environ.get("BACKEND_PORT", "8002"))
    backend_port = _pick_available_port(backend_host, requested_backend_port)
    frontend_host = os.environ.get("FRONTEND_HOST", "127.0.0.1")
    requested_frontend_port = int(os.environ.get("FRONTEND_PORT", "5173"))
    frontend_port = _pick_available_port(frontend_host, requested_frontend_port)

    backend_url = f"http://{backend_host}:{backend_port}"
    frontend_url = f"http://{frontend_host}:{frontend_port}"
    backend_readiness_url = f"{backend_url}/health/readiness"

    if backend_port != requested_backend_port:
        print(f"Requested backend port {requested_backend_port} unavailable, using {backend_port}.")
    if frontend_port != requested_frontend_port:
        print(f"Requested frontend port {requested_frontend_port} unavailable, using {frontend_port}.")

    print(f"Starting FastAPI backend on {backend_url}")
    print(f"Starting React frontend on {frontend_url}")

    uvicorn_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.main:app",
        "--host",
        backend_host,
        "--port",
        str(backend_port),
    ]

    try:
        backend_proc = subprocess.Popen(uvicorn_cmd)
    except FileNotFoundError:
        print("Unable to start uvicorn. Install requirements first:")
        print("pip install -r requirements.txt")
        return

    try:
        wait_for_http(backend_readiness_url, timeout=25)
        print(f"Backend is ready at {backend_readiness_url}")
    except Exception as err:
        print(f"Backend failed to start: {err}")
        terminate_process(backend_proc)
        return

    npm_executable = "npm.cmd" if os.name == "nt" else "npm"
    frontend_env = os.environ.copy()
    frontend_env["VITE_BACKEND_URL"] = backend_url

    frontend_cmd = [
        npm_executable,
        "run",
        "dev",
        "--",
        f"--host={frontend_host}",
        f"--port={frontend_port}",
    ]

    try:
        frontend_proc = subprocess.Popen(frontend_cmd, cwd=frontend_dir, env=frontend_env)
    except FileNotFoundError:
        print("Unable to start npm. Install Node.js and run `npm install` in frontend.")
        terminate_process(backend_proc)
        return

    try:
        wait_for_http(frontend_url, timeout=30)
        print(f"Frontend is ready at {frontend_url}")
        print(f"Backend docs available at {backend_url}/docs")
        print("Press Ctrl+C to stop both services.")
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        terminate_process(frontend_proc)
        terminate_process(backend_proc)


if __name__ == "__main__":
    main()
