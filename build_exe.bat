@echo off
cd /d "%~dp0"
py -m PyInstaller --noconfirm --onedir --windowed --name SPX_Order_Tracking --collect-all playwright --distpath build\bundle --workpath build\onedir --specpath build app.pyw
if errorlevel 1 goto finish
copy /Y build\bundle\SPX_Order_Tracking\SPX_Order_Tracking.exe .
xcopy /E /I /Y build\bundle\SPX_Order_Tracking\_internal _internal
:finish
pause
