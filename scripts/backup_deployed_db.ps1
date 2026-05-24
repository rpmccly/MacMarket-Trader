[CmdletBinding()]
param(
  [string]$DeployRoot = "C:\Dashboard\MacMarket-Trader",
  [string]$BackupRoot = "",
  [switch]$DryRun,
  [switch]$StopServices,
  [int[]]$Ports = @(9500, 9510)
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$BackupTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
  $BackupRoot = Join-Path $DeployRoot "backups\db\$BackupTimestamp"
}

$EnvVariableNames = @(
  "DATABASE_URL",
  "SQLALCHEMY_DATABASE_URL",
  "APP_DATABASE_URL",
  "MACMARKET_DATABASE_URL",
  "DB_PATH",
  "SQLITE_PATH"
)

$SqlitePathVariables = @("DB_PATH", "SQLITE_PATH")
$SearchFolderNames = @("data", "storage", ".")
$SearchExtensions = @(".sqlite", ".sqlite3", ".db")
$ExcludedFolders = @(".git", ".venv", "node_modules", ".next", "backups", "logs", "test-results")

function Write-Step {
  param([string]$Message)
  Write-Host "[backup-db] $Message"
}

function Write-WarningStep {
  param([string]$Message)
  Write-Host "[backup-db] WARNING: $Message" -ForegroundColor Yellow
}

function Resolve-FullPath {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$BasePath
  )
  $expanded = [Environment]::ExpandEnvironmentVariables($Path.Trim())
  if ([System.IO.Path]::IsPathRooted($expanded)) {
    return [System.IO.Path]::GetFullPath($expanded)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $BasePath $expanded))
}

function Read-EnvEntries {
  param([Parameter(Mandatory = $true)][string]$Path)
  $entries = @()
  if (-not (Test-Path -LiteralPath $Path)) {
    return $entries
  }

  foreach ($rawLine in Get-Content -LiteralPath $Path) {
    $line = $rawLine.Trim()
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
      continue
    }
    if ($line.StartsWith("export ")) {
      $line = $line.Substring(7).Trim()
    }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) {
      continue
    }

    $key = $line.Substring(0, $idx).Trim()
    if ($EnvVariableNames -notcontains $key) {
      continue
    }

    $value = $line.Substring($idx + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    $entries += [pscustomobject]@{
      Key = $key
      Value = $value
      Source = "$Path`:$key"
    }
  }
  return $entries
}

function Read-DeployedEnv {
  param([Parameter(Mandatory = $true)][string]$Root)
  $map = @{}
  foreach ($envFileName in @(".env", ".env.local")) {
    $envPath = Join-Path $Root $envFileName
    foreach ($entry in Read-EnvEntries -Path $envPath) {
      $map[$entry.Key] = $entry
    }
  }
  return $map
}

function Resolve-SqliteUrlPath {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$BasePath
  )
  $raw = $Url.Trim()
  foreach ($prefix in @("sqlite+pysqlite:///", "sqlite:///")) {
    if ($raw.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
      $dbPath = $raw.Substring($prefix.Length)
      $queryIndex = $dbPath.IndexOf("?")
      if ($queryIndex -ge 0) {
        $dbPath = $dbPath.Substring(0, $queryIndex)
      }
      $dbPath = [System.Uri]::UnescapeDataString($dbPath)
      if ($dbPath -eq ":memory:") {
        throw "SQLite in-memory database cannot be backed up from deployed files."
      }
      if ($dbPath -match "^/[A-Za-z]:/") {
        $dbPath = $dbPath.Substring(1)
      }
      return Resolve-FullPath -Path $dbPath -BasePath $BasePath
    }
  }
  return $null
}

function Test-IsPostgresUrl {
  param([string]$Value)
  return $Value -match "^(postgres|postgresql)://"
}

function Test-IsSqliteUrl {
  param([string]$Value)
  return $Value -match "^sqlite(\+pysqlite)?:///"
}

function Test-IsLikelySqlitePath {
  param([string]$Value)
  $extension = [System.IO.Path]::GetExtension(($Value -split "\?", 2)[0])
  return $SearchExtensions -contains $extension.ToLowerInvariant()
}

