param(
    [string]$RepoPath = "",
    [int]$IntervalSeconds = 300,
    [switch]$Once,
    [switch]$Loop,
    [switch]$DryRun,
    [switch]$NoNotifications
)

$ErrorActionPreference = "Stop"
$script:ScriptPath = $MyInvocation.MyCommand.Path
$script:InitialCwd = (Get-Location).Path
$script:LogFile = $null
$script:FallbackLogFile = Join-Path ([System.IO.Path]::GetTempPath()) "macmarket_agent_scheduler_startup.log"

function Write-AgentSchedulerLog {
    param([string]$Message)
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ssK")
    $line = "[$stamp] $Message"
    if ($script:LogFile) {
        try {
            $line | Add-Content -LiteralPath $script:LogFile -Encoding UTF8
            return
        } catch {
            $fallbackLine = "[$stamp] LOG_WRITE_ERROR $($_.Exception.GetType().Name): $($_.Exception.Message)"
            $fallbackLine | Add-Content -LiteralPath $script:FallbackLogFile -Encoding UTF8
        }
    }
    $line | Add-Content -LiteralPath $script:FallbackLogFile -Encoding UTF8
}

function Write-AgentSchedulerConsole {
    param([string]$Message)
    if ($Once -or (-not $Loop -and $DryRun)) {
        Write-Host $Message
    }
}

function Invoke-AgentSchedulerCommand {
    param(
        [string]$Label,
        [string]$Python,
        [string[]]$Arguments
    )
    Write-AgentSchedulerLog "$Label START command=`"$Python $($Arguments -join ' ')`""
    Write-AgentSchedulerConsole "$Label START"
    $output = @()
    $exitCode = 0
    try {
        $output = & $Python @Arguments 2>&1
        $exitCode = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }
    } catch {
        $exitCode = 1
        $output = @("EXCEPTION $($_.Exception.GetType().Name): $($_.Exception.Message)")
    }
    foreach ($line in $output) {
        Write-AgentSchedulerLog "$Label OUT $line"
        Write-AgentSchedulerConsole "$line"
    }
    Write-AgentSchedulerLog "$Label END exit_code=$exitCode"
    Write-AgentSchedulerConsole "$Label END exit_code=$exitCode"
    return $exitCode
}

try {
    if (-not $Once -and -not $Loop) {
        $Loop = $true
    }
    if ($Once -and $Loop) {
        throw "Specify either -Once or -Loop, not both."
    }
    if ($DryRun) {
        $NoNotifications = $true
    }
    if ([string]::IsNullOrWhiteSpace($RepoPath)) {
        if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
            throw "Cannot infer RepoPath because PSScriptRoot is empty."
        }
        $RepoPath = Split-Path -Parent $PSScriptRoot
    }

    $RepoPath = [System.IO.Path]::GetFullPath($RepoPath)
    $LogDir = Join-Path $RepoPath "logs"
    if (-not (Test-Path -LiteralPath $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
    $script:LogFile = Join-Path $LogDir "agent_scheduler.log"
    $Python = Join-Path $RepoPath ".venv\Scripts\python.exe"
    $VenvPath = Join-Path $RepoPath ".venv"
    $EnvPath = Join-Path $RepoPath ".env"
    $ModeName = if ($Once) { "once" } else { "loop" }

    Write-AgentSchedulerLog "STARTUP timestamp=$((Get-Date).ToString('o'))"
    Write-AgentSchedulerLog "STARTUP script_path=$script:ScriptPath"
    Write-AgentSchedulerLog "STARTUP initial_cwd=$script:InitialCwd"
    Write-AgentSchedulerLog "STARTUP repo_root=$RepoPath"
    Write-AgentSchedulerLog "STARTUP mode=$ModeName dry_run=$($DryRun.IsPresent) no_notifications=$($NoNotifications.IsPresent)"
    Write-AgentSchedulerLog "STARTUP interval_seconds=$IntervalSeconds"
    Write-AgentSchedulerLog "STARTUP log_file=$script:LogFile"
    Write-AgentSchedulerLog "STARTUP python_path=$Python"
    Write-AgentSchedulerLog "STARTUP venv_exists=$(Test-Path -LiteralPath $VenvPath)"
    Write-AgentSchedulerLog "STARTUP env_exists=$(Test-Path -LiteralPath $EnvPath)"

    if (-not (Test-Path -LiteralPath $RepoPath)) {
        throw "RepoPath does not exist: $RepoPath"
    }
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Python not found at $Python"
    }

    Set-Location -LiteralPath $RepoPath
    Write-AgentSchedulerLog "HEARTBEAT startup cwd=$((Get-Location).Path)"

    [void](Invoke-AgentSchedulerCommand -Label "DB_DIAGNOSTICS" -Python $Python -Arguments @("-m", "macmarket_trader.cli", "db-diagnostics"))

    do {
        Write-AgentSchedulerLog "HEARTBEAT scheduler_loop check_start dry_run=$($DryRun.IsPresent) no_notifications=$($NoNotifications.IsPresent)"
        $checkArgs = @("-m", "macmarket_trader.cli", "agent-scheduler-check")
        if ($DryRun) {
            $checkArgs += "--dry-run"
        }
        if ($NoNotifications) {
            $checkArgs += "--no-notifications"
        }
        $exitCode = Invoke-AgentSchedulerCommand -Label "SCHEDULER_CHECK" -Python $Python -Arguments $checkArgs
        Write-AgentSchedulerLog "HEARTBEAT scheduler_loop check_end exit_code=$exitCode"
        if ($Once) {
            if ($exitCode -ne 0) {
                exit $exitCode
            }
            exit 0
        }
        $sleepSeconds = [Math]::Max(30, $IntervalSeconds)
        Write-AgentSchedulerLog "HEARTBEAT scheduler_loop sleeping_seconds=$sleepSeconds"
        Start-Sleep -Seconds $sleepSeconds
    } while ($true)
} catch {
    $message = "STARTUP_ERROR $($_.Exception.GetType().Name): $($_.Exception.Message)"
    Write-AgentSchedulerLog $message
    Write-AgentSchedulerConsole $message
    exit 1
}
