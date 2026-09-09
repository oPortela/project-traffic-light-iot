@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Crie o ambiente Python seguindo as instrucoes do README.md.
  pause
  exit /b 1
)
echo Abra http://127.0.0.1:8000 no navegador.
echo Para encerrar, pressione Ctrl+C.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