function Add-SqliteCandidate {
  param(
    [System.Collections.Generic.List[object]]$Candidates,
    [string]$Path,
    [string]$DiscoveredFrom,
    [System.Collections.Generic.List[string]]$Warnings
  )
  $fullPath = Resolve-FullPath -Path $Path -BasePath $DeployRoot
  if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
    $Warnings.Add("SQLite path from $DiscoveredFrom was not found: $fullPath")
    return
  }
  $Candidates.Add([pscustomobject]@{
    DatabaseType = "sqlite"
    Path = $fullPath
    DiscoveredFrom = $DiscoveredFrom
  })
}

function Test-IsExcludedPath {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Root
  )
  $full = [System.IO.Path]::GetFullPath($Path)
  $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
  if (-not $full.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $false
  }
  $relative = $full.Substring($rootFull.Length).TrimStart('\', '/')
  if ([string]::IsNullOrWhiteSpace($relative)) {
    return $false
  }
  $parts = $relative -split "[\\/]+"
  foreach ($part in $parts) {
    if ($ExcludedFolders -contains $part) {
      return $true
    }
  }
  return $false
}

function Find-SqliteFiles {
  param([Parameter(Mandatory = $true)][string]$Root)
  $found = New-Object "System.Collections.Generic.List[string]"
  $seen = @{}
  foreach ($folderName in $SearchFolderNames) {
    $folder = if ($folderName -eq ".") { $Root } else { Join-Path $Root $folderName }
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) {
      continue
    }
    foreach ($item in Get-ChildItem -LiteralPath $folder -Recurse -File -ErrorAction SilentlyContinue) {
      if ($SearchExtensions -notcontains $item.Extension.ToLowerInvariant()) {
        continue
      }
      if (Test-IsExcludedPath -Path $item.FullName -Root $Root) {
        continue
      }
      $full = [System.IO.Path]::GetFullPath($item.FullName)
      if (-not $seen.ContainsKey($full)) {
        $seen[$full] = $true
        $found.Add($full)
      }
    }
  }
  return $found
}

function Get-SqliteSidecars {
  param([Parameter(Mandatory = $true)][string]$DatabasePath)
  $paths = @(
    $DatabasePath,
    "$DatabasePath.wal",
    "$DatabasePath.shm",
    "$DatabasePath-wal",
    "$DatabasePath-shm",
    "$DatabasePath-journal"
  )
  $output = New-Object "System.Collections.Generic.List[string]"
  $seen = @{}
  foreach ($path in $paths) {
    if ((Test-Path -LiteralPath $path -PathType Leaf) -and -not $seen.ContainsKey($path)) {
      $seen[$path] = $true
      $output.Add($path)
    }
  }
  return $output
}

function Get-BackupDestination {
  param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$TargetRoot
  )
  $sourceFull = [System.IO.Path]::GetFullPath($SourcePath)
  $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
  if ($sourceFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    $relative = $sourceFull.Substring($rootFull.Length).TrimStart('\', '/')
    return Join-Path $TargetRoot $relative
  }
  $safeName = ($sourceFull -replace "[:\\/]+", "_").Trim("_")
  return Join-Path (Join-Path $TargetRoot "external") $safeName
}

