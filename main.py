import sys
import time
from concurrent.futures import Future
import threading
from dataclasses import replace
from PySide6.QtCore import Qt, QTimer, QByteArray, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QMenu,
    QSizeGrip,
    QHBoxLayout,
    QMessageBox,
)
from clock_widget import ClockWidget
from time_service import TimeService
from config import load, save
from settings_window import SettingsWindow
from autostart import set_enabled
from ntp_client import query, RateLimitError


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.config = load()
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
        row = QHBoxLayout()
        self.sync_button = QPushButton("同期")
        self.sync_button.clicked.connect(self.sync)
        row.addWidget(self.sync_button)
        settings = QPushButton("設定")
        settings.clicked.connect(self.settings)
        row.addWidget(settings)
        self.grip = QSizeGrip(self)
        row.addWidget(self.grip)
        layout.addLayout(row)
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
        position = self.pos()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.config.on_top)
        self.setWindowFlag(
            Qt.WindowType.FramelessWindowHint,
            self.config.frameless or self.config.transparent,
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, self.config.transparent
        )
        self.setWindowOpacity(self.config.opacity)
        self.setStyleSheet(
            "QLabel { color: %s; }"
            % ("#eeeeee" if self.config.theme == "Dark" else "#30343b")
        )
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            Qt.GlobalColor.darkGray
            if self.config.theme == "Dark"
            else Qt.GlobalColor.white,
        )
        self.setPalette(palette)
        self.setAutoFillBackground(not self.config.transparent)
        self.digital.setVisible(self.config.digital)
        self.clock.config = self.config
        self.clock.cache_key = None
        if visible:
            self.show()
            self.move(position)

    def sync(self):
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
        action = menu.addAction("常に最前面")
        action.setCheckable(True)
        action.setChecked(self.config.on_top)
        action.triggered.connect(self.toggle_top)
        menu.addAction("最小化", self.showMinimized)
        menu.addAction("終了", self.close)
        menu.exec(event.globalPos())

    def toggle_top(self, checked):
        self.config = replace(self.config, on_top=checked)
        self.apply_visual()

    def eventFilter(self, obj, event):
        if obj is self or (isinstance(obj, QWidget) and self.isAncestorOf(obj)):
            if isinstance(obj, (QPushButton, QSizeGrip)):
                return super().eventFilter(obj, event)
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
        try:
            save(self.config)
        except OSError:
            pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NICT Analog Clock")
    app.setOrganizationName("NICTAnalogClock")
    from PySide6.QtNetwork import QNetworkInformation

    QNetworkInformation.loadDefaultBackend()
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
