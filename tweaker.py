"""WinTweaker: простой твикер скрытых настроек Windows 10/11.

Каждый твик описан данными (раздел реестра, значение «вкл» и «выкл»),
поэтому любое изменение можно вернуть обратно тем же переключателем.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter.messagebox as mb
from dataclasses import dataclass
from typing import Any, Optional

if sys.platform != "win32":
    sys.exit("WinTweaker работает только в Windows.")

import winreg  # noqa: E402

import customtkinter as ctk  # noqa: E402

HKCU = winreg.HKEY_CURRENT_USER
HKLM = winreg.HKEY_LOCAL_MACHINE
DWORD = winreg.REG_DWORD
SZ = winreg.REG_SZ

ADV = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
CLASSIC_MENU = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"


@dataclass
class Tweak:
    category: str
    title: str
    desc: str
    hive: int
    path: str
    name: str
    kind: int
    on: Any            # значение, когда твик включён
    off: Any           # значение, когда выключен (None = удалить значение)
    admin: bool = False
    special: Optional[str] = None  # "keyexists" для ключей без значений


TWEAKS = [
    # --- Интерфейс ---
    Tweak("Интерфейс", "Показывать расширения файлов", "Видеть .txt, .exe, .png в именах",
          HKCU, ADV, "HideFileExt", DWORD, 0, 1),
    Tweak("Интерфейс", "Показывать скрытые файлы", "Скрытые файлы и папки видны в Проводнике",
          HKCU, ADV, "Hidden", DWORD, 1, 2),
    Tweak("Интерфейс", "Старое контекстное меню (Win 11)", "Правый клик без «Показать дополнительные параметры»",
          HKCU, CLASSIC_MENU, "", SZ, "", None, special="keyexists"),
    Tweak("Интерфейс", "Панель задач слева (Win 11)", "Кнопка «Пуск» и значки слева, как в Win 10",
          HKCU, ADV, "TaskbarAl", DWORD, 0, 1),
    Tweak("Интерфейс", "Секунды в часах на панели задач", "Часы показывают чч:мм:сс",
          HKCU, ADV, "ShowSecondsInSystemClock", DWORD, 1, 0),
    Tweak("Интерфейс", "Отключить залипание клавиш (Shift x5)", "Не появляется окно при быстрых нажатиях Shift",
          HKCU, r"Control Panel\Accessibility\StickyKeys", "Flags", SZ, "506", "510"),
    # --- Приватность ---
    Tweak("Приватность", "Отключить рекламный ID", "Приложения не получают персональный рекламный идентификатор",
          HKCU, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", DWORD, 0, 1),
    Tweak("Приватность", "Отключить рекомендации в «Пуске»", "Меньше рекламы и предложенных приложений",
          HKCU, ADV, "Start_IrisRecommendations", DWORD, 0, 1),
    Tweak("Приватность", "Отключить советы и рекламу Windows", "Предложения на экране блокировки и в уведомлениях",
          HKCU, CDM, "SubscribedContent-338388Enabled", DWORD, 0, 1),
    Tweak("Приватность", "Отключить Bing в поиске «Пуск»", "Поиск ищет только на вашем ПК",
          HKCU, r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", DWORD, 1, None),
    Tweak("Приватность", "Минимум телеметрии (нужен админ)", "Ограничивает отправку диагностических данных",
          HKLM, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", DWORD, 0, None, admin=True),
    # --- Производительность ---
    Tweak("Производительность", "Отключить анимацию окон", "Окна сворачиваются мгновенно",
          HKCU, r"Control Panel\Desktop\WindowMetrics", "MinAnimate", SZ, "0", "1"),
    Tweak("Производительность", "Убрать задержку меню", "Меню открываются без паузы",
          HKCU, r"Control Panel\Desktop", "MenuShowDelay", SZ, "0", "400"),
]


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _open(hive, path, write=False):
    access = winreg.KEY_WOW64_64KEY | (winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY if write else winreg.KEY_READ)
    return winreg.OpenKey(hive, path, 0, access)


def is_on(t: Tweak) -> bool:
    try:
        if t.special == "keyexists":
            _open(t.hive, t.path + r"\InprocServer32").Close()
            return True
        with _open(t.hive, t.path) as k:
            val, _ = winreg.QueryValueEx(k, t.name)
        return str(val) == str(t.on)
    except OSError:
        return False


def set_state(t: Tweak, enable: bool) -> None:
    if t.special == "keyexists":
        sub = t.path + r"\InprocServer32"
        if enable:
            with winreg.CreateKeyEx(t.hive, sub, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                winreg.SetValueEx(k, "", 0, SZ, "")
        else:
            for p in (sub, t.path):
                try:
                    winreg.DeleteKeyEx(t.hive, p, winreg.KEY_WOW64_64KEY, 0)
                except FileNotFoundError:
                    pass
        return
    value = t.on if enable else t.off
    with winreg.CreateKeyEx(t.hive, t.path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
        if value is None:
            try:
                winreg.DeleteValue(k, t.name)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(k, t.name, 0, t.kind, value)


# ---------- Действия-кнопки ----------
def restart_explorer():
    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True)
    subprocess.Popen(["explorer.exe"])


def clean_temp() -> str:
    freed, errors = 0, 0
    for folder in {tempfile.gettempdir(), os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Temp")}:
        if not os.path.isdir(folder):
            continue
        for entry in os.scandir(folder):
            try:
                size = entry.stat().st_size if entry.is_file() else 0
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path)
                else:
                    os.remove(entry.path)
                freed += size
            except OSError:
                errors += 1
    return f"Освобождено около {freed / 1024 / 1024:.1f} МБ (пропущено занятых файлов: {errors})"


def power_plan(guid: str) -> bool:
    r = subprocess.run(["powercfg", "/setactive", guid], capture_output=True)
    return r.returncode == 0


def restore_point() -> bool:
    cmd = 'Checkpoint-Computer -Description "WinTweaker" -RestorePointType MODIFY_SETTINGS'
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)
    return r.returncode == 0


# ---------- Интерфейс ----------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("WinTweaker")
        self.geometry("760x620")
        self.minsize(640, 520)

        admin_txt = "запущено от администратора" if is_admin() else "без прав администратора (часть твиков недоступна)"
        ctk.CTkLabel(self, text=f"WinTweaker  |  {admin_txt}", anchor="w").pack(fill="x", padx=16, pady=(12, 0))

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=8)
        cats = list(dict.fromkeys(t.category for t in TWEAKS)) + ["Инструменты"]
        for c in cats:
            tabs.add(c)

        for t in TWEAKS:
            self._add_tweak(tabs.tab(t.category), t)
        self._add_tools(tabs.tab("Инструменты"))

        self.status = ctk.CTkLabel(self, text="Готово", anchor="w")
        self.status.pack(fill="x", padx=16, pady=(0, 10))

    def _add_tweak(self, parent, t: Tweak):
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", padx=6, pady=4)
        var = ctk.BooleanVar(value=is_on(t))
        sw = ctk.CTkSwitch(row, text=t.title, variable=var, font=ctk.CTkFont(weight="bold"))
        sw.configure(command=lambda: self._toggle(t, var))
        sw.pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(row, text=t.desc, text_color="gray70").pack(anchor="w", padx=48, pady=(0, 8))

    def _toggle(self, t: Tweak, var: ctk.BooleanVar):
        want = var.get()
        if t.admin and not is_admin():
            mb.showwarning("Нужны права", "Запустите программу от имени администратора.")
            var.set(not want)
            return
        try:
            set_state(t, want)
            self.status.configure(text=f"{'Включено' if want else 'Выключено'}: {t.title}. "
                                       "Если не видно эффекта, перезапустите Проводник (вкладка «Инструменты»).")
        except OSError as e:
            mb.showerror("Ошибка", str(e))
            var.set(not want)

    def _add_tools(self, parent):
        def btn(text, fn):
            ctk.CTkButton(parent, text=text, command=fn, height=36).pack(fill="x", padx=12, pady=6)

        btn("Перезапустить Проводник", lambda: (restart_explorer(), self.status.configure(text="Проводник перезапущен")))
        btn("Очистить временные файлы", lambda: self.status.configure(text=clean_temp()))
        btn("План питания: высокая производительность",
            lambda: self._report(power_plan("8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"), "План питания изменён"))
        btn("План питания: сбалансированный",
            lambda: self._report(power_plan("381b4222-f694-41f0-9685-ff5bb260df2e"), "План питания изменён"))
        btn("Создать точку восстановления (нужен админ)",
            lambda: self._report(restore_point(), "Точка восстановления создана"))

    def _report(self, ok: bool, msg: str):
        self.status.configure(text=msg if ok else "Не удалось выполнить (проверьте права администратора)")


if __name__ == "__main__":
    App().mainloop()
