$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $repoRoot 'apps/api')
$env:UV_CACHE_DIR = Join-Path $repoRoot '.uv-cache'
uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
