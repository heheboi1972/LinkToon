$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$originalPublicApiUrl = $env:NEXT_PUBLIC_API_URL
try {
    if (-not $env:NEXT_PUBLIC_API_URL) { $env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000' }
    foreach ($step in @('lint', 'typecheck', 'test', 'build')) {
        npm run $step
        if ($LASTEXITCODE -ne 0) { throw "Frontend $step failed" }
    }
} finally {
    if ($null -eq $originalPublicApiUrl) {
        Remove-Item Env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
    } else {
        $env:NEXT_PUBLIC_API_URL = $originalPublicApiUrl
    }
}
Push-Location -LiteralPath 'apps/api'
try {
    $env:UV_CACHE_DIR = Join-Path $repoRoot '.uv-cache'
    uv run ruff check . ../../scripts
    if ($LASTEXITCODE -ne 0) { throw 'Backend lint failed' }
    uv run mypy app
    if ($LASTEXITCODE -ne 0) { throw 'Backend typecheck failed' }
    uv run pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
    uv run alembic check
    if ($LASTEXITCODE -ne 0) { throw 'Migration drift detected' }
} finally { Pop-Location }
