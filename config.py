import json
import os
import sys
import tempfile
from pathlib import Path
from dataclasses import dataclass, asdict, fields
from zoneinfo import ZoneInfo


@dataclass
class Config:
    server: str = "ntp.nict.jp"
    interval: int = 900
    theme: str = "Classic"
    seconds: bool = True
    sweep: bool = True
    clock_only: bool = False
    show_status: bool = True
    show_controls: bool = True
    digital: bool = True
    milliseconds: bool = False
    size: int = 320
    transparent: bool = False
    opacity: float = 1.0
    on_top: bool = False
    frameless: bool = False
    timezone: str = "Asia/Tokyo"
    autostart: bool = False
    geometry: str = ""

    def validate(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if field.type is float:
                valid = type(value) in (int, float)
            else:
                valid = type(value) is field.type
            if not valid:
                raise ValueError("設定の型が不正です")
        self.server = self.server.strip()
        if (
            not self.server
            or len(self.server) > 253
            or any(c.isspace() for c in self.server)
        ):
            raise ValueError("NTPサーバーを確認してください")
        ZoneInfo(self.timezone)
        if not 60 <= self.interval <= 86400 or not 180 <= self.size <= 1600:
            raise ValueError("同期間隔またはサイズが範囲外です")
        if not 0.2 <= self.opacity <= 1 or self.theme not in (
            "Classic",
            "Dark",
            "Minimal",
        ):
            raise ValueError("表示設定が不正です")
        for field in fields(self):
            if field.type is bool and type(getattr(self, field.name)) is not bool:
                raise ValueError("設定の型が不正です")
        return self


def config_path():
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "NICTAnalogClock" / "settings.json"


def load(path=None):
    try:
        data = json.loads((path or config_path()).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return Config()
        return Config(
            **{k: v for k, v in data.items() if k in {f.name for f in fields(Config)}}
        ).validate()
    except (OSError, ValueError, TypeError, KeyError):
        return Config()


def save(config, path=None):
    config.validate()
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(asdict(config), stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
