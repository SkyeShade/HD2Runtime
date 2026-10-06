@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
set "STATUS=%ERRORLEVEL%"
rem Started by a double-click, the window closes on exit: keep it open so a failure can be read.
if not "%STATUS%"=="0" echo %cmdcmdline% | "%SystemRoot%\System32\find.exe" /i "%~nx0" >nul && pause
exit /b %STATUS%
