# WinTweaker

Простой твикер скрытых настроек Windows 10/11 на Python (customtkinter).
Каждый переключатель обратим: выключили — значение вернулось.

## Запуск
    pip install -r requirements.txt
    python tweaker.py

Для твиков с пометкой «админ» запускайте от имени администратора.

## Сборка .exe
Запушьте в GitHub: вкладка Actions -> Build exe -> Artifacts -> WinTweaker-exe.
Локально:
    pyinstaller --onefile --noconsole --uac-admin --collect-all customtkinter --name WinTweaker tweaker.py

## Добавить свой твик
Допишите объект `Tweak(...)` в список `TWEAKS` в tweaker.py.
