@echo off
echo Isolating AntiGravity IDE (AI Brain & Memory)...

:: Isolate the AI's Brain and Customizations to this specific folder
set GEMINI_APP_DATA=%~dp0.gemini\antigravity-ide
set GEMINI_CONFIG_DIR=%~dp0.gemini\config

:: Instead of breaking Chrome by changing the global APPDATA,
:: we sandbox the IDE specifically using VS Code's portable data flags.
echo Starting AntiGravity IDE Workspace in strict portable mode...
antigravity-ide . --user-data-dir="%~dp0.ide-data" --extensions-dir="%~dp0.ide-extensions"
exit
