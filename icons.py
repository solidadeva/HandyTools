"""Original code-native vector artwork for the Handy family."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

ART = {
 'download': '<path d="M32 16v25m-10-10 10 10 10-10M17 42v7a3 3 0 0 0 3 3h24a3 3 0 0 0 3-3v-7"/>',
 'convert': '<path d="M16 24h32m-9-9 9 9-9 9M48 42H16m9-9-9 9 9 9"/>',
 'donate': '<path d="M32 48 16 32c-12-13 5-27 16-13 11-14 28 0 16 13Z"/>',
 'settings': '<path d="m27 10-1 6-5 3-6-2-5 9 5 4v5l-5 4 5 9 6-2 5 3 1 6h10l1-6 5-3 6 2 5-9-5-4v-5l5-4-5-9-6 2-5-3-1-6Z"/><circle cx="32" cy="32" r="9"/>',
 'sun': '<circle cx="32" cy="32" r="10"/><path d="M32 8v6m0 36v6M8 32h6m36 0h6M15 15l4 4m26 26 4 4M15 49l4-4m26-26 4-4"/>',
 'moon': '<path d="M46 41A22 22 0 0 1 23 12a22 22 0 1 0 23 29Z"/>',
 'close': '<path d="m20 20 24 24m0-24L20 44"/>',
 'minimize': '<path d="M18 32h28"/>',
 'brand': '<rect x="12" y="12" width="16" height="16" rx="4"/><rect x="36" y="12" width="16" height="16" rx="4"/><rect x="12" y="36" width="16" height="16" rx="4"/><rect x="36" y="36" width="16" height="16" rx="4"/>'
}


def svg(name, color='#dce8e6', tile=False):
    background = ''
    if tile:
        # One quiet accent per app; no raster dependencies or external fonts.
        background = f'<rect x="1" y="1" width="62" height="62" rx="16" fill="{color}"/>'
        color = '#142524' if name == 'download' else '#f7f3ff'
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 64 64">'
            + background + f'<g fill="none" stroke="{color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">'
            + ART[name] + '</g></svg>')


def app_icon(name, color='#dce8e6', size=64, tile=False):
    data = svg(name, color, tile).encode()
    pm = QPixmap(size*2,size*2); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); QSvgRenderer(data).render(p); p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def export_assets(destination):
    folder=Path(destination); folder.mkdir(parents=True,exist_ok=True)
    for filename,name,color,tile in [
        ('easy-downloader','download','#91d5bd',True),
        ('easy-converter','convert','#8879cc',True),
        ('settings','settings','#dce8e6',False),
        ('donate','donate','#dce8e6',False)]:
        (folder/(filename+'.svg')).write_text(svg(name,color,tile),encoding='utf-8')
        app_icon(name,color,256,tile).pixmap(256,256).save(str(folder/(filename+'.png')))
