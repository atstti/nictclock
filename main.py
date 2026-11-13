import sys
from pathlib import Path
import time
from concurrent.futures import Future
import threading
from dataclasses import replace
from PySide6.QtCore import Qt, QTimer, QByteArray, QEvent
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QMenu,
    QSizeGrip,
    QHBoxLayout,
    QMessageBox,
    QToolButton,
)
from icons import tool_icon
from clock_widget import ClockWidget
from time_service import TimeService
from config import Config, load, save
from settings_window import SettingsWindow
from autostart import set_enabled
from ntp_client import query, RateLimitError


class Window(QWidget):
    def __init__(self, smoke_test=False):
        super().__init__()
        self.smoke_test = smoke_test
        self.config = Config() if smoke_test else load()
        self.service = TimeService()
        self.future = None
        self.failures = 0
        self.last_attempt = -1e9
        self.due = 0
        self.state = "未同期"
        self.error = ""
        self.drag = None
        self.blocked_until = 0
        self.uncertain = False
        self.last_tick = time.monotonic()
        self.last_wall = time.time()
        self.setWindowTitle("NICT Analog Clock")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.clock = ClockWidget(self.service, self.config)
        layout.addWidget(self.clock, 1)
        self.digital = QLabel()
        self.digital.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.digital)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.status)
        self.toolbar = QWidget()
        row = QHBoxLayout(self.toolbar)
        row.setContentsMargins(0, 0, 0, 0)
        self.sync_button = QToolButton()
        self.sync_button.setToolTip("今すぐ同期")
        self.sync_button.setAccessibleName("今すぐ同期")
        self.sync_button.setAutoRaise(True)
        self.sync_button.clicked.connect(self.sync)
        row.addStretch()
        row.addWidget(self.sync_button)
        self.settings_button = QToolButton()
        self.settings_button.setToolTip("設定")
        self.settings_button.setAccessibleName("設定")
        self.settings_button.setAutoRaise(True)
        self.settings_button.clicked.connect(self.settings)
        row.addStretch()
        row.addWidget(self.settings_button)
        row.addStretch()
        self.grip = QSizeGrip(self)
        row.addWidget(self.grip)
        layout.addWidget(self.toolbar)
        self.apply_visual()
        self.resize(self.config.size, self.config.size)
        if self.config.geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.config.geometry.encode()))
        self.ensure_visible()
        app = QApplication.instance()
        app.installEventFilter(self)
        app.applicationStateChanged.connect(
            lambda state: (
                self.wake() if state == Qt.ApplicationState.ApplicationActive else None
            )
        )
        app.screenAdded.connect(lambda _: self.ensure_visible())
        app.screenRemoved.connect(lambda _: QTimer.singleShot(0, self.ensure_visible))
        for screen in app.screens():
            screen.availableGeometryChanged.connect(lambda _: self.ensure_visible())
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        QTimer.singleShot(0, self.sync)

    def ensure_visible(self):
        screens = QGuiApplication.screens()
        if not screens:
            return
        if not any(
            s.availableGeometry().intersects(self.frameGeometry()) for s in screens
        ):
            self.move(screens[0].availableGeometry().topLeft())
        screen = self.screen() or screens[0]
        area = screen.availableGeometry()
        self.resize(min(self.width(), area.width()), min(self.height(), area.height()))
        self.move(
            max(area.left(), min(self.x(), area.right() - self.width() + 1)),
            max(area.top(), min(self.y(), area.bottom() - self.height() + 1)),
        )

    def apply_visual(self):
        visible = self.isVisible()
        geometry = self.geometry()
        flags = self.windowFlags()
        flags = (
            (flags | Qt.WindowType.WindowStaysOnTopHint)
            if self.config.on_top
            else (flags & ~Qt.WindowType.WindowStaysOnTopHint)
        )
        frameless = self.config.frameless or self.config.transparent
        flags = (
            (flags | Qt.WindowType.FramelessWindowHint)
            if frameless
            else (flags & ~Qt.WindowType.FramelessWindowHint)
        )
        transparent_changed = (
            self.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            != self.config.transparent
        )
        native_changed = flags != self.windowFlags() or transparent_changed
        if native_changed:
            # macOS/Windows need a fresh platform window when changing translucency.
            self.hide()
            if self.windowHandle() is not None:
                self.destroy(True, False)
            self.setWindowFlags(flags)
            self.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground, self.config.transparent
            )
            self.setAttribute(
                Qt.WidgetAttribute.WA_NoSystemBackground, self.config.transparent
            )
        self.setWindowOpacity(self.config.opacity)
        dark = self.config.theme == "Dark"
        ink = "#f0f2f5" if dark else "#252c36"
        self.sync_button.setIcon(tool_icon("sync", ink, self.devicePixelRatioF()))
        self.settings_button.setIcon(
            tool_icon("settings", ink, self.devicePixelRatioF())
        )
        panel = "rgba(39,45,53,225)" if dark else "rgba(252,251,247,235)"
        self.setStyleSheet(f"""
            QLabel {{ color: {ink}; }}
            QToolButton {{ color: {ink}; background: {panel}; border: 1px solid rgba(128,138,150,65);
                border-radius: 14px; min-width: 28px; max-width: 28px; min-height: 28px;
                max-height: 28px; padding: 0px; font-size: 19px; }}
            QToolButton:hover {{ border: 1px solid #df3d4b; }}
            QToolButton:pressed {{ background: rgba(128,138,150,150); }}
            QToolButton:disabled {{ color: #888888; border-color: rgba(128,138,150,35); }}
        """)
        self.digital.setStyleSheet("background: transparent;")
        self.status.setStyleSheet("background: transparent; font-size: 10px;")
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            Qt.GlobalColor.darkGray
            if self.config.theme == "Dark"
            else Qt.GlobalColor.white,
        )
        self.setPalette(palette)
        self.setAutoFillBackground(not self.config.transparent)
        self.digital.setVisible(self.config.digital and not self.config.clock_only)
        self.status.setVisible(self.config.show_status and not self.config.clock_only)
        self.toolbar.setVisible(
            self.config.show_controls and not self.config.clock_only
        )
        self.clock.config = self.config
        self.clock.cache_key = None
        if native_changed:
            self.setGeometry(geometry)
        if visible:
            self.show()
            self.setGeometry(geometry)

    def sync(self):
        if self.smoke_test:
            return
        if (
            self.future is not None
            or time.monotonic() - self.last_attempt < 60
            or time.monotonic() < self.blocked_until
        ):
            return
        self.last_attempt = time.monotonic()
        self.state = "同期中"
        self.error = ""
        future = Future()
        self.future = future
        server = self.config.server

        def run():
            try:
                future.set_result(query(server))
            except Exception as exc:
                future.set_exception(exc)

        threading.Thread(target=run, daemon=True, name="NTP").start()

    def wake(self):
        if time.monotonic() - self.last_attempt >= 60:
            self.due = 0

    def tick(self):
        mono, wall = time.monotonic(), time.time()
        # Handles platforms where monotonic either includes or excludes suspend time.
        if (
            mono - self.last_tick > 5
            or abs((wall - self.last_wall) - (mono - self.last_tick)) > 5
        ):
            self.uncertain = True
            self.wake()
        self.last_tick, self.last_wall = mono, wall
        if self.future is not None and self.future.done():
            try:
                self.service.synchronize(self.future.result())
                self.uncertain = False
                self.failures = 0
                self.state = "同期済み"
                self.error = ""
                self.due = mono + self.config.interval
            except Exception as exc:
                self.failures += 1
                if isinstance(exc, RateLimitError):
                    self.blocked_until = mono + 900
                from PySide6.QtNetwork import QNetworkInformation

                info = QNetworkInformation.instance()
                offline = (
                    info is not None
                    and info.reachability()
                    == QNetworkInformation.Reachability.Disconnected
                )
                self.state = "オフライン" if offline else "接続エラー"
                self.error = str(exc)
                self.due = mono + (
                    900
                    if isinstance(exc, RateLimitError)
                    else min(900, 60 * 2 ** min(self.failures - 1, 4))
                )
            self.future = None
        if self.future is None and mono >= self.due:
            self.sync()
        self.sync_button.setEnabled(
            self.future is None
            and mono - self.last_attempt >= 60
            and mono >= self.blocked_until
        )
        dt = self.service.local(self.config.timezone)
        text = dt.strftime("%H:%M:%S") + (
            f".{dt.microsecond // 1000:03d}" if self.config.milliseconds else ""
        )
        self.digital.setText(
            f"{text}\n{dt:%Y/%m/%d} {'月火水木金土日'[dt.weekday()]}曜日  {dt.tzname()}"
        )
        sample = self.service.sample
        age = self.service.age()
        stale = self.uncertain or (
            age is not None and age > max(1800, self.config.interval * 2)
        )
        details = f"NTP: {self.state}" + ("（精度低下の可能性）" if stale else "")
        details += f"\nServer: {self.config.server}"
        if sample:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            last = datetime.fromtimestamp(sample.utc, ZoneInfo(self.config.timezone))
            details += f"\nOffset: {sample.offset * 1000:+.1f} ms  RTT: {sample.rtt * 1000:.1f} ms\nLast Sync: {last:%m/%d %H:%M:%S}"
            if sample.server != self.config.server:
                details += f"（前回: {sample.server}）"
        else:
            details += "\n未同期：ローカル時計で暫定動作"
        if self.error:
            details += "\n" + self.error
        self.status.setText(details)
        self.status.setToolTip(
            (self.error + "\n" if self.error else "")
            + "Offset・RTTは測定値であり、絶対精度を保証しません。"
        )
        self.clock.update()

    def settings(self):
        if not hasattr(self, "dialog") or not self.dialog.isVisible():
            self.dialog = SettingsWindow(self.config, self)
            self.dialog.applied.connect(self.apply_config)
        self.dialog.show()
        self.dialog.raise_()

    def apply_config(self, new):
        try:
            if new.autostart != self.config.autostart:
                set_enabled(new.autostart)
            save(new)
        except OSError as exc:
            QMessageBox.warning(
                self, "保存エラー", f"設定を保存できませんでした。\n{exc}"
            )
            return
        old = self.config
        self.config = new
        self.dialog.config = new
        self.apply_visual()
        if new.size != old.size:
            self.resize(new.size, new.size)
        if new.server != old.server or new.interval != old.interval:
            self.due = 0

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("今すぐ同期", self.sync)
        menu.addAction("設定", self.settings)
        clock_only = menu.addAction("文字盤だけ")
        clock_only.setCheckable(True)
        clock_only.setChecked(self.config.clock_only)
        clock_only.triggered.connect(self.toggle_clock_only)
        action = menu.addAction("常に最前面")
        action.setCheckable(True)
        action.setChecked(self.config.on_top)
        action.triggered.connect(self.toggle_top)
        menu.addAction("最小化", self.showMinimized)
        menu.addAction("終了", self.close)
        menu.exec(event.globalPos())

    def toggle_clock_only(self, checked):
        self.config = replace(self.config, clock_only=checked)
        self.apply_visual()
        if hasattr(self, "dialog"):
            self.dialog.config = self.config
            checkbox = self.dialog.controls["clock_only"]
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)
        try:
            save(self.config)
        except OSError:
            QMessageBox.warning(self, "保存エラー", "表示設定を保存できませんでした。")

    def toggle_top(self, checked):
        self.config = replace(self.config, on_top=checked)
        self.apply_visual()

    def eventFilter(self, obj, event):
        # Settings is a separate top-level window, even though it has this parent.
        # Never steal mouse presses from its checkboxes, fields or other controls.
        if obj is self or (
            isinstance(obj, (ClockWidget, QLabel)) and obj.window() is self
        ):
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                if self.windowHandle() and self.windowHandle().startSystemMove():
                    return True
                self.drag = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
            elif event.type() == QEvent.Type.MouseMove and self.drag is not None:
                self.move(event.globalPosition().toPoint() - self.drag)
                return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self.drag = None
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.timer.stop()
        self.config.geometry = bytes(self.saveGeometry().toBase64()).decode()
        if not self.smoke_test:
            try:
                save(self.config)
            except OSError:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    assets = Path(__file__).resolve().parent / "assets"
    icon_path = assets / "app-icon.png"
    if not icon_path.exists():
        icon_path = assets / "icon-master.webp"
    icon = QIcon(str(icon_path))
    if icon.isNull() or icon.pixmap(32, 32).isNull():
        raise RuntimeError("アプリのアイコンを読み込めませんでした")
    app.setWindowIcon(icon)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "NICTAnalogClock.Desktop"
        )
    app.setApplicationName("NICT Analog Clock")
    app.setOrganizationName("NICTAnalogClock")
    from PySide6.QtNetwork import QNetworkInformation

    QNetworkInformation.loadDefaultBackend()
    smoke_test = "--smoke-test" in sys.argv
    window = Window(smoke_test=smoke_test)
    window.show()
    if smoke_test:
        QTimer.singleShot(1000, window.close)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
