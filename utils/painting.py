from PySide6.QtCore import (
    Qt,
    QUrl,
    QSize,
    QDateTime,
    QThread,
    QMetaObject,
    Qt as QtNs,
    Q_ARG,
    Slot,
    QTimer,
    QObject,
    Signal,
)
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

# 确保导入
import pyqtgraph as pg  # 确保已安装 PyQtGraph
from PySide6.QtWidgets import QWidget as _QW
from PySide6.QtQuick import QQuickView


def svg_to_icon(self, svg_path, size):
    """将 SVG 文件渲染为 QIcon"""
    renderer = QSvgRenderer(svg_path)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
