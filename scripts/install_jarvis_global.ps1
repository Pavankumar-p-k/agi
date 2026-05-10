param(
    [switch]$SkipCompletion
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = (Get-Command python -ErrorAction Stop).Source

Write-Host "Installing jarvis launcher globally from $RepoRoot"
& $PythonExe -m pip install -e $RepoRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not $SkipCompletion) {
    $CompletionScript = Join-Path $RepoRoot "completions\jarvis-completion.ps1"
    $ProfilePath = $PROFILE.CurrentUserAllHosts
    $ProfileDir = Split-Path -Parent $ProfilePath
    if (-not (Test-Path $ProfileDir)) {
        New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
    }
    if (-not (Test-Path $ProfilePath)) {
        New-Item -ItemType File -Path $ProfilePath -Force | Out-Null
    }
    $Line = ". `"$CompletionScript`""
    $ProfileContent = Get-Content $ProfilePath -ErrorAction SilentlyContinue
    if ($ProfileContent -notcontains $Line) {
        Add-Content -Path $ProfilePath -Value $Line
        Write-Host "PowerShell completion registered in $ProfilePath"
    } else {
        Write-Host "PowerShell completion already registered"
    }
}

Write-Host "Done. Open a new terminal and run: jarvis --help"
