param([string]$Python = "3.12", [switch]$Postgres)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if (-not (Test-Path -LiteralPath '.env')) {
    $randomBytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($randomBytes)
    $rng.Dispose()
    $secret = [Convert]::ToBase64String($randomBytes)
    $template = (Get-Content -LiteralPath '.env.example' -Raw).Replace('GENERATE_WITH_SETUP_SCRIPT', $secret)
    if ($Postgres) {
        $template = $template.Replace('sqlite:///./.data/linktoon.db', 'postgresql+psycopg://linktoon:linktoon_local@localhost:5432/linktoon')
    }
    [IO.File]::WriteAllText((Join-Path $repoRoot '.env'), $template, (New-Object Text.UTF8Encoding($false)))
}
npm install
if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
Push-Location -LiteralPath 'apps/api'
try {
    $env:UV_CACHE_DIR = Join-Path $repoRoot '.uv-cache'
    uv sync --python $Python
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed. For PostgreSQL start docker compose up -d db redis first.' }
} finally { Pop-Location }
Write-Output 'Setup complete. Run scripts/start-api.ps1 and npm run dev in separate terminals.'
