# mixxx-mcp Windows installer
# Run from PowerShell as Administrator: .\install-windows.ps1

$ErrorActionPreference = "Stop"

$REPO_DIR   = Split-Path -Parent $MyInvocation.MyCommand.Path
$MIXXX_CTRL = "$env:LOCALAPPDATA\Mixxx\controllers"
$LOOPMIDI   = "https://www.tobias-erichsen.de/software/loopmidi.html"

Write-Host "=== mixxx-mcp Windows Setup ===" -ForegroundColor Cyan

# ── 1. Copy controller files ─────────────────────────────────────────────
Write-Host "`n[1/4] Copying controller files to Mixxx..." -ForegroundColor Yellow
if (-not (Test-Path $MIXXX_CTRL)) {
    New-Item -ItemType Directory -Path $MIXXX_CTRL -Force | Out-Null
    Write-Host "  Created: $MIXXX_CTRL"
}
Copy-Item "$REPO_DIR\mixxx-mcp.js"       $MIXXX_CTRL -Force
Copy-Item "$REPO_DIR\mixxx-mcp.midi.xml" $MIXXX_CTRL -Force
Write-Host "  Copied: mixxx-mcp.js + mixxx-mcp.midi.xml" -ForegroundColor Green

# ── 2. Check Python ──────────────────────────────────────────────────────
Write-Host "`n[2/4] Checking Python..." -ForegroundColor Yellow
try {
    $pyver = python --version 2>&1
    Write-Host "  Found: $pyver" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# ── 3. Install Python deps ────────────────────────────────────────────────
Write-Host "`n[3/4] Installing Python dependencies..." -ForegroundColor Yellow
Set-Location $REPO_DIR
python -m pip install mcp python-osc python-rtmidi --quiet
Write-Host "  Installed: mcp, python-osc, python-rtmidi" -ForegroundColor Green

# ── 4. loopMIDI check ─────────────────────────────────────────────────────
Write-Host "`n[4/4] Virtual MIDI port check..." -ForegroundColor Yellow
$midiPorts = python -c "import rtmidi; o=rtmidi.MidiOut(); print(o.get_ports())" 2>$null
if ($midiPorts -like "*mixxx-mcp*") {
    Write-Host "  loopMIDI port 'mixxx-mcp' found." -ForegroundColor Green
} else {
    Write-Host "  loopMIDI port NOT found." -ForegroundColor Red
    Write-Host "  ACTION REQUIRED:" -ForegroundColor Yellow
    Write-Host "    1. Download loopMIDI: $LOOPMIDI"
    Write-Host "    2. Install and launch loopMIDI"
    Write-Host "    3. Type 'mixxx-mcp' in the port name field, click +"
    Write-Host "    4. Re-run this script to verify"
}

# ── Done ──────────────────────────────────────────────────────────────────
Write-Host "`n=== Setup complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Launch loopMIDI (must stay running)"
Write-Host "  2. Open Mixxx → Preferences → Controllers → Enable 'mixxx-mcp'"
Write-Host "  3. Start the MCP server:"
Write-Host "       python $REPO_DIR\main.py" -ForegroundColor Green
Write-Host ""
Write-Host "Claude Desktop config (~\AppData\Roaming\Claude\claude_desktop_config.json):"
Write-Host @"
{
  "mcpServers": {
    "mixxx": {
      "command": "python",
      "args": ["$($REPO_DIR -replace '\\','\\\\')\\main.py"]
    }
  }
}
"@ -ForegroundColor DarkGray
