from dataclasses import replace
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QPushButton,
    QMessageBox,
)


class SettingsWindow(QDialog):
    applied = Signal(object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("設定 — NICT Analog Clock")
        form = QFormLayout(self)
        self.controls = {}
        labels = {
            "server": "NTPサーバー",
            "interval": "同期間隔（秒・60以上）",
            "theme": "デザイン",
            "seconds": "秒針を表示",
            "sweep": "スイープ秒針",
            "digital": "デジタル表示",
            "milliseconds": "ミリ秒を表示",
            "size": "時計サイズ（px）",
            "transparent": "背景透過",
            "opacity": "ウィンドウ透過度",
            "on_top": "常に最前面",
            "frameless": "枠なし",
            "timezone": "タイムゾーン",
            "autostart": "ログイン時に自動起動",
        }
        for name, label in labels.items():
            value = getattr(config, name)
            if name == "theme":
                control = QComboBox()
                control.addItems(["Classic", "Dark", "Minimal"])
                control.setCurrentText(value)
            elif isinstance(value, bool):
                control = QCheckBox()
                control.setChecked(value)
            elif isinstance(value, int):
                control = QSpinBox()
                control.setRange(
                    60 if name == "interval" else 180,
                    86400 if name == "interval" else 1600,
                )
                control.setValue(value)
            elif isinstance(value, float):
                control = QDoubleSpinBox()
                control.setRange(0.2, 1)
                control.setSingleStep(0.05)
                control.setValue(value)
            else:
                control = QLineEdit(value)
            self.controls[name] = control
            form.addRow(label, control)
        hint = QLabel(
            "背景透過中は枠なしになります。\n文字盤の外側を透過し、文字盤は読みやすく保ちます。"
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        for name in ("frameless", "transparent"):
            self.controls[name].toggled.connect(lambda _checked: self.apply())
        button = QPushButton("適用")
        button.clicked.connect(self.apply)
        form.addRow(button)

    def apply(self):
        changes = {}
        for name, c in self.controls.items():
            if isinstance(c, QCheckBox):
                value = c.isChecked()
            elif isinstance(c, QComboBox):
                value = c.currentText()
            elif isinstance(c, (QSpinBox, QDoubleSpinBox)):
                value = c.value()
            else:
                value = c.text().strip()
            changes[name] = value
        try:
            config = replace(self.config, **changes).validate()
        except Exception:
            QMessageBox.warning(
                self, "設定エラー", "設定値またはタイムゾーン名を確認してください。"
            )
            return
        self.applied.emit(config)
