# MacMarket-Trader deploy test temp helper.
#
# Provides a unique per-run pytest --basetemp path outside the deploy tree,
# best-effort stale-temp cleanup, and a guarded robust path remover that
# refuses to touch deploy runtime data (data/storage/uploads/logs/backups).
#
# Modes (-Mode):
#   New          Print a fresh unique basetemp path under
#                $env:TEMP\macmarket-pytest-deploy\<timestamp>-<pid>.
#   CleanStale   Delete macmarket-pytest-deploy\* entries older than
#                -MaxAgeDays days. Always exits 0 (best-effort).
#   Remove       Best-effort robust removal of -Path, refusing dangerous
#                paths. Used after tests complete. Always exits 0.
#
# Intentional design notes:
# * The helper never deletes data/storage/uploads/logs/backups directly. Even
#   if -Path points at one of those, it refuses.
# * Removal is retried a few times with short sleeps to ride out transient
#   Windows file-lock errors from lingering child processes.
# * Read-only/system/hidden attributes are cleared recursively before delete.
# * No takeown/icacls fall-through. The deploy script logs a clear warning
#   when not running as Administrator and proceeds without escalation.

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("New", "CleanStale", "Remove")]
  [string]$Mode,

  [string]$Path,
  [int]$MaxAgeDays = 1,
  [int]$Retries = 4,
  [int]$RetrySleepMs = 250
)

$ErrorActionPreference = "Continue"

function Get-DeployTempRoot {
  $base = $env:TEMP
  if ([string]::IsNullOrWhiteSpace($base)) {
    $base = $env:LOCALAPPDATA
    if (-not [string]::IsNullOrWhiteSpace($base)) {
      $base = Join-Path $base "Temp"
    }
  }
  if ([string]::IsNullOrWhiteSpace($base)) {
    $base = "C:\Windows\Temp"
  }
  return (Join-Path $base "macmarket-pytest-deploy")
}

