# GarminCoach home server startup script
# Run once: uv pip install -e ".[server]"
# Then: .\start_server.ps1

$env:COACH_SERVER_TOKEN  = "REPLACE_WITH_YOUR_SECRET_TOKEN"   # pick any secret string
$env:ANTHROPIC_API_KEY   = "REPLACE_WITH_YOUR_ANTHROPIC_KEY"    # sk-ant-...
$env:COACH_PORT          = "8765"

Write-Host "Starting GarminCoach server on port $env:COACH_PORT..."
& uv run python server.py
