$ErrorActionPreference = 'Stop'
try {
    Set-Location -LiteralPath $PSScriptRoot
    $candidate = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($candidate) {
        & $candidate.Source -3 setup.py
    } else {
        $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $candidate) { throw 'Python 3.11 이상을 먼저 설치하세요: https://www.python.org/downloads/windows/' }
        & $candidate.Source setup.py
    }
    if ($LASTEXITCODE -ne 0) { throw '설치가 완료되지 않았습니다. 위 오류를 확인하세요.' }
    Write-Host '설치 완료. 바탕화면의 업무보고 작업실 아이콘을 실행하세요.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
