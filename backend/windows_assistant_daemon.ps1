param(
    [string]$WakePhrase = "jarvis",
    [string]$ServerHost = "127.0.0.1",
    [int]$ServerPort = 8000,
    [double]$MinConfidence = 0.62,
    [int]$CommandWindowSeconds = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Speech

$wake = $WakePhrase.Trim().ToLower()
if ([string]::IsNullOrWhiteSpace($wake)) {
    $wake = "jarvis"
}

$endpoint = "http://$ServerHost`:$ServerPort/api/automation/command"

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$installed = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }
$preferred = $installed | Where-Object { $_.Gender -eq "Male" -and $_.Culture.Name -like "en-*" } | Select-Object -First 1
if ($preferred) {
    try { $synth.SelectVoice($preferred.Name) } catch {}
}
$synth.Rate = -1
$synth.Volume = 100

function Speak([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) { return }
    try {
        $synth.SpeakAsyncCancelAll() | Out-Null
        $synth.SpeakAsync($text) | Out-Null
    } catch {}
}

function Normalize-Text([string]$text) {
    return ([string]$text).Trim().ToLower()
}

function Extract-Command([string]$inputText) {
    $t = Normalize-Text $inputText
    if (-not $t.Contains($wake)) { return "" }
    $idx = $t.IndexOf($wake)
    if ($idx -lt 0) { return "" }
    $cmd = $t.Substring($idx + $wake.Length).Trim()
    if ($cmd.StartsWith(",")) { $cmd = $cmd.Substring(1).Trim() }
    if ($cmd.StartsWith(":")) { $cmd = $cmd.Substring(1).Trim() }
    if ($cmd.StartsWith("please ")) { $cmd = $cmd.Substring(7).Trim() }
    return $cmd
}

Write-Host "[Windows Assistant] Starting..."
Write-Host "[Windows Assistant] Wake phrase: '$wake'"
Write-Host "[Windows Assistant] Endpoint: $endpoint"
Write-Host ("[Windows Assistant] Minimum confidence: {0:N2}" -f $MinConfidence)
Write-Host ("[Windows Assistant] Command window: {0}s" -f $CommandWindowSeconds)
Speak "Windows assistant started. Say $wake to begin."

$recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$recognizer.SetInputToDefaultAudioDevice()
$recognizer.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$script:RunLoop = $true
$script:AwaitingCommandUntil = Get-Date "2000-01-01"
$stopCommands = @("stop listening", "stop assistant", "exit assistant", "shutdown assistant")

$recognizedHandler = {
    param($sender, $eventArgs)
    try {
        $result = $eventArgs.Result
        if ($null -eq $result) { return }
        $confidence = [double]$result.Confidence
        if ($confidence -lt $MinConfidence) { return }

        $spoken = [string]$result.Text
        $spoken = $spoken.Trim()
        if ([string]::IsNullOrWhiteSpace($spoken)) { return }
        Write-Host ("[Heard] {0} (confidence {1:N2})" -f $spoken, $confidence)

        $normalized = Normalize-Text $spoken
        $hasWake = $normalized.Contains($wake)
        $cmd = ""
        if ($hasWake) {
            $cmd = Extract-Command $spoken
            if ([string]::IsNullOrWhiteSpace($cmd)) {
                $script:AwaitingCommandUntil = (Get-Date).AddSeconds($CommandWindowSeconds)
                Speak "Yes. Tell me your command."
                return
            }
        } elseif ((Get-Date) -lt $script:AwaitingCommandUntil) {
            $cmd = $normalized
        }
        if ([string]::IsNullOrWhiteSpace($cmd)) { return }

        $script:AwaitingCommandUntil = Get-Date "2000-01-01"

        Write-Host "[Command] $cmd"
        if ($stopCommands -contains $cmd) {
            Speak "Stopping windows assistant."
            Start-Sleep -Milliseconds 250
            $script:RunLoop = $false
            $sender.RecognizeAsyncStop()
            return
        }

        $body = @{ command = $cmd } | ConvertTo-Json
        try {
            $response = Invoke-RestMethod -Uri $endpoint -Method Post -ContentType "application/json" -Body $body -TimeoutSec 20
            $speech = ""
            if ($response -and $response.speech) {
                $speech = [string]$response.speech
            } elseif ($response -and $response.action) {
                $speech = [string]$response.action
            }
            if ([string]::IsNullOrWhiteSpace($speech)) {
                $speech = "Done."
            }
            Write-Host "[Reply] $speech"
            Speak $speech
        } catch {
            Write-Host "[Error] Could not reach backend: $($_.Exception.Message)"
            Speak "I could not reach the backend automation server."
        }
    } catch {
        Write-Host "[Error] Recognition handler failed: $($_.Exception.Message)"
    }
}

$hypothesisHandler = {
    param($sender, $eventArgs)
    $result = $eventArgs.Result
    if ($null -eq $result) { return }
    $text = [string]$result.Text
    $text = $text.Trim()
    if (-not [string]::IsNullOrWhiteSpace($text)) {
        Write-Host "[Partial] $text"
    }
}

$completedHandler = {
    param($sender, $eventArgs)
    if (-not $script:RunLoop) { return }
    Write-Host "[Info] Recognizer completed; restarting listener..."
    Start-Sleep -Milliseconds 600
    try {
        $sender.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
    } catch {
        Write-Host "[Error] Could not restart recognizer: $($_.Exception.Message)"
    }
}

$recognizer.add_SpeechRecognized($recognizedHandler)
$recognizer.add_SpeechHypothesized($hypothesisHandler)
$recognizer.add_RecognizeCompleted($completedHandler)
try {
    $recognizer.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
} catch {
    Write-Host "[Error] Failed to start recognizer: $($_.Exception.Message)"
    Speak "Speech recognizer failed to start."
}

try {
    while ($script:RunLoop) {
        Start-Sleep -Seconds 1
    }
} finally {
    try { $recognizer.RecognizeAsyncCancel() } catch {}
    try { $recognizer.Dispose() } catch {}
    try { $synth.Dispose() } catch {}
}
