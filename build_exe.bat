@echo off
echo ============================================
echo  Smart Attendance -- Build Windows EXE
echo ============================================
echo.

call .venv\Scripts\activate.bat

echo [1/3] Installing / verifying dependencies...
pip install -r requirements.txt --quiet

echo [2/3] Installing Playwright browser...
playwright install chromium

echo [3/3] Building EXE with PyInstaller...
pyinstaller smart_attendance.spec --clean --noconfirm

echo.
echo ============================================
echo  Build complete!
echo  Executable: dist\SmartAttendance.exe
echo ============================================
pause