function Get-Sha256 {
  param([Parameter(Mandatory = $true)][string]$Path)
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Stop-PortListeners {
  param(
    [int[]]$Ports,
    [switch]$DryRun
  )
  $records = New-Object "System.Collections.Generic.List[object]"
  foreach ($port in ($Ports | Sort-Object -Unique)) {
    $connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($connections.Count -eq 0) {
      Write-Step "No listener found on port $port."
      continue
    }
    foreach ($processId in ($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
      if ($processId -le 0) {
        continue
      }
      $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
      $processName = if ($process) { $process.ProcessName } else { "unknown" }
      $action = if ($DryRun) { "would_stop" } else { "stopped" }
      Write-Step "$action listener on port ${port}: pid $processId ($processName)"
      if (-not $DryRun) {
        Stop-Process -Id $processId -Force -ErrorAction Stop
      }
      $records.Add([pscustomobject]@{
        port = $port
        process_id = $processId
        process_name = $processName
        action = $action
      })
    }
  }
  return $records
}

function Get-PostgresConnectionInfo {
  param([Parameter(Mandatory = $true)][string]$Url)
  $uri = [System.Uri]$Url
  $user = ""
  $password = ""
  if (-not [string]::IsNullOrWhiteSpace($uri.UserInfo)) {
    $parts = $uri.UserInfo.Split(":", 2)
    $user = [System.Uri]::UnescapeDataString($parts[0])
    if ($parts.Count -gt 1) {
      $password = [System.Uri]::UnescapeDataString($parts[1])
    }
  }
  $database = [System.Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart("/"))
  if ([string]::IsNullOrWhiteSpace($database)) {
    throw "Postgres DATABASE_URL must include a database name."
  }
  $query = @{}
  foreach ($part in $uri.Query.TrimStart("?").Split("&")) {
    if ([string]::IsNullOrWhiteSpace($part)) { continue }
    $kv = $part.Split("=", 2)
    $key = [System.Uri]::UnescapeDataString($kv[0])
    $value = if ($kv.Count -gt 1) { [System.Uri]::UnescapeDataString($kv[1]) } else { "" }
    $query[$key] = $value
  }
  return [pscustomobject]@{
    Host = $uri.Host
    Port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
    Database = $database
    User = $user
    Password = $password
    SslMode = if ($query.ContainsKey("sslmode")) { $query["sslmode"] } else { "" }
  }
}

function Invoke-PostgresBackup {
  param(
    [Parameter(Mandatory = $true)][string]$ConnectionUrl,
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$TargetRoot,
    [switch]$DryRun
  )
  $pgDump = Get-Command "pg_dump" -ErrorAction SilentlyContinue
  if ($null -eq $pgDump) {
    throw "Postgres database detected from $Source, but pg_dump is not available. Install PostgreSQL client tools and retry."
  }
  $info = Get-PostgresConnectionInfo -Url $ConnectionUrl
  $dumpPath = Join-Path $TargetRoot "postgres-$BackupTimestamp.dump"

  if ($DryRun) {
    Write-Step "Would run pg_dump custom-format backup to $dumpPath."
    return [pscustomobject]@{
      files = @()
      file_sizes = @{}
      sha256_hashes = @{}
    }
  }

  New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
  $oldEnv = @{
    PGHOST = $env:PGHOST
    PGPORT = $env:PGPORT
    PGDATABASE = $env:PGDATABASE
    PGUSER = $env:PGUSER
    PGPASSWORD = $env:PGPASSWORD
    PGSSLMODE = $env:PGSSLMODE
  }
  try {
    $env:PGHOST = $info.Host
    $env:PGPORT = [string]$info.Port
    $env:PGDATABASE = $info.Database
    if (-not [string]::IsNullOrWhiteSpace($info.User)) { $env:PGUSER = $info.User }
    if (-not [string]::IsNullOrWhiteSpace($info.Password)) { $env:PGPASSWORD = $info.Password }
    if (-not [string]::IsNullOrWhiteSpace($info.SslMode)) { $env:PGSSLMODE = $info.SslMode }

    & $pgDump.Source "--format=custom" "--file=$dumpPath" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "pg_dump failed with exit code $LASTEXITCODE. Verify database credentials, network access, and permissions. The connection string was not printed."
    }
  } finally {
    foreach ($key in $oldEnv.Keys) {
      if ($null -eq $oldEnv[$key]) {
        Remove-Item -Path "Env:\$key" -ErrorAction SilentlyContinue
      } else {
        Set-Item -Path "Env:\$key" -Value $oldEnv[$key]
      }
    }
  }

  $sizes = @{}
  $hashes = @{}
  $sizes[$dumpPath] = (Get-Item -LiteralPath $dumpPath).Length
  $hashes[$dumpPath] = Get-Sha256 -Path $dumpPath
  return [pscustomobject]@{
    files = @($dumpPath)
    file_sizes = $sizes
    sha256_hashes = $hashes
  }
}

function Write-RestoreReadme {
  param(
    [Parameter(Mandatory = $true)][string]$TargetRoot,
    [Parameter(Mandatory = $true)][string]$DatabaseType
  )
  $notes = @(
    "MacMarket-Trader pre-migration database backup",
    "",
    "Created: $(Get-Date -Format o)",
    "",
    "Safety notes:",
    "- Stop backend/frontend/scheduler processes before restoring a SQLite database.",
    "- Do not restore over a running database file.",
    "- Verify the manifest hashes before using a backup.",
    "- This backup script does not run Alembic or modify the source database.",
    ""
  )
  if ($DatabaseType -eq "postgres") {
    $notes += @(
      "Postgres restore outline:",
      "- Create or select the target database explicitly.",
      "- Use pg_restore with the custom-format dump in this folder.",
      "- Keep credentials out of shell history and logs."
    )
  } else {
    $notes += @(
      "SQLite restore outline:",
      "- Stop services first.",
      "- Copy the backed-up .db/.sqlite/.sqlite3 file and any sidecars back to the deployed DB path.",
      "- Restart services only after the files are in place."
    )
  }
  Set-Content -LiteralPath (Join-Path $TargetRoot "README.txt") -Value ($notes -join [Environment]::NewLine) -Encoding UTF8
}

function Write-Manifest {
  param(
    [Parameter(Mandatory = $true)][hashtable]$Manifest,
    [Parameter(Mandatory = $true)][string]$TargetRoot
  )
  $manifestPath = Join-Path $TargetRoot "backup-manifest.json"
  $Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
  return $manifestPath
}

function Main {
  Write-Step "Deploy root: $DeployRoot"
  Write-Step "Backup root: $BackupRoot"
  Write-Step "Dry run: $($DryRun.IsPresent)"

  if (-not (Test-Path -LiteralPath $DeployRoot -PathType Container)) {
    throw "Deploy root not found: $DeployRoot"
  }

  $deployFull = [System.IO.Path]::GetFullPath($DeployRoot)
  $backupFull = [System.IO.Path]::GetFullPath($BackupRoot)
  $warnings = New-Object "System.Collections.Generic.List[string]"
  $envMap = Read-DeployedEnv -Root $deployFull
  $sqliteCandidates = New-Object "System.Collections.Generic.List[object]"
  $postgresCandidate = $null

  foreach ($key in $EnvVariableNames) {
    if (-not $envMap.ContainsKey($key)) {
      continue
    }
    $entry = $envMap[$key]
    $value = [string]$entry.Value
    if ([string]::IsNullOrWhiteSpace($value)) {
      continue
    }
    if (Test-IsPostgresUrl -Value $value) {
      $postgresCandidate = [pscustomobject]@{
        DatabaseType = "postgres"
        ConnectionUrl = $value
        DiscoveredFrom = $entry.Source
      }
      break
    }
    if (Test-IsSqliteUrl -Value $value) {
      $sqlitePath = Resolve-SqliteUrlPath -Url $value -BasePath $deployFull
      Add-SqliteCandidate -Candidates $sqliteCandidates -Path $sqlitePath -DiscoveredFrom $entry.Source -Warnings $warnings
    } elseif (($SqlitePathVariables -contains $key) -or (Test-IsLikelySqlitePath -Value $value)) {
      Add-SqliteCandidate -Candidates $sqliteCandidates -Path $value -DiscoveredFrom $entry.Source -Warnings $warnings
    }
  }

  if ($null -eq $postgresCandidate) {
    foreach ($path in Find-SqliteFiles -Root $deployFull) {
      $sqliteCandidates.Add([pscustomobject]@{
        DatabaseType = "sqlite"
        Path = $path
        DiscoveredFrom = "filesystem_search"
      })
    }
  }

  foreach ($warning in $warnings) {
    Write-WarningStep $warning
  }

  $stoppedPorts = @()
  if ($StopServices) {
    $stoppedPorts = @(Stop-PortListeners -Ports $Ports -DryRun:$DryRun)
  } else {
    Write-Step "StopServices not supplied; no services will be stopped."
  }

  if ($null -ne $postgresCandidate) {
    Write-Step "Detected Postgres database from $($postgresCandidate.DiscoveredFrom). Connection string hidden."
    $backupResult = Invoke-PostgresBackup -ConnectionUrl $postgresCandidate.ConnectionUrl -Source $postgresCandidate.DiscoveredFrom -TargetRoot $backupFull -DryRun:$DryRun
    $manifest = @{
      backup_timestamp = (Get-Date).ToUniversalTime().ToString("o")
      deploy_root = $deployFull
      backup_root = $backupFull
      database_type = "postgres"
      discovered_from = $postgresCandidate.DiscoveredFrom
      files_backed_up = $backupResult.files
      file_sizes = $backupResult.file_sizes
      sha256_hashes = $backupResult.sha256_hashes
      stopped_ports = $stoppedPorts
      dry_run = [bool]$DryRun
    }
    if ($DryRun) {
      Write-Step "Dry run complete. No backup files or manifest were written."
      return 0
    }
    Write-RestoreReadme -TargetRoot $backupFull -DatabaseType "postgres"
    $manifestPath = Write-Manifest -Manifest $manifest -TargetRoot $backupFull
    Write-Step "Backup manifest: $manifestPath"
    Write-Step "Postgres backup complete."
    return 0
  }

  $dbPaths = New-Object "System.Collections.Generic.List[string]"
  $seenDb = @{}
  foreach ($candidate in $sqliteCandidates) {
    $full = [System.IO.Path]::GetFullPath([string]$candidate.Path)
    if (-not $seenDb.ContainsKey($full)) {
      $seenDb[$full] = $true
      $dbPaths.Add($full)
    }
  }

  if ($dbPaths.Count -eq 0) {
    throw "No deployed database found. Checked env variables and likely SQLite folders under $deployFull."
  }

  if (-not $StopServices) {
    Write-WarningStep "SQLite backups are safest when backend/frontend/scheduler listeners are stopped. Re-run with -StopServices to stop supplied ports before copying."
  }

  $copyPairs = New-Object "System.Collections.Generic.List[object]"
  $seenFiles = @{}
  foreach ($dbPath in $dbPaths) {
    foreach ($filePath in Get-SqliteSidecars -DatabasePath $dbPath) {
      $full = [System.IO.Path]::GetFullPath($filePath)
      if ($seenFiles.ContainsKey($full)) {
        continue
      }
      $seenFiles[$full] = $true
      $dest = Get-BackupDestination -SourcePath $full -Root $deployFull -TargetRoot $backupFull
      $copyPairs.Add([pscustomobject]@{
        Source = $full
        Destination = $dest
      })
    }
  }

  Write-Step "Detected SQLite backup set with $($copyPairs.Count) file(s)."
  foreach ($pair in $copyPairs) {
    if ($DryRun) {
      Write-Step "Would copy: $($pair.Source) -> $($pair.Destination)"
    }
  }
  if ($DryRun) {
    Write-Step "Dry run complete. No backup files or manifest were written."
    return 0
  }

  $filesBackedUp = New-Object "System.Collections.Generic.List[string]"
  $fileSizes = @{}
  $hashes = @{}
  foreach ($pair in $copyPairs) {
    $destDir = Split-Path -Parent $pair.Destination
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item -LiteralPath $pair.Source -Destination $pair.Destination -Force
    $filesBackedUp.Add($pair.Destination)
    $fileSizes[$pair.Destination] = (Get-Item -LiteralPath $pair.Destination).Length
    $hashes[$pair.Destination] = Get-Sha256 -Path $pair.Destination
    Write-Step "Copied: $($pair.Source) -> $($pair.Destination)"
  }

  $discoveredFrom = @()
  foreach ($candidate in $sqliteCandidates) {
    if ($candidate.PSObject.Properties.Name -contains "DiscoveredFrom") {
      $discoveredFrom += [string]$candidate.DiscoveredFrom
    }
  }
  $discoveredFrom = @($discoveredFrom | Sort-Object -Unique)

  $manifest = @{
    backup_timestamp = (Get-Date).ToUniversalTime().ToString("o")
    deploy_root = $deployFull
    backup_root = $backupFull
    database_type = "sqlite"
    discovered_from = $discoveredFrom
    files_backed_up = $filesBackedUp
    file_sizes = $fileSizes
    sha256_hashes = $hashes
    stopped_ports = $stoppedPorts
    dry_run = [bool]$DryRun
  }
  Write-RestoreReadme -TargetRoot $backupFull -DatabaseType "sqlite"
  $manifestPath = Write-Manifest -Manifest $manifest -TargetRoot $backupFull
  Write-Step "Backup manifest: $manifestPath"
  Write-Step "SQLite backup complete."
  return 0
}

try {
  exit (Main)
} catch {
  Write-Host "[backup-db] ERROR: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
