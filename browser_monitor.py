#!/usr/bin/env python3
"""
Browser Monitor for Code Extract
Monitors browser tabs and stops server when all tabs close.
"""

import os
import sys
import time
import signal
import subprocess
import threading

try:
    import psutil
except ImportError:
    print("Installing psutil...")
    subprocess.run([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

DEFAULT_PORT = 8420
BROWSER_NAMES = ("safari", "chrome", "firefox", "brave", "edge", "arc")


class BrowserMonitor:
    """Monitors browser connections to the server and shuts down when all close."""

    def __init__(self, server_pid: int, port: int = DEFAULT_PORT):
        self.server_pid = server_pid
        self.port = port
        self.browser_pids: set[int] = set()
        self.monitoring = False
        self.check_interval = 5  # seconds

    def start_monitoring(self):
        self.monitoring = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
        print(f"Started browser monitoring (server PID: {self.server_pid})")

    def stop_monitoring(self):
        self.monitoring = False

    def _monitor_loop(self):
        while self.monitoring:
            self._check_browsers()
            time.sleep(self.check_interval)

    def _check_browsers(self):
        current = self._find_browsers_with_connection()

        # If we previously saw browsers but now none remain, stop the server
        if not current and self.browser_pids:
            print("All browser tabs closed - stopping server")
            self._stop_server()
            self.browser_pids.clear()
            return

        self.browser_pids = current

    def _find_browsers_with_connection(self) -> set[int]:
        """Find browser PIDs that have a TCP connection to our port."""
        found: set[int] = set()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info["name"].lower()
                if not any(b in name for b in BROWSER_NAMES):
                    continue
                for conn in proc.connections():
                    if hasattr(conn, "raddr") and conn.raddr and conn.raddr.port == self.port:
                        found.add(proc.info["pid"])
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return found

    def _stop_server(self):
        try:
            os.kill(self.server_pid, signal.SIGTERM)
            print(f"Stopped server (PID: {self.server_pid})")
        except ProcessLookupError:
            print("Server process already terminated")
        except Exception as e:
            print(f"Error stopping server: {e}")


def start_server_with_monitor(project_path: str | None = None, port: int = DEFAULT_PORT):
    """Start the code-extract server with browser lifecycle monitoring."""
    from pathlib import Path

    project_dir = Path(__file__).parent

    # Build command
    cli_path = project_dir / "code_extract" / "cli.py"
    if cli_path.exists():
        cmd = [sys.executable, str(cli_path), "serve", "--port", str(port), "--no-open"]
    else:
        cmd = ["code-extract", "serve", "--port", str(port), "--no-open"]

    print(f"Starting code-extract server on port {port}...")
    server = subprocess.Popen(
        cmd,
        cwd=str(project_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    print(f"Server PID: {server.pid}")

    # Open browser
    import webbrowser
    time.sleep(2)
    webbrowser.open(f"http://localhost:{port}")

    # Start monitor
    monitor = BrowserMonitor(server.pid, port)
    monitor.start_monitoring()

    try:
        server.wait()
        monitor.stop_monitoring()
        print("Server stopped")
    except KeyboardInterrupt:
        print("\nInterrupted - stopping server...")
        server.terminate()
        monitor.stop_monitoring()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Browser Monitor for Code Extract")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument("project", nargs="?", help="Project path")

    args = parser.parse_args()
    start_server_with_monitor(args.project, args.port)
