@echo off
setlocal

powershell -ExecutionPolicy Bypass -File "%~dp0install_jarvis_global.ps1" %*
