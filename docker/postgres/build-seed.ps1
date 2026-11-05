<#
.SYNOPSIS
  Generate the seed files for the cafy-agent-db image: full schema + job listings only (no personal data).

.DESCRIPTION
  Reads an existing database (DATABASE_URL in .env by default) with pg_dump. Read-only on the source.
  Writes docker\postgres\initdb\:
    01-schema.sql      every table, index and constraint in the public schema, no rows
    02-jobs.sql        rows of public.jobs (scraped job postings) and public.alembic_version
  Users, sign-in tokens, profiles, resumes, applications and email data are NOT included.

.EXAMPLE
  .\docker\postgres\build-seed.ps1
  docker build -t cafy-agent-db:local docker\postgres
#>
param(
  [string]$DatabaseUrl = "",
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin"
)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $PSScriptRoot "initdb"

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
if (-not (Test-Path $pgDump)) { throw "Not found: $pgDump (use -PgBin)" }

New-Item -ItemType Directory -Force -Path $out | Out-Null
$common = @("--no-owner", "--no-privileges", "--no-password", "--host=$($uri.Host)", "--port=$port", "--username=$user", "--dbname=$dbName")
$env:PGPASSWORD = $password
try {
  Write-Host "Schema (public, no rows) -> 01-schema.sql"
  $schemaFile = Join-Path $out "01-schema.sql"
  & $pgDump @common --schema-only --schema=public "--file=$schemaFile"
  if ($LASTEXITCODE -ne 0) { throw "pg_dump (schema) failed" }

  Write-Host "Job listings + migration version -> 02-jobs.sql"
  $jobsFile = Join-Path $out "02-jobs.sql"
  & $pgDump @common --data-only --table=public.jobs --table=public.alembic_version "--file=$jobsFile"
  if ($LASTEXITCODE -ne 0) { throw "pg_dump (jobs) failed" }
} finally {
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

# A fresh PostgreSQL already has the public schema; make the dump's CREATE SCHEMA safe to run there.
$schemaText = [System.IO.File]::ReadAllText($schemaFile)
$schemaText = $schemaText -replace '(?m)^CREATE SCHEMA public;', 'CREATE SCHEMA IF NOT EXISTS public;'
[System.IO.File]::WriteAllText($schemaFile, $schemaText, (New-Object System.Text.UTF8Encoding($false)))

Get-ChildItem $out | ForEach-Object { "{0,-16} {1,8:N0} KB" -f $_.Name, ($_.Length / 1KB) }
Write-Host "Seed ready. Build: docker build -t cafy-agent-db:local docker\postgres"
