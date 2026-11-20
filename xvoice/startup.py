"""Per-user 'Start with Windows' toggle.

The value lives in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
That key is the current user's, so no administrator rights are required.
Turning the setting off removes the value. The default is off.
"""

import subprocess
import sys
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "x-voice"


class RunKeyStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class MemoryRunKey:
    """In-memory stand-in for the HKCU Run key. Tests use this."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def launch_command(executable: str, args: list[str] | None = None) -> str:
    """Quote an executable and optional arguments the way Windows Run expects."""
    parts = [executable, *(args or [])]
    if not executable.strip():
        raise ValueError("The program path is empty.")
    return subprocess.list2cmdline(parts)


def current_launch_command() -> str:
    """Command that starts this copy of x-voice again."""
    if getattr(sys, "frozen", False):
        return launch_command(sys.executable)
    return launch_command(sys.executable, ["-m", "xvoice"])


def apply_startup(enabled: bool, command: str, store: RunKeyStore) -> None:
    """Write or remove the per-user Run value. Default off means remove it."""
    if not enabled:
        store.delete(VALUE_NAME)
        return
    if not command.strip():
        raise ValueError("The startup command is empty.")
    store.set(VALUE_NAME, command)


def startup_is_enabled(store: RunKeyStore) -> bool:
    value = store.get(VALUE_NAME)
    return bool(value and value.strip())


def apply_user_startup(enabled: bool, command: str | None = None) -> None:
    """Apply the toggle on this PC. Off is a no-op on other systems."""
    if sys.platform != "win32":
        if enabled:
            raise OSError("Start with Windows only works on Windows.")
        return
    apply_startup(enabled, command or current_launch_command(), windows_run_key())


def windows_run_key() -> RunKeyStore:
    """HKCU Run key. Imported only when the Windows app actually toggles startup."""
    import winreg

    class _WinregRunKey:
        def get(self, name: str) -> str | None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
                    value, _kind = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                return None
            except OSError:
                return None
            return str(value)

        def set(self, name: str, value: str) -> None:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

        def delete(self, name: str) -> None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, name)
            except FileNotFoundError:
                return
            except OSError as exc:
                if getattr(exc, "winerror", None) == 2:
                    return
                raise

    return _WinregRunKey()
