"""Centered frameless launcher, extensible carousel and independent tool windows."""
from dataclasses import dataclass
import json
import math
from pathlib import Path

from PySide6.QtCore import (Qt, QRectF, QPoint, QPointF, QSize, QSettings, QTimer, Signal,
                           Property, QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QCursor, QShortcut,
                          QKeySequence, QGuiApplication, QLinearGradient)
from PySide6.QtWidgets import (QMainWindow, QWidget, QPushButton, QVBoxLayout,
    QHBoxLayout, QScrollArea, QFrame, QMessageBox, QToolTip, QSizeGrip)

from app import ToolPage, tool_styles
from engine import tool
from workers import Task
from icons import app_icon

from version import VERSION


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    glyph: str
    color: str
    kind: str


TOOLS = (
    ToolSpec('downloader', 'Easy Downloader', 'download', '#007aff', 'download'),
    ToolSpec('converter', 'Easy Converter', 'convert', '#ff9500', 'convert'),
)

PALETTES = {
 'dark': dict(panel='#1c1c1e', panel_top='#29292c', tab='#323235', tab_top='#3a3a3d', ink='#f5f5f7', muted='#98989d', edge='#414145', selected='#303034', accent='#0a84ff'),
 'light': dict(panel='#f5f5f7', panel_top='#ffffff', tab='#e5e5ea', tab_top='#f0f0f3', ink='#1d1d1f', muted='#6e6e73', edge='#d9d9df', selected='#ebebf0', accent='#007aff')
}



def center_window(widget):
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen:
        frame = widget.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        widget.move(frame.topLeft())