function Test-IsDangerousPath {
  param([string]$Candidate)
  if ([string]::IsNullOrWhiteSpace($Candidate)) { return $true }

  try {
    $full = [System.IO.Path]::GetFullPath($Candidate)
  } catch {
    return $true
  }

  $normalized = $full.TrimEnd('\','/').ToLowerInvariant()
  if ([string]::IsNullOrWhiteSpace($normalized)) { return $true }

  # Refuse drive roots and very short paths.
  if ($normalized.Length -le 3) { return $true }
  if ($normalized -match '^[a-z]:\\?$') { return $true }

  # Refuse Windows and root program paths outright.
  $forbiddenPrefixes = @(
    "c:\windows",
    "c:\program files",
    "c:\program files (x86)",
    "c:\users\public",
    "c:\$recycle.bin"
  )
  foreach ($prefix in $forbiddenPrefixes) {
    if ($normalized.StartsWith($prefix)) { return $true }
  }

  # Refuse the deploy root itself. Removal is only allowed for known temp/cache
  # artifact subdirectories, not the deploy root or its runtime data folders.
  $deployRoot = "c:\dashboard\macmarket-trader"
  if ($normalized -eq $deployRoot) { return $true }
  if ($normalized -eq ($deployRoot + "\")) { return $true }

  $protectedSuffixes = @(
    "\data", "\storage", "\uploads", "\logs", "\backups",
    "\apps", "\src", "\tests", "\scripts", "\docs", "\alembic"
  )
  foreach ($suffix in $protectedSuffixes) {
    if ($normalized.EndsWith($suffix)) { return $true }
  }

  return $false
}

function Test-IsAllowedTempPath {
  param([string]$Candidate)
  if ([string]::IsNullOrWhiteSpace($Candidate)) { return $false }
  try {
    $full = [System.IO.Path]::GetFullPath($Candidate)
  } catch {
    return $false
  }
  $normalized = $full.ToLowerInvariant()

  # Only allow temp/cache artifacts and known scratch folders.
  $allowedFragments = @(
    "\.tmp\pytest-deploy",
    "\.tmp\pytest-deploy\",
    "\.pytest_cache",
    "\.pytest-tmp",
    "\macmarket-pytest-deploy\",
    "\macmarket-pytest-deploy"
  )
  foreach ($fragment in $allowedFragments) {
    if ($normalized.Contains($fragment)) { return $true }
  }
  return $false
}

function Clear-PathAttributes {
  param([string]$Target)
  if (-not (Test-Path -LiteralPath $Target)) { return }
  try {
    Get-ChildItem -LiteralPath $Target -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
      try {
        $_.Attributes = 'Normal'
      } catch {
        # Ignore individual attribute clears; best-effort only.
      }
    }
  } catch {
    # Best-effort.
  }
}

function Remove-PathRobust {
  param(
    [string]$Target,
    [int]$Attempts = 4,
    [int]$SleepMs = 250
  )

  if (-not (Test-Path -LiteralPath $Target)) {
    return $true
  }

  if (Test-IsDangerousPath -Candidate $Target) {
    Write-Warning ("[deploy-test-temp] refusing to remove protected path: {0}" -f $Target)
    return $false
  }

  if (-not (Test-IsAllowedTempPath -Candidate $Target)) {
    Write-Warning ("[deploy-test-temp] refusing to remove non-temp path: {0}" -f $Target)
    return $false
  }

  for ($i = 1; $i -le $Attempts; $i++) {
    try {
      Clear-PathAttributes -Target $Target
      Remove-Item -LiteralPath $Target -Recurse -Force -ErrorAction Stop
      if (-not (Test-Path -LiteralPath $Target)) {
        return $true
      }
    } catch {
      if ($i -eq $Attempts) {
        Write-Warning ("[deploy-test-temp] cleanup failed for {0}: {1}" -f $Target, $_.Exception.Message)
        return $false
      }
      Start-Sleep -Milliseconds $SleepMs
    }
  }
  return $false
}

switch ($Mode) {
  "New" {
    $root = Get-DeployTempRoot
    try {
      if (-not (Test-Path -LiteralPath $root)) {
        New-Item -ItemType Directory -Path $root -Force | Out-Null
      }
    } catch {
      Write-Warning ("[deploy-test-temp] could not create temp root {0}: {1}" -f $root, $_.Exception.Message)
    }
    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss-fff")
    $unique = "{0}-{1}" -f $stamp, $PID
    $full = Join-Path $root $unique
    try {
      New-Item -ItemType Directory -Path $full -Force | Out-Null
    } catch {
      Write-Warning ("[deploy-test-temp] could not create unique temp {0}: {1}" -f $full, $_.Exception.Message)
    }
    # Emit the absolute path on stdout for the caller. Nothing else.
    Write-Output $full
    exit 0
  }

  "CleanStale" {
    $root = Get-DeployTempRoot
    if (-not (Test-Path -LiteralPath $root)) {
      exit 0
    }
    $cutoff = (Get-Date).AddDays(-1 * [Math]::Max(0, $MaxAgeDays))
    try {
      Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue | ForEach-Object {
        try {
          if ($_.LastWriteTime -lt $cutoff) {
            $candidate = $_.FullName
            if ((Test-IsAllowedTempPath -Candidate $candidate) -and -not (Test-IsDangerousPath -Candidate $candidate)) {
              [void](Remove-PathRobust -Target $candidate -Attempts $Retries -SleepMs $RetrySleepMs)
            }
          }
        } catch {
          # Best-effort; never fail deploy on stale cleanup.
        }
      }
    } catch {
      Write-Warning ("[deploy-test-temp] stale cleanup encountered an error: {0}" -f $_.Exception.Message)
    }
    exit 0
  }

  "Remove" {
    if ([string]::IsNullOrWhiteSpace($Path)) {
      exit 0
    }
    [void](Remove-PathRobust -Target $Path -Attempts $Retries -SleepMs $RetrySleepMs)
    exit 0
  }
}
