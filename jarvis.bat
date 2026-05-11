@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%backend\.venv311\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%ROOT%backend\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%ROOT%backend\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" "%ROOT%jarvis.py" %*
