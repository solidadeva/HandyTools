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


def svg(name, color='#8e8e93', tile=False):
    background = ''
    if tile:
        top,bottom = ('#5ac8fa','#007aff') if name=='download' else ('#ffcc66','#ff9500') if name=='convert' else ('#9ea5b2','#535d70')
        background = f'''<defs><linearGradient id="tile" x1="0" y1="0" x2="0.25" y2="1"><stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient><linearGradient id="rim" x1="0" y1="0" x2="0" y2="1"><stop stop-color="white" stop-opacity=".55"/><stop offset="1" stop-color="white" stop-opacity=".04"/></linearGradient></defs>
        <path d="M22 2H42C56 2 62 8 62 22V42C62 56 56 62 42 62H22C8 62 2 56 2 42V22C2 8 8 2 22 2Z" fill="url(#tile)"/>
        <path d="M22 2H42C56 2 62 8 62 22V42C62 56 56 62 42 62H22C8 62 2 56 2 42V22C2 8 8 2 22 2Z" fill="none" stroke="url(#rim)" stroke-width=".75"/>'''
        color = '#ffffff'
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 64 64">'
            + background + f'<g fill="none" stroke="{color}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">'
            + ART[name] + '</g></svg>')


def app_icon(name, color='#8e8e93', size=64, tile=False):
    data = svg(name, color, tile).encode()
    pm = QPixmap(size*2,size*2); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); QSvgRenderer(data).render(p); p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def export_assets(destination):
    folder=Path(destination); folder.mkdir(parents=True,exist_ok=True)
    for filename,name,color,tile in [
        ('easy-downloader','download','#007aff',True),
        ('easy-converter','convert','#ff9500',True),
        ('settings','settings','#8e8e93',False),
        ('donate','donate','#8e8e93',False)]:
        (folder/(filename+'.svg')).write_text(svg(name,color,tile),encoding='utf-8')
        app_icon(name,color,256,tile).pixmap(256,256).save(str(folder/(filename+'.png')))
