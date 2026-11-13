import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from dataclasses import replace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from clock_widget import ClockWidget
from time_service import TimeService
from config import Config


def test_render_all_designs():
    app = QApplication.instance() or QApplication([])
    for theme in ("Classic", "Dark", "Minimal"):
        for transparent in (False, True):
            widget = ClockWidget(
                TimeService(), replace(Config(), theme=theme, transparent=transparent)
            )
            widget.resize(480, 320)
            widget.show()
            app.processEvents()
            image = widget.grab().toImage()
            assert not image.isNull()
            assert widget.cache_key[0] == 320
            widget.close()


def test_window_fallback_and_settings(tmp_path):
    from main import Window

    app = QApplication.instance() or QApplication([])
    with (
        patch("main.load", return_value=Config()),
        patch("main.save"),
        patch("main.query", side_effect=OSError("テスト接続エラー")),
    ):
        window = Window()
        window.show()
        window.sync()
        import time

        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)
            window.tick()
        assert window.state == "接続エラー"
        assert "ローカル時計" in window.status.text()
        assert window.service.now() > 0
        window.settings()
        window.dialog.controls["theme"].setCurrentText("Dark")
        window.dialog.apply()
        assert window.config.theme == "Dark"
        window.close()
        window.dialog.close()


def test_settings_clicks_and_native_mode_switches():
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from main import Window

    app = QApplication.instance() or QApplication([])
    with (
        patch("main.load", return_value=Config()),
        patch("main.save"),
        patch.object(Window, "sync"),
    ):
        window = Window()
        window.show()
        window.settings()
        app.processEvents()
        checkbox = window.dialog.controls["frameless"]
        # Reproduce a window manager accepting startSystemMove: dialog clicks
        # must not be consumed by the main window's application event filter.
        with patch.object(
            window.windowHandle(), "startSystemMove", return_value=True
        ) as move:
            QTest.mouseClick(
                checkbox,
                Qt.MouseButton.LeftButton,
                pos=QPoint(8, checkbox.height() // 2),
            )
            app.processEvents()
            assert checkbox.isChecked()
            assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
            move.assert_not_called()
        QTest.mouseClick(
            checkbox, Qt.MouseButton.LeftButton, pos=QPoint(8, checkbox.height() // 2)
        )
        app.processEvents()
        assert not window.windowFlags() & Qt.WindowType.FramelessWindowHint
        transparent = window.dialog.controls["transparent"]
        QTest.mouseClick(
            transparent,
            Qt.MouseButton.LeftButton,
            pos=QPoint(8, transparent.height() // 2),
        )
        app.processEvents()
        assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.isVisible() and window.dialog.isVisible()
        QTest.mouseClick(
            transparent,
            Qt.MouseButton.LeftButton,
            pos=QPoint(8, transparent.height() // 2),
        )
        app.processEvents()
        assert not window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert not window.windowFlags() & Qt.WindowType.FramelessWindowHint
        window.dialog.close()
        window.close()


def test_transparent_dial_keeps_contrast():
    app = QApplication.instance() or QApplication([])
    for theme in ("Classic", "Dark", "Minimal"):
        widget = ClockWidget(
            TimeService(), replace(Config(), theme=theme, transparent=True)
        )
        widget.resize(320, 320)
        widget.show()
        app.processEvents()
        widget.grab()
        face = widget.face.toImage()
        ratio = widget.devicePixelRatioF()
        assert face.pixelColor(round(160 * ratio), round(90 * ratio)).alpha() >= 235
        assert face.pixelColor(0, 0).alpha() == 0
        widget.close()
