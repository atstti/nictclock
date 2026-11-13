"""Small vector icons, rendered at the display's pixel density."""

import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def tool_icon(kind, color, ratio=1.0):
    pixmap = QPixmap(round(24 * ratio), round(24 * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(
        QPen(
            QColor(color),
            1.8,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    if kind == "settings":
        for i in range(8):
            angle = math.radians(i * 45)
            painter.drawLine(
                QPointF(12 + 7 * math.cos(angle), 12 + 7 * math.sin(angle)),
                QPointF(12 + 9 * math.cos(angle), 12 + 9 * math.sin(angle)),
            )
        painter.drawEllipse(QPointF(12, 12), 6, 6)
        painter.drawEllipse(QPointF(12, 12), 2, 2)
    else:
        path = QPainterPath()
        path.arcMoveTo(QRectF(5, 5, 14, 14), 45)
        path.arcTo(QRectF(5, 5, 14, 14), 45, 285)
        painter.drawPath(path)
        painter.drawPolyline([QPointF(19, 11), QPointF(18, 16), QPointF(13, 15)])
    painter.end()
    return QIcon(pixmap)
