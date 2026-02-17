#!/usr/bin/env python3
"""
macOS Menubar App Wrapper for Code Extract
Run: python3 macos_menubar_app.py
"""

import os
import sys
import json
import time
import signal
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

# PyObjC imports for macOS menubar
try:
    import rumps
    from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
    HAS_RUMPS = True
except ImportError:
    print("PyObjC/rumps not installed. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rumps", "pyobjc-framework-Cocoa"])
    import rumps
    from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
    HAS_RUMPS = True

APP_NAME = "Code Extract"
APP_VERSION = "0.3.0"
DEFAULT_PORT = 8420
CONFIG_FILE = Path(__file__).parent / "code_extract_macos_config.json"
PROJECT_DIR = Path(__file__).parent


def load_config() -> dict:
    """Load config from JSON file, or return defaults."""
    defaults = {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "server_port": DEFAULT_PORT,
        "auto_start": True,
        "auto_open_browser": True,
        "monitor_browser": True,
        "ui": {
            "notifications": True,
        },
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                user_cfg = json.load(f)
            defaults.update(user_cfg)
        except Exception:
            pass
    return defaults


class CodeExtractMenubarApp:
    """macOS menubar app that manages the code-extract server lifecycle."""

    def __init__(self, project_path=None, port=DEFAULT_PORT):
        self.config = load_config()
        self.app = rumps.App(APP_NAME, quit_button=None)
        self.server_process = None
        self.server_port = port
        self.project_path = project_path
        self.is_running = False

        self.setup_menu()

        # Auto-start server on launch
        if self.config.get("auto_start", True):
            threading.Timer(1.0, self.start_server).start()

    def setup_menu(self):
        """Configure the menubar menu."""
        items = [
            rumps.MenuItem("Start Server", callback=self.start_server),
            rumps.MenuItem("Stop Server", callback=self.stop_server),
            rumps.MenuItem("Open in Browser", callback=self.open_browser),
            None,  # separator
            rumps.MenuItem(f"Port: {self.server_port}", callback=None),
            rumps.MenuItem(f"v{APP_VERSION}", callback=None),
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        self.app.menu = items
        self.update_status()

    def update_status(self):
        """Update menubar icon based on running state."""
        if self.is_running:
            self.app.title = "CE"
            self.app.menu["Start Server"].set_callback(None)
            self.app.menu["Stop Server"].set_callback(self.stop_server)
            self.app.menu["Open in Browser"].set_callback(self.open_browser)
        else:
            self.app.title = "ce"
            self.app.menu["Start Server"].set_callback(self.start_server)
            self.app.menu["Stop Server"].set_callback(None)
            self.app.menu["Open in Browser"].set_callback(None)

    def _build_server_cmd(self) -> list[str]:
        """Build the command to start the code-extract server."""
        # Use the CLI module directly — works whether or not pip-installed
        cli_path = PROJECT_DIR / "code_extract" / "cli.py"
        if cli_path.exists():
            return [
                sys.executable, str(cli_path),
                "serve",
                "--port", str(self.server_port),
                "--no-open",
            ]
        # Fallback: installed CLI
        return [
            "code-extract", "serve",
            "--port", str(self.server_port),
            "--no-open",
        ]

    def start_server(self, _=None):
        """Start the code-extract server."""
        if self.is_running:
            rumps.notification(APP_NAME, "Server already running", "")
            return

        try:
            cmd = self._build_server_cmd()
            self.server_process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid,
            )

            if self._wait_for_server():
                self.is_running = True
                self.update_status()

                if self.config.get("auto_open_browser", True):
                    threading.Timer(0.5, self.open_browser).start()

                if self.config.get("ui", {}).get("notifications", True):
                    rumps.notification(
                        APP_NAME,
                        "Server started",
                        f"http://localhost:{self.server_port}",
                    )

                # Monitor for crashes
                threading.Thread(target=self._monitor_server, daemon=True).start()
            else:
                self.stop_server()
                rumps.notification(APP_NAME, "Failed to start server", "Check console for errors")

        except Exception as e:
            rumps.notification(APP_NAME, "Startup error", str(e))

    def _wait_for_server(self, timeout=30) -> bool:
        """Wait for the server to become responsive."""
        import urllib.request
        import urllib.error

        start = time.time()
        url = f"http://localhost:{self.server_port}/api/scans"
        while time.time() - start < timeout:
            try:
                req = urllib.request.urlopen(url, timeout=1)
                if req.status in (200, 404):
                    return True
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        return False

    def _monitor_server(self):
        """Watch for server process exit."""
        if self.server_process:
            self.server_process.wait()
            self.is_running = False
            self.update_status()
            if self.config.get("ui", {}).get("notifications", True):
                rumps.notification(APP_NAME, "Server stopped", "Process terminated")

    def stop_server(self, _=None):
        """Stop the server."""
        if not self.is_running and not self.server_process:
            return

        try:
            if self.server_process:
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGTERM)
                self.server_process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if self.server_process:
                try:
                    os.killpg(os.getpgid(self.server_process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        except Exception as e:
            rumps.notification(APP_NAME, "Error stopping server", str(e))

        self.is_running = False
        self.server_process = None
        self.update_status()

    def open_browser(self, _=None):
        """Open the web UI in the default browser."""
        if not self.is_running:
            rumps.notification(APP_NAME, "Server not running", "Start server first")
            return
        webbrowser.open(f"http://localhost:{self.server_port}")

    def quit_app(self, _=None):
        """Clean shutdown."""
        self.stop_server()
        rumps.quit_application()

    def run(self):
        """Start the menubar app."""
        # Hide Python from dock — run as menubar-only (Accessory = no dock, but allows menubar)
        from AppKit import NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.app.run()


def create_plist_file():
    """Create LaunchAgent plist for auto-start on login."""
    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.code-extract.launcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{os.path.abspath(__file__)}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/code-extract.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/code-extract_error.log</string>
</dict>
</plist>
'''
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.code-extract.launcher.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)
    print(f"LaunchAgent created at: {plist_path}")
    print(f"To enable: launchctl load {plist_path}")
    return plist_path


def create_app_bundle():
    """Create a .app bundle for macOS."""
    app_dir = Path.home() / "Applications" / f"{APP_NAME}.app"
    contents_dir = app_dir / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    info_plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>CodeExtract</string>
    <key>CFBundleIdentifier</key>
    <string>com.code-extract.app</string>
    <key>CFBundleName</key>
    <string>{APP_NAME}</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>{APP_VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
'''
    (contents_dir / "Info.plist").write_text(info_plist)

    executable = macos_dir / "CodeExtract"
    script_content = f'''#!/bin/bash
cd "{PROJECT_DIR}"
"{sys.executable}" "{os.path.abspath(__file__)}" "$@"
'''
    executable.write_text(script_content)
    executable.chmod(0o755)

    # Copy icon if exists
    icon_src = PROJECT_DIR / "code_extract.icns"
    if icon_src.exists():
        shutil.copy(icon_src, resources_dir / "AppIcon.icns")

    print(f"App bundle created at: {app_dir}")
    return app_dir


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Code Extract macOS Menubar App")
    parser.add_argument("project", nargs="?", help="Project path to scan on startup")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument("--create-launchagent", action="store_true", help="Create LaunchAgent plist")
    parser.add_argument("--create-app", action="store_true", help="Create .app bundle")
    parser.add_argument("--install-deps", action="store_true", help="Install dependencies")

    args = parser.parse_args()

    if args.install_deps:
        print("Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "rumps", "pyobjc-framework-Cocoa", "psutil"])
        print("Dependencies installed")
        return

    if args.create_launchagent:
        create_plist_file()
        return

    if args.create_app:
        create_app_bundle()
        return

    print(f"Starting {APP_NAME} macOS Menubar App...")
    print(f"  Port: {args.port}")
    print("  Click the menubar icon to control the server")

    app = CodeExtractMenubarApp(project_path=args.project, port=args.port)
    app.run()


if __name__ == "__main__":
    main()
