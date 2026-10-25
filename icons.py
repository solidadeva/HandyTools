"""Original code-native vector artwork for the Handy family."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QIcon, QIconEngine, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

ART = {
 'download': '<path d="M32 16v25m-10-10 10 10 10-10M17 42v7a3 3 0 0 0 3 3h24a3 3 0 0 0 3-3v-7"/>',
 'convert': '<path d="M16 24h32m-9-9 9 9-9 9M48 42H16m9-9-9 9 9 9"/>',
 'donate': '<path d="M32 48 16 32c-12-13 5-27 16-13 11-14 28 0 16 13Z"/>',
 'settings': '<path d="m28 9-1 6-5 3-6-2-6 10 5 4v5l-5 4 6 10 6-2 5 3 1 6h9l1-6 5-3 6 2 6-10-5-4v-5l5-4-6-10-6 2-5-3-1-6Z"/><circle cx="32" cy="32" r="8"/>',
 'folder': '<path d="M9 23v-6a4 4 0 0 1 4-4h13l6 7h19a4 4 0 0 1 4 4v23a4 4 0 0 1-4 4H13a4 4 0 0 1-4-4V23h46"/>',
 'file': '<path d="M35 9H17a4 4 0 0 0-4 4v38a4 4 0 0 0 4 4h30a4 4 0 0 0 4-4V25L35 9v16h16M24 36h16M24 44h11"/>',
 'details': '<rect x="10" y="11" width="44" height="42" rx="7"/><path d="M20 24h24M20 32h24M20 40h14"/>',
 'refresh': '<path d="M51 25A20 20 0 0 0 16 17l-5 6m0-13v13h13M13 39a20 20 0 0 0 35 8l5-6m0 13V41H40"/>',
 'chevron-down': '<path d="m19 26 13 13 13-13"/>',
 'chevron-up': '<path d="m19 38 13-13 13 13"/>',
 'check': '<path d="m16 33 10 10 23-24"/>',
 'upload': '<path d="M32 44V15m-10 10 10-10 10 10M13 39v11a3 3 0 0 0 3 3h32a3 3 0 0 0 3-3V39"/>',
 'sun': '<circle cx="32" cy="32" r="10"/><path d="M32 8v6m0 36v6M8 32h6m36 0h6M15 15l4 4m26 26 4 4M15 49l4-4m26-26 4-4"/>',
 'moon': '<path d="M46 41A22 22 0 0 1 23 12a22 22 0 1 0 23 29Z"/>',
 'close': '<path d="m20 20 24 24m0-24L20 44"/>',
 'minimize': '<path d="M18 32h28"/>',
 'brand': '<rect x="12" y="12" width="16" height="16" rx="4"/><rect x="36" y="12" width="16" height="16" rx="4"/><rect x="12" y="36" width="16" height="16" rx="4"/><rect x="36" y="36" width="16" height="16" rx="4"/>'
}


def svg(name, color='#8e8e93', tile=False):
    background = ''
    if tile:
        top,bottom = ('#5ac8fa','#007aff') if name=='download' else ('#ffcc66','#ff9500') if name=='convert' else ('#9ea5b2','#535d70')
        background = f'''<defs><linearGradient id="tile" x1="0" y1="0" x2="0.25" y2="1"><stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient><linearGradient id="rim" x1="0" y1="0" x2="0" y2="1"><stop stop-color="white" stop-opacity=".55"/><stop offset="1" stop-color="white" stop-opacity=".04"/></linearGradient></defs>
        <path d="M22 2H42C56 2 62 8 62 22V42C62 56 56 62 42 62H22C8 62 2 56 2 42V22C2 8 8 2 22 2Z" fill="url(#tile)"/>
        <path d="M22 2H42C56 2 62 8 62 22V42C62 56 56 62 42 62H22C8 62 2 56 2 42V22C2 8 8 2 22 2Z" fill="none" stroke="url(#rim)" stroke-width=".75"/>'''
        color = '#ffffff'
    stroke = '2.8' if tile else '3.6'
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 64 64">'
            + background + f'<g fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
            + ART[name] + '</g></svg>')


class VectorIconEngine(QIconEngine):
    """Render SVG at the requested physical resolution, including fractional DPI."""
    def __init__(self, name, color, tile):
        super().__init__()
        self.name, self.color, self.tile = name, color, tile

    def availableSizes(self, mode=QIcon.Mode.Normal, state=QIcon.State.Off):
        return [QSize(n,n) for n in (16,24,32,48,64,128,256,512,1024)]

    def clone(self):
        return VectorIconEngine(self.name, self.color, self.tile)

    def paint(self, painter, rect, mode, state):
        painter.save()
        if mode == QIcon.Mode.Disabled:
            painter.setOpacity(painter.opacity() * .38)
        QSvgRenderer(svg(self.name, self.color, self.tile).encode()).render(painter, QRectF(rect))
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        self.paint(painter, pm.rect(), mode, state)
        painter.end()
        return pm

    def scaledPixmap(self, size, mode, state, scale):
        pm = self.pixmap(QSize(round(size.width()*scale), round(size.height()*scale)), mode, state)
        pm.setDevicePixelRatio(scale)
        return pm


def app_icon(name, color='#8e8e93', size=64, tile=False):
    if name == 'genyconnect':
        return QIcon(str(Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets/icons/genyconnect.png'))
    return QIcon(VectorIconEngine(name, color, tile))


def set_button_icon(button, name):
    button.setProperty('iconGlyph', name)
    button.setIconSize(QSize(20, 20))
    button.setAccessibleName(button.text())


def refresh_button_icons(widget, theme):
    from PySide6.QtWidgets import QPushButton
    color = '#f5f5f7' if theme == 'dark' else '#1d1d1f'
    for button in widget.findChildren(QPushButton):
        glyph = button.property('iconGlyph')
        if glyph:
            button.setIcon(app_icon(glyph, '#ffffff' if button.objectName() == 'primary' else color))


def export_assets(destination):
    folder=Path(destination); folder.mkdir(parents=True,exist_ok=True)
    for filename,name,color,tile in [
        ('easy-downloader','download','#007aff',True),
        ('easy-converter','convert','#ff9500',True),
        ('settings','settings','#8e8e93',False),
        ('donate','donate','#8e8e93',False)]:
        (folder/(filename+'.svg')).write_text(svg(name,color,tile),encoding='utf-8')
        app_icon(name,color,1024,tile).pixmap(1024,1024).save(str(folder/(filename+'.png')))


# Keep small built-in control symbols in the same vector family.
from PySide6.QtWidgets import QProxyStyle, QStyle, QComboBox, QStyleOptionComboBox
from PySide6.QtGui import QPalette


class IconStyle(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None):
        glyphs = {QStyle.PrimitiveElement.PE_IndicatorArrowDown: 'chevron-down',
                  QStyle.PrimitiveElement.PE_IndicatorArrowUp: 'chevron-up'}
        if element in glyphs:
            rect = option.rect
            side = min(rect.width(), rect.height(), 18)
            target = QRectF(rect.center().x()-side/2, rect.center().y()-side/2, side, side)
            QSvgRenderer(svg(glyphs[element], option.palette.color(QPalette.ColorRole.Text).name()).encode()).render(painter, target)
        else:
            super().drawPrimitive(element, option, painter, widget)

    def standardIcon(self, standard, option=None, widget=None):
        if standard == QStyle.StandardPixmap.SP_LineEditClearButton:
            color = (widget.palette() if widget else QPalette()).color(QPalette.ColorRole.Text).name()
            return app_icon('close', color)
        return super().standardIcon(standard, option, widget)


class IconComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        rect = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                           QStyle.SubControl.SC_ComboBoxArrow, self)
        target = QRectF(rect.center().x()-9, rect.center().y()-9, 18, 18)
        painter = QPainter(self)
        if not self.isEnabled(): painter.setOpacity(.38)
        QSvgRenderer(svg('chevron-down', self.palette().color(QPalette.ColorRole.Text).name()).encode()).render(painter, target)
        painter.end()
