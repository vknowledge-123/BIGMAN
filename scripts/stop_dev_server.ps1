$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root "data\uvicorn.pid"
$Stopped = @()

if (Test-Path $PidFile) {
    $ProcessIdFromFile = Get-Content $PidFile | Select-Object -First 1
    if ($ProcessIdFromFile) {
        try {
            Stop-Process -Id ([int]$ProcessIdFromFile) -ErrorAction Stop
            $Stopped += $ProcessIdFromFile
        }
        catch {
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$Processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -like "*uvicorn*" -and
        $_.CommandLine -like "*app.main:app*"
    }

foreach ($Process in $Processes) {
    try {
        Stop-Process -Id ([int]$Process.ProcessId) -ErrorAction Stop
        $Stopped += $Process.ProcessId
    }
    catch {
    }
}

if ($Stopped.Count -eq 0) {
    Write-Output "No scanner uvicorn process was running."
}
else {
    Write-Output "Stopped scanner uvicorn process(es): $($Stopped -join ', ')."
}
