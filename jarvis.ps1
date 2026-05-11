$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $Root "backend\.venv311\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) { $PythonExe = Join-Path $Root "backend\.venv\Scripts\python.exe" }
if (-not (Test-Path $PythonExe)) { $PythonExe = Join-Path $Root "backend\venv\Scripts\python.exe" }
if (-not (Test-Path $PythonExe)) { $PythonExe = "python" }

# Add the jarvis root directory to PYTHONPATH so jarvis_os can be found
$env:PYTHONPATH = $Root + ";" + $env:PYTHONPATH
if (-not $env:PYTHONPATH) { $env:PYTHONPATH = $Root }

# Also add to sys.path in the script by setting PYTHONPATH
& $PythonExe (Join-Path $Root "jarvis.py") @args
