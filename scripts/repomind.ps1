param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('setup','start','stop','test','lint','format','index','evaluate')]
  [string]$Task,
  [switch]$Build
)
$root = Split-Path -Parent $PSScriptRoot
switch ($Task) {
  'setup' { if (!(Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env" }; docker compose -f "$root\docker-compose.yml" pull }
  'start' {
    if ($Build) {
      docker compose -f "$root\docker-compose.yml" up -d --build
    } else {
      docker compose -f "$root\docker-compose.yml" up -d
    }
  }
  'stop' { docker compose -f "$root\docker-compose.yml" down }
  'test' { Push-Location "$root\backend"; .\venv\Scripts\python.exe -m pytest; Pop-Location }
  'lint' { Push-Location "$root\frontend"; npm run lint; Pop-Location }
  'format' { Push-Location "$root\backend"; .\venv\Scripts\python.exe -m ruff format app tests; Pop-Location }
  'index' { Write-Host 'Use the Projects page or POST /api/v1/projects to register and index a repository.' }
  'evaluate' { Push-Location "$root\backend"; .\venv\Scripts\python.exe ..\scripts\performance_report.py; Pop-Location }
}
