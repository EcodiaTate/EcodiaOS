@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%collate.py" %*
endlocal
