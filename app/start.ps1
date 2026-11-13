$ErrorActionPreference = 'Stop'
try {
    $projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $runtime = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $url = 'http://127.0.0.1:8765'
    $health = $null
    try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch {}
    if ($health -and ($health.app -ne 'work-report' -or $health.project -ne $projectRoot)) {
        throw '8765 포트를 다른 프로그램이 사용하고 있습니다.'
    }
    if (-not $health) {
        $serverPath = Join-Path $PSScriptRoot 'server.py'
        $outLog = Join-Path $PSScriptRoot 'server.stdout.log'
        $errLog = Join-Path $PSScriptRoot 'server.stderr.log'
        $proc = Start-Process -FilePath $runtime.python -ArgumentList @('"' + $serverPath + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
        $proc.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'server.pid')
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Milliseconds 300
            try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1; break } catch {}
        }
        if (-not $health) { throw "웹앱 실행에 실패했습니다. 로그: $errLog" }
    }
    $chromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if (-not (Test-Path -LiteralPath $chromePath)) { $chromePath = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe' }
    if (Test-Path -LiteralPath $chromePath) {
        Start-Process -FilePath $chromePath -ArgumentList @('--new-window', $url) -WindowStyle Normal
    } else { Start-Process $url }
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, '업무보고 웹앱') | Out-Null
}
