import math
from PySide6.QtCore import Qt, QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPixmap
from PySide6.QtWidgets import QWidget
from time_service import hand_angles


class ClockWidget(QWidget):
    def __init__(self, service, config, parent=None):
        super().__init__(parent)
        self.service, self.config = service, config
        self.cache_key = None
        self.setMinimumSize(140, 140)

    def sizeHint(self):
        return QSize(320, 320)

    def paintEvent(self, event):
        side = min(self.width(), self.height())
        ratio = self.devicePixelRatioF()
        key = (side, ratio, self.config.theme, self.config.transparent)
        if self.cache_key != key:
            self.cache_key = key
            self.face = QPixmap(round(side * ratio), round(side * ratio))
            self.face.setDevicePixelRatio(ratio)
            self.face.fill(Qt.GlobalColor.transparent)
            p = QPainter(self.face)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.scale(side / 320, side / 320)
            p.translate(160, 160)
            dark = self.config.theme == "Dark"
            self.ink = QColor("#f0f2f5" if dark else "#252c36")
            p.setPen(QPen(QColor("#657080"), 1))
            p.setBrush(
                Qt.BrushStyle.NoBrush
                if self.config.transparent
                else QColor("#272d35" if dark else "#fcfbf7")
            )
            p.drawEllipse(QPointF(0, 0), 153, 153)
            minimal = self.config.theme == "Minimal"
            for i in range(60):
                a = math.radians(i * 6)
                outer, inner = 141, (130 if i % 5 == 0 else 136)
                p.setPen(
                    QPen(
                        self.ink,
                        (1 if minimal else 3) if i % 5 == 0 else 1,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                p.drawLine(
                    QPointF(math.sin(a) * inner, -math.cos(a) * inner),
                    QPointF(math.sin(a) * outer, -math.cos(a) * outer),
                )
            if not minimal:
                p.setPen(self.ink)
                p.setFont(QFont("Sans Serif", 17))
                for i in range(1, 13):
                    a = math.radians(i * 30)
                    p.drawText(
                        QRectF(math.sin(a) * 111 - 20, -math.cos(a) * 111 - 17, 40, 34),
                        Qt.AlignmentFlag.AlignCenter,
                        str(i),
                    )
            p.end()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate((self.width() - side) / 2, (self.height() - side) / 2)
        p.drawPixmap(0, 0, self.face)
        p.scale(side / 320, side / 320)
        p.translate(160, 160)
        dt = self.service.local(self.config.timezone)
        angles = hand_angles(
            dt.hour, dt.minute, dt.second, dt.microsecond, self.config.sweep
        )
        minimal = self.config.theme == "Minimal"
        for angle, length, width, color in [
            (angles[0], 76, 4 if minimal else 7, self.ink),
            (angles[1], 109, 2 if minimal else 4, self.ink),
        ] + ([(angles[2], 125, 1.8, QColor("#df3d4b"))] if self.config.seconds else []):
            p.save()
            p.rotate(angle)
            p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(
                QPointF(0, 13 if color == QColor("#df3d4b") else 4), QPointF(0, -length)
            )
            p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#df3d4b") if self.config.seconds else self.ink)
        p.drawEllipse(QPointF(), 4, 4)