class Carousel(QWidget):
    activated = Signal(str)
    selection_changed = Signal(int)

    def __init__(self, tools=TOOLS, parent=None):
        super().__init__(parent)
        self.tools = list(tools)
        self.selected = 0
        self.theme = 'dark'
        self.offset = 0.0
        self.press_pos = None
        self.hovered = -1
        self.wheel_delta = 0
        self.cache = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName('App carousel')
        self.setAccessibleDescription('Left and Right select an app. Enter opens it. Mouse wheel or drag also navigates.')
        self.animation = QPropertyAnimation(self, b'viewOffset', self)
        self.animation.setDuration(230)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.update_accessibility()

    def get_offset(self):
        return self.offset

    def set_offset(self, value):
        self.offset = value; self.update()

    viewOffset = Property(float, get_offset, set_offset)

    def update_accessibility(self):
        if self.tools:
            self.setAccessibleName('App carousel: ' + self.tools[self.selected].name)

    def set_tools(self, tools):
        self.animation.stop()
        self.tools = list(tools)
        self.selected = min(self.selected, max(0, len(self.tools)-1))
        self.offset = float(self.start_index())
        self.update_accessibility(); self.update()

    def start_index(self):
        return max(0, min(self.selected-1, len(self.tools)-3))

    def select(self, index):
        if not self.tools:
            return
        self.selected = index % len(self.tools)
        self.animation.stop(); self.animation.setStartValue(self.offset)
        self.animation.setEndValue(float(self.start_index())); self.animation.start()
        self.update_accessibility(); self.selection_changed.emit(self.selected); self.update()

    def step(self, direction):
        self.select(self.selected + direction)

    def item_rect(self, index):
        slots = min(3, len(self.tools))
        spacing = min(214, (self.width()-170)/max(1,slots))
        x = self.width()/2 + (index-self.offset-(slots-1)/2)*spacing
        height=min(174,self.height()-62)
        return QRectF(x-91, 17 if self.height()<250 else 30, 182, height)

    def arrow_rect(self, right):
        return QRectF(self.width()-65 if right else 25, self.height()/2-21, 40, 42)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = PALETTES[self.theme]
        p.setClipRect(QRectF(85,0,self.width()-170,self.height()-27))
        for i, spec in enumerate(self.tools):
            r = self.item_rect(i)
            if r.right() < 80 or r.left() > self.width()-80:
                continue
            selected = i == self.selected
            p.setPen(QPen(QColor(c['edge']),1) if selected else Qt.PenStyle.NoPen)
            p.setBrush(QColor(c['selected']) if selected else Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r,22,22)
            if i == self.hovered and not selected:
                p.setPen(QPen(QColor(c['edge']),1)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRoundedRect(r,22,22)
            key = (spec.glyph, spec.color)
            if key not in self.cache:
                self.cache[key] = app_icon(spec.glyph,spec.color,92,True)
            size=min(86,int(r.height()*.52))
            self.cache[key].paint(p, int(r.center().x()-size/2), int(r.top()+15),size,size)
            p.setPen(QColor(c['ink']))
            f=QFont('Segoe UI',11); f.setWeight(QFont.Weight.Medium); p.setFont(f)
            p.drawText(QRectF(r.x(),r.top()+size+28,r.width(),26),Qt.AlignmentFlag.AlignCenter,spec.name)
            if selected:
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(c['accent']))
                p.drawEllipse(QPointF(r.center().x(),r.bottom()-10),2,2)
        p.setClipping(False)
        for right in (False,True):
            rect = self.arrow_rect(right)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c['selected']))
            p.drawRoundedRect(rect,20,20)
            p.setPen(QPen(QColor(c['muted']),1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            x,y=rect.center().x(),rect.center().y(); direction=1 if right else -1
            p.drawLine(QPointF(x-direction*3,y-6),QPointF(x+direction*3,y))
            p.drawLine(QPointF(x+direction*3,y),QPointF(x-direction*3,y+6))
        count = len(self.tools)
        gap = min(14,180/max(1,count))
        for i in range(count):
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(c['muted'] if i==self.selected else c['edge']))
            p.drawEllipse(QPointF(self.width()/2 + (i-(count-1)/2)*gap,self.height()-22),3,3)

    def keyPressEvent(self,e):
        if e.key() == Qt.Key.Key_Right:
            self.step(1);e.accept()
        elif e.key() == Qt.Key.Key_Left:
            self.step(-1);e.accept()
        elif e.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space) and self.tools:
            self.activated.emit(self.tools[self.selected].id);e.accept()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self,e):
        angle = e.angleDelta().x() or e.angleDelta().y()
        if angle:
            self.wheel_delta += angle
            if abs(self.wheel_delta) >= 120:
                self.step(-1 if self.wheel_delta>0 else 1); self.wheel_delta=0
        elif not e.pixelDelta().isNull():
            self.wheel_delta += e.pixelDelta().x() or e.pixelDelta().y()
            if abs(self.wheel_delta)>=40:
                self.step(-1 if self.wheel_delta>0 else 1); self.wheel_delta=0
        e.accept()

    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self.press_pos=e.position();self.setFocus();e.accept()

    def mouseMoveEvent(self,e):
        self.hovered=next((i for i in range(len(self.tools)) if self.item_rect(i).contains(e.position())),-1)
        over_arrow=any(self.arrow_rect(r).contains(e.position()) for r in (True,False))
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hovered>=0 or over_arrow else Qt.CursorShape.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self,e):
        if e.button()!=Qt.MouseButton.LeftButton or self.press_pos is None:
            return
        delta=e.position()-self.press_pos;self.press_pos=None
        if abs(delta.x())>35:
            self.step(1 if delta.x()<0 else -1);return
        if delta.manhattanLength()>12:
            return
        for right in (False,True):
            if self.arrow_rect(right).contains(e.position()):
                self.step(1 if right else -1);return
        for i,spec in enumerate(self.tools):
            if self.item_rect(i).contains(e.position()):
                self.select(i);self.activated.emit(spec.id);return

    def leaveEvent(self,e):
        self.hovered=-1;self.update()


