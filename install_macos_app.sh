#!/bin/bash
# macOS App Installer for Code Extract

set -e

echo "Installing Code Extract macOS App..."

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "This script is for macOS only"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Find or create venv
VENV_DIR="$HOME/venv"
if [[ ! -d "$VENV_DIR/bin" ]]; then
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python"

# Install Python dependencies
echo "Installing Python dependencies..."
"$PIP" install -q rumps pyobjc-framework-Cocoa psutil

# Install code-extract with all extras
echo "Installing code-extract..."
"$PIP" install -q -e ".[all]"

# Create LaunchAgent for auto-start
echo "Creating LaunchAgent..."
"$PYTHON" macos_menubar_app.py --create-launchagent

# Create .app bundle
echo "Creating .app bundle..."
"$PYTHON" macos_menubar_app.py --create-app

# Create desktop shortcut
cat > ~/Desktop/CodeExtract.command << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
"$PYTHON" macos_menubar_app.py "\$@"
EOF
chmod +x ~/Desktop/CodeExtract.command

echo ""
echo "Installation complete!"
echo ""
echo "To start:"
echo "  1. Double-click ~/Desktop/CodeExtract.command"
echo "  2. Or run: $PYTHON macos_menubar_app.py"
echo "  3. The app appears in your menubar as 'CE'"
echo ""
echo "To enable auto-start on login:"
echo "  launchctl load ~/Library/LaunchAgents/com.code-extract.launcher.plist"
