<#
.SYNOPSIS
  Restore a pg_dump backup into the Docker PostgreSQL container ("db" service). Never overwrites data.

.DESCRIPTION
  Starts the db service, waits until it is healthy, and refuses to continue if the target database already
  contains tables in the public schema. The restore runs in a single transaction: it either fully succeeds
  or leaves the target database unchanged. The source dump file is not modified.

.EXAMPLE
  .\docker\restore-into-docker.ps1                     # newest backups\*.dump
  .\docker\restore-into-docker.ps1 -DumpFile backups\cafy_agent_20261106_101500.dump
#>
param([string]$DumpFile = "")
# Native tools (docker, pg_dump) write progress to stderr; check $LASTEXITCODE instead of failing on it.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  if (-not $DumpFile) {
    $latest = Get-ChildItem (Join-Path $root "backups") -Filter *.dump -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "No backups\*.dump found. Run .\docker\backup-local-db.ps1 first." }
    $DumpFile = $latest.FullName
  }
  $DumpFile = (Resolve-Path $DumpFile -ErrorAction Stop).Path
  if (Test-Path "$DumpFile.sha256") {
    $expected = ((Get-Content "$DumpFile.sha256") -split '\s+')[0]
    if ((Get-FileHash -Algorithm SHA256 $DumpFile).Hash -ne $expected) { throw "Checksum mismatch for $DumpFile" }
    Write-Host "Checksum OK"
  }

  docker compose up -d db 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "docker compose up -d db failed (exit $LASTEXITCODE)" }
  Write-Host "Waiting for the db container to be healthy..."
  for ($i = 0; $i -lt 60; $i++) {
    $state = docker inspect --format "{{.State.Health.Status}}" (docker compose ps -q db)
    if ($state -eq "healthy") { break }
    Start-Sleep -Seconds 2
  }
  if ($state -ne "healthy") { throw "db container is not healthy (state: $state)" }

  $existing = docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from information_schema.tables where table_schema = ''public''"'
  if ([int]$existing -gt 0) {
    throw "The Docker database already has $existing tables in public. Refusing to overwrite it. " +
          "To start over, back it up first, then remove the volume deliberately (see docs/DOCKER.md)."
  }

  $container = docker compose ps -q db
  docker cp $DumpFile "${container}:/tmp/restore.dump" | Out-Null
  Write-Host "Restoring $(Split-Path -Leaf $DumpFile) into the Docker database (single transaction)..."
  docker compose exec -T db sh -c 'pg_restore --no-owner --no-privileges --single-transaction --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump'
  $code = $LASTEXITCODE
  docker compose exec -T db rm -f /tmp/restore.dump | Out-Null
  if ($code -ne 0) { throw "pg_restore failed (exit $code). The Docker database was left unchanged." }
  Write-Host "Restore complete. Verify with: .\.venv\Scripts\python.exe docker\compare_databases.py"
} finally {
  Pop-Location
}
