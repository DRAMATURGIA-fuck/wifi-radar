@echo off
REM Сборка одного wifi-radar.exe под Windows (нужен установленный Python).
REM Запусти двойным кликом или из cmd в папке проекта.

echo [1/2] Устанавливаю PyInstaller...
python -m pip install --upgrade pyinstaller || goto :err

echo [2/2] Собираю exe...
python -m PyInstaller --onefile --windowed --name wifi-radar ^
    --icon assets\icon.ico wifi_radar.py || goto :err

echo.
echo Готово! Файл: dist\wifi-radar.exe
echo Его можно запускать на любом Windows без установленного Python.
pause
exit /b 0

:err
echo.
echo Ошибка сборки. Убедись, что Python установлен и добавлен в PATH
echo (python --version должно что-то вывести).
pause
exit /b 1
