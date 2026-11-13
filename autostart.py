"""Only user-level login entries; invoked after explicit settings change."""

import sys
import plistlib
from pathlib import Path


def command():
    return (
        [sys.executable]
        if getattr(sys, "frozen", False)
        else [sys.executable, str(Path(__file__).with_name("main.py").resolve())]
    )


def set_enabled(enabled):
    args = command()
    if sys.platform == "darwin":
        path = Path.home() / "Library/LaunchAgents/jp.nictanalogclock.user.plist"
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as stream:
                plistlib.dump(
                    {
                        "Label": "jp.nictanalogclock.user",
                        "ProgramArguments": args,
                        "RunAtLoad": True,
                    },
                    stream,
                )
        else:
            path.unlink(missing_ok=True)
    elif sys.platform == "win32":
        import winreg
        import subprocess

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    "NICTAnalogClock",
                    0,
                    winreg.REG_SZ,
                    subprocess.list2cmdline(args),
                )
            else:
                try:
                    winreg.DeleteValue(key, "NICTAnalogClock")
                except FileNotFoundError:
                    pass
    elif enabled:
        raise OSError("自動起動はmacOSとWindowsで利用できます")
