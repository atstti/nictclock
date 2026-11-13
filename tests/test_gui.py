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
