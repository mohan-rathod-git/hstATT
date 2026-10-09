@echo off
echo Running Smart Attendance tests...
call .venv\Scripts\activate.bat
pytest tests\ -v --tb=short
pause
