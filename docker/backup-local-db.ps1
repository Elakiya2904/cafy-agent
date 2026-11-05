<#
.SYNOPSIS
  Back up the existing (non-Docker) Cafy Agent PostgreSQL database to backups\*.dump. Read-only on the source.

.DESCRIPTION
  Reads the connection from DATABASE_URL in .env (or -DatabaseUrl), runs pg_dump in custom format,
  checks the dump can be read with pg_restore --list, and writes a SHA-256 checksum next to it.
  The source database is never modified.

.EXAMPLE
  .\docker\backup-local-db.ps1
  .\docker\backup-local-db.ps1 -PgBin "C:\Program Files\PostgreSQL\18\bin"
#>
param(
  [string]$DatabaseUrl = "",
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
  [string]$OutDir = ""
)
# Native tools (docker, pg_dump) write progress to stderr; check $LASTEXITCODE instead of failing on it.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $root "backups" }

if (-not $DatabaseUrl) {
  $line = Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
  if (-not $line) { throw "DATABASE_URL not found in .env; pass -DatabaseUrl." }
  $DatabaseUrl = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
}
$uri = [System.Uri]($DatabaseUrl -replace '^postgresql\+psycopg://', 'postgresql://')
$user, $password = $uri.UserInfo -split ':', 2
$user = [System.Uri]::UnescapeDataString($user)
$password = if ($password) { [System.Uri]::UnescapeDataString($password) } else { "" }
$dbName = $uri.AbsolutePath.TrimStart('/')
$port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }

$pgDump = Join-Path $PgBin "pg_dump.exe"
$pgRestore = Join-Path $PgBin "pg_restore.exe"
foreach ($tool in @($pgDump, $pgRestore)) { if (-not (Test-Path $tool)) { throw "Not found: $tool (use -PgBin)" } }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dump = Join-Path $OutDir "${dbName}_$stamp.dump"

Write-Host "Backing up $dbName on $($uri.Host):$port as $user -> $dump"
$env:PGPASSWORD = $password
try {
  & $pgDump --format=custom --compress=6 --no-password --host=$($uri.Host) --port=$port --username=$user --dbname=$dbName --file=$dump
  if ($LASTEXITCODE -ne 0) { throw "pg_dump failed (exit $LASTEXITCODE)" }
} finally {
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

$entries = & $pgRestore --list $dump
if ($LASTEXITCODE -ne 0) { throw "The dump could not be read back (pg_restore --list failed)." }
$tables = ($entries | Select-String ' TABLE DATA ').Count
$hash = (Get-FileHash -Algorithm SHA256 $dump).Hash
"$hash  $(Split-Path -Leaf $dump)" | Set-Content -Encoding ascii "$dump.sha256"

$size = "{0:N1} MB" -f ((Get-Item $dump).Length / 1MB)
Write-Host "OK: $size, $tables tables with data, SHA-256 $hash"
Write-Host "Dump: $dump"