class Surface(QWidget):
    def __init__(self,window):
        super().__init__(window)
        self.owner=window
        self.drag_start=None

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c=PALETTES[self.owner.theme]
        w,h=self.width(),self.height()
        tab_gradient=QLinearGradient(0,0,0,h)
        tab_gradient.setColorAt(0,QColor(c['tab_top']));tab_gradient.setColorAt(1,QColor(c['tab']))
        p.setPen(QPen(QColor(c['edge']),.8));p.setBrush(tab_gradient)
        margin=w*.135
        p.drawRoundedRect(QRectF(margin+.5,.5,w-2*margin-1,88),26,26)
        p.drawRoundedRect(QRectF(margin+.5,h-88,w-2*margin-1,87.5),26,26)
        body_gradient=QLinearGradient(0,44,0,h-44)
        body_gradient.setColorAt(0,QColor(c['panel_top']));body_gradient.setColorAt(1,QColor(c['panel']))
        p.setBrush(body_gradient)
        p.drawRoundedRect(QRectF(.5,44,w-1,h-88),32,32)
        p.setPen(QColor(c['ink']));f=QFont('Segoe UI',14 if w>=800 else 12);f.setWeight(QFont.Weight.DemiBold);p.setFont(f)
        p.drawText(QRectF(margin+60,5,w-2*margin-144,34),Qt.AlignmentFlag.AlignCenter,'Handy Tools App')

    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton and e.position().y()<44:
            self.drag_start=e.globalPosition().toPoint()-self.owner.pos()

    def mouseMoveEvent(self,e):
        if self.drag_start is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.owner.move(e.globalPosition().toPoint()-self.drag_start)

    def mouseReleaseEvent(self,e):
        self.drag_start=None

    def resizeEvent(self,e):
        w,h=self.width(),self.height()
        margin=int(w*.135)
        self.owner.carousel.setGeometry(0,44,w,h-88)
        self.owner.footer.setGeometry(margin+22,h-42,w-2*margin-62,36)
        self.owner.theme_button.setGeometry(margin+15,4,36,36)
        self.owner.minimize_button.setGeometry(w-margin-83,4,32,36)
        self.owner.close_button.setGeometry(w-margin-49,4,32,36)
        self.owner.resize_grip.setGeometry(w-margin-24,h-24,16,16)
        self.owner.settings.setValue('launcher_size',[w,h])


class ResizeGrip(QSizeGrip):
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(PALETTES[self.window().theme]['muted']),1.4))
        for offset in (0,4,8):
            p.drawLine(4+offset,14,14,4+offset)


class ToolWindow(QMainWindow):
    def __init__(self,manager,spec):
        super().__init__(manager,Qt.WindowType.Window)
        self.manager=manager;self.spec=spec
        self.setWindowTitle(spec.name)
        self.setWindowIcon(app_icon(spec.glyph,spec.color,64,True))
        self.resize(850,780);self.setMinimumSize(650,670)
        screen=QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen:
            available=screen.availableGeometry()
            self.setMinimumSize(min(650,available.width()-32),min(670,available.height()-64))
            self.resize(min(850,available.width()-32),min(780,available.height()-64))
        self.pending_close=False
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(28,26,28,26)
        self.page=ToolPage(manager,spec.kind);box.addWidget(self.page)
        scroll.setWidget(content);self.setCentralWidget(scroll)
        self.apply_theme();center_window(self)

    def apply_theme(self):
        self.setStyleSheet(tool_styles(self.manager.theme))

    def closeEvent(self,e):
        if self.page.is_busy():
            if not self.pending_close and not self.manager.closing:
                if QMessageBox.question(self,'عملیات در حال اجراست','عملیات متوقف شود و پنجره بسته شود؟')!=QMessageBox.StandardButton.Yes:
                    e.ignore();return
            self.pending_close=True;self.page.cancel();e.ignore()
        else:
            e.accept()


