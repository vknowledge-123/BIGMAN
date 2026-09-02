param(
    [int]$Port = 8000
)

$Root = Split-Path -Parent $PSScriptRoot
$OutLog = Join-Path $Root "data\uvicorn.out.log"
$ErrLog = Join-Path $Root "data\uvicorn.err.log"
$PidFile = Join-Path $Root "data\uvicorn.pid"

$Process = Start-Process `
    -FilePath "py" `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden `
    -PassThru

$Process.Id | Set-Content -Path $PidFile

$Url = "http://127.0.0.1:$Port/api/state"
for ($Attempt = 1; $Attempt -le 10; $Attempt++) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5 | Select-Object -ExpandProperty Content
        exit 0
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

Get-Content $ErrLog -Tail 80
exit 1
