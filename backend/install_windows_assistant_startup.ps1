param(
    [string]$TaskName = "JarvisWindowsAssistant"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed startup task '$TaskName'."
} else {
    Write-Host "Startup task '$TaskName' not found."
}

Write-Host "Background assistant startup is disabled."
