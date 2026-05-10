# JARVIS Commands

## Core Terminal Commands

```powershell
jarvis cli
jarvis chat
jarvis think "what should I work on today?"
jarvis plan "build a FastAPI auth module"
jarvis run "create a backup script"
jarvis exec "open chrome"
jarvis memory "deadline"
jarvis status
jarvis logs 20
```

## Server Commands

```powershell
jarvis server
jarvis server /m
jarvis server --host 0.0.0.0 --port 8000
jarvis server /m --no-reload
```

Meaning:

- `jarvis server` starts the FastAPI backend.
- `jarvis server /m` starts the multi-model Ollama endpoints first, then starts the backend.

## GUI Commands

```powershell
jarvis gui
jarvis gui --device windows
jarvis gui --api-url http://127.0.0.1:8000
```

Notes:

- `jarvis gui` starts the Flutter app from `apps/jarvis_app`.
- Flutter must already be installed and available on `PATH`.
- On Windows, the launcher supports `flutter.bat` and `flutter.cmd` installations.
- If startup still fails, run `flutter doctor` and then try `flutter run -d windows` inside `apps/jarvis_app` to isolate Flutter-specific issues.

## Full Desktop Stack

```powershell
jarvis up
jarvis up /m
jarvis up /m --background
```

Meaning:

- `jarvis up` starts the desktop stack.
- `jarvis up /m` starts multi-model server mode plus the desktop stack.
- `jarvis up /m --background` opens the services in separate windows.

## Student AGI Commands

```powershell
jarvis student
jarvis student -- --status
jarvis student -- --teach python
jarvis student -- --daily
```

## Model Commands

```powershell
jarvis models list
jarvis models start
```

## IDE / Extension Commands

```powershell
jarvis extension list
jarvis extension show codex
jarvis extension show vscode
jarvis extension show cursor
jarvis extension show windsurf
jarvis extension show zed
jarvis extension show jetbrains
```

These commands print the local API endpoints and recommended startup commands for each IDE family.

## Dry Run Examples

```powershell
jarvis server /m --dry-run
jarvis gui --dry-run
jarvis up /m --background --dry-run
```

## Global Install

Windows PowerShell:

```powershell
.\scripts\install_jarvis_global.ps1
```

Windows CMD:

```cmd
scripts\install_jarvis_global.bat
```

Manual install:

```powershell
python -m pip install -e .
```

## Shell Completion

PowerShell:

- Installed automatically by `scripts/install_jarvis_global.ps1`
- Completion script: `completions/jarvis-completion.ps1`

Bash:

```bash
source completions/jarvis.bash
```

Zsh:

```bash
fpath=(./completions $fpath)
autoload -Uz compinit && compinit
```