class Window(QMainWindow):
    def __init__(self,settings=None):
        super().__init__()
        self.settings=settings if settings is not None else QSettings('HandyTools','HandyToolsApp')
        self.theme=self.settings.value('theme','dark')
        if self.theme not in PALETTES:
            self.theme='dark'
        self.closing=False;self.setup_task=None;self.windows={};self.factories={};self.settings_dialog=None
        self.specs=list(TOOLS);self.history=[]
        self.setWindowTitle('Handy Tools App')
        self.setWindowIcon(app_icon('brand','#007aff'))
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen=QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        available=screen.availableGeometry() if screen else None
        size=self.settings.value('launcher_size',[760,300])
        try:
            width,height=int(size[0]),int(size[1])
        except (ValueError,TypeError,IndexError):
            width,height=760,300
        self.setMinimumSize(600,280)
        self.resize(max(600,min(width,available.width()-48 if available else 1400)),
                    max(280,min(height,available.height()-48 if available else 800)))
        self.surface=Surface(self);self.setCentralWidget(self.surface)
        self.carousel=Carousel(self.specs,self.surface);self.carousel.activated.connect(self.open_tool)
        self.footer=QWidget(self.surface);self.footer.setObjectName('footer')
        row=QHBoxLayout(self.footer);row.setContentsMargins(4,0,4,0);row.setSpacing(14)
        from app import label
        self.version=label('WIN  ·  v'+VERSION+'  /  BY SOLIDADEVA');row.addWidget(self.version);row.addStretch()
        self.donate_button=self.icon_button('donate','دونیت — به‌زودی',lambda:self.coming_soon(self.donate_button))
        self.settings_button=self.icon_button('settings','تنظیمات و آپدیت',self.open_settings)
        row.addWidget(self.donate_button);row.addWidget(self.settings_button)
        self.theme_button=self.icon_button('sun','تغییر حالت روشن / تاریک',self.toggle_theme)
        self.minimize_button=self.icon_button('minimize','کوچک کردن',self.showMinimized)
        self.close_button=self.icon_button('close','بستن',self.close)
        self.resize_grip=ResizeGrip(self.surface)
        self.resize_grip.setToolTip('برای تغییر اندازه، این گوشه را بکشید')
        self.resize_grip.setAccessibleName('تغییر اندازهٔ لانچر')
        for key,fn in [('Left',lambda:self.carousel.step(-1)),('Right',lambda:self.carousel.step(1)),
                       ('Return',lambda:self.open_selected()),('Enter',lambda:self.open_selected())]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(fn)
        self.apply_theme();center_window(self)
        self.restore_recent()
        QTimer.singleShot(0,self.prepare_tools)

    def icon_button(self,glyph,tooltip,fn):
        b=QPushButton(self.surface);b.setFixedSize(36,36);b.setProperty('glyph',glyph)
        b.setCursor(Qt.CursorShape.PointingHandCursor);b.setToolTip(tooltip);b.setAccessibleName(tooltip)
        b.clicked.connect(fn);return b

    def open_settings(self):
        from update_ui import SettingsDialog
        if self.settings_dialog is None:
            self.settings_dialog=SettingsDialog(self)
        if self.settings_dialog.task is None:
            self.settings_dialog.pending_close=False
        self.settings_dialog.apply_theme()
        self.settings_dialog.show();self.settings_dialog.raise_();self.settings_dialog.activateWindow()

    def coming_soon(self,b):
        QToolTip.showText(b.mapToGlobal(QPoint(0,-28)),'این بخش در نسخه‌های بعدی اضافه می‌شود.',b)

    def register_tool(self,spec,factory):
        """Add future apps without changing carousel layout or navigation."""
        if any(x.id==spec.id for x in self.specs):
            raise ValueError('Duplicate app id: '+spec.id)
        self.specs.append(spec);self.factories[spec.id]=factory;self.carousel.set_tools(self.specs)

    def open_selected(self):
        if self.carousel.tools:
            self.open_tool(self.carousel.tools[self.carousel.selected].id)

    def open_tool(self,tool_id):
        spec=next(x for x in self.specs if x.id==tool_id)
        if tool_id not in self.windows:
            factory=self.factories.get(tool_id,ToolWindow)
            self.windows[tool_id]=factory(self,spec)
        window=self.windows[tool_id]
        window.showNormal();window.raise_();window.activateWindow()
        return window

    def toggle_theme(self):
        self.theme='light' if self.theme=='dark' else 'dark'
        self.settings.setValue('theme',self.theme);self.apply_theme()

    def apply_theme(self):
        c=PALETTES[self.theme];self.carousel.theme=self.theme;self.carousel.update();self.surface.update()
        self.surface.setStyleSheet('QWidget { background: transparent; color: '+c['ink']+'; font-family: "Segoe UI"; } QPushButton { background: transparent; border: none; border-radius: 9px; } QPushButton:hover { background: '+c['edge']+'; } QPushButton:focus { border: 1px solid '+c['muted']+'; } QToolTip { background: '+c['tab']+'; color: '+c['ink']+'; padding: 8px; }')
        self.version.setStyleSheet('font-size: 11px; color: '+c['muted']+';')
        for b in [self.donate_button,self.settings_button,self.theme_button,self.minimize_button,self.close_button]:
            glyph=b.property('glyph')
            if b is self.theme_button:
                glyph='sun' if self.theme=='dark' else 'moon'
            b.setIcon(app_icon(glyph,c['muted'],22));b.setIconSize(QSize(22,22))
        for window in self.windows.values():
            window.apply_theme()
        if self.settings_dialog is not None:
            self.settings_dialog.apply_theme()

    def prepare_tools(self):
        if self.closing:
            return
        try:
            tool('ffmpeg');tool('ffprobe');return
        except RuntimeError:
            pass
        task=Task('setup',{},self);self.setup_task=task
        task.progress.connect(lambda percent,text:self.version.setText('FFmpeg  ·  '+(f'{percent:.0f}%' if percent is not None else '…')))
        task.failed.connect(lambda text:self.setup_failed(text))
        task.finished.connect(self.setup_finished);task.start()

    def setup_failed(self,text):
        self.version.setToolTip('دریافت FFmpeg ناموفق؛ با شروع عملیات دوباره تلاش می‌شود.\n'+text)

    def setup_finished(self):
        task=self.setup_task;self.setup_task=None
        self.version.setText('WIN  ·  v'+VERSION+'  /  BY SOLIDADEVA')
        if task:
            task.deleteLater()
        self.finish_close()

    def restore_recent(self):
        try:
            history=json.loads(self.settings.value('history','[]'))
            self.history=[x for x in history if isinstance(x,dict) and 'path' in x and 'kind' in x][:3]
        except (TypeError,ValueError):
            self.history=[]

    def record(self,kind,value):
        self.history=[dict(kind=kind,path=value)]+[x for x in self.history if x['path']!=value][:2]
        self.settings.setValue('history',json.dumps(self.history,ensure_ascii=False))

    def clear_recent(self):
        self.history=[];self.settings.remove('history')

    def pages(self):
        return [w.page for w in self.windows.values() if hasattr(w,'page')]

    def task_finished(self,page):
        for window in self.windows.values():
            if getattr(window,'page',None) is page and window.pending_close:
                window.pending_close=False;QTimer.singleShot(0,window.close)
        self.finish_close()

    def closeEvent(self,e):
        busy=[p for p in self.pages() if p.is_busy()]
        updating=self.settings_dialog is not None and self.settings_dialog.task is not None
        if busy or self.setup_task or updating:
            if not self.closing:
                if busy and QMessageBox.question(self,'عملیات در حال اجراست','همهٔ عملیات متوقف شوند و برنامه بسته شود؟')!=QMessageBox.StandardButton.Yes:
                    e.ignore();return
                self.closing=True
                for p in busy:
                    p.cancel()
                if self.setup_task:
                    self.setup_task.cancel()
                if updating:
                    self.settings_dialog.reject()
            e.ignore()
        else:
            for window in self.windows.values():
                window.close()
            if self.settings_dialog is not None:
                self.settings_dialog.reject()
            self.settings.sync();e.accept()

    def finish_close(self):
        updating=self.settings_dialog is not None and self.settings_dialog.task is not None
        if self.closing and not self.setup_task and not updating and not any(p.is_busy() for p in self.pages()):
            QTimer.singleShot(0,self.close)
