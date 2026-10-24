"""Shared tool interfaces for the Handy Tools App launcher."""
import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QSize, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QComboBox, QFileDialog,
    QProgressBar, QPlainTextEdit, QMessageBox, QScrollArea, QSizePolicy)
from engine import FORMATS, IMAGES, tool
from workers import Task, validate_url

DARK = dict(bg='#1c1c1e', side='#242426', card='#2c2c2e', hover='#3a3a3c', text='#f5f5f7',
            muted='#a1a1a6', border='#444446', accent='#0a84ff', ink='#ffffff', input='#242426', hero='#303034')
LIGHT = dict(bg='#f5f5f7', side='#f2f2f4', card='#ffffff', hover='#e8e8ed', text='#1d1d1f',
             muted='#6e6e73', border='#d9d9df', accent='#007aff', ink='#ffffff', input='#ffffff', hero='#eaf3ff')


def icon(kind, color='#b5a2ff', size=48):
    """Small vector icons, painted at high resolution for Windows scaling."""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 48, size * 2 / 48)
    p.setPen(QPen(QColor(color), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == 'convert':
        p.drawRoundedRect(9, 7, 20, 27, 4, 4)
        p.drawLine(16, 15, 23, 15); p.drawLine(16, 21, 23, 21)
        p.drawLine(22, 40, 40, 40); p.drawLine(34, 34, 40, 40); p.drawLine(34, 46, 40, 40)
        p.drawLine(39, 10, 39, 27); p.drawLine(33, 21, 39, 27); p.drawLine(45, 21, 39, 27)
    elif kind == 'download':
        p.drawRoundedRect(7, 6, 34, 27, 5, 5)
        p.drawLine(24, 13, 24, 27); p.drawLine(18, 21, 24, 27); p.drawLine(30, 21, 24, 27)
        p.drawLine(15, 41, 33, 41); p.drawLine(24, 33, 24, 41)
    elif kind == 'home':
        p.drawLine(8, 23, 24, 9); p.drawLine(24, 9, 40, 23)
        p.drawLine(12, 20, 12, 39); p.drawLine(12, 39, 36, 39); p.drawLine(36, 39, 36, 20)
        p.drawRect(21, 28, 7, 11)
    else:
        for x, y in ((8,8),(27,8),(8,27),(27,27)):
            p.drawRoundedRect(x, y, 13, 13, 3, 3)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def label(text, role='', wrap=False):
    w = QLabel(text)
    if role:
        w.setObjectName(role)
    w.setWordWrap(wrap)
    return w


def button(text, fn, role=''):
    w = QPushButton(text)
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    w.clicked.connect(fn)
    if role:
        w.setObjectName(role)
    return w


class DropButton(QPushButton):
    file_selected = Signal(str)

    def __init__(self):
        super().__init__('انتخاب فایل یا کشیدن و رها کردن در این قسمت\nویدیو، صدا یا تصویر • پشتیبانی از HEIC')
        self.setObjectName('drop')
        self.setMinimumHeight(116)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self.browse)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'انتخاب فایل')
        if path:
            self.file_selected.emit(path)

    def dragEnterEvent(self, e):
        urls = e.mimeData().urls()
        if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_file():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if self.isEnabled():
            urls = e.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_file():
                self.file_selected.emit(urls[0].toLocalFile())
                e.acceptProposedAction()


class ToolPage(QWidget):
    def __init__(self, window, kind):
        super().__init__()
        self.window, self.kind = window, kind
        self.task = None
        self.output = None
        self.source = None
        self.inputs = []
        self.custom_folder = window.settings.value('converter_folder', '') if kind == 'convert' else ''
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        titles = ('Easy Converter', 'تبدیل ویدیو، صدا و تصویر با حفظ فایل اصلی') if kind == 'convert' else ('Easy Downloader', 'دانلود ویدیو با خروجی MP4 سازگار با پریمیر')
        title = label(titles[0], 'pageTitle')
        title.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        box.addWidget(title)
        box.addWidget(label(titles[1], 'muted'))
        form = QFrame(); form.setObjectName('panel')
        formbox = QVBoxLayout(form); formbox.setContentsMargins(24, 22, 24, 22); formbox.setSpacing(12)
        if kind == 'convert':
            formbox.addWidget(label('۱. فایل ورودی', 'section'))
            self.pick = DropButton(); self.pick.file_selected.connect(self.set_source)
            formbox.addWidget(self.pick); self.inputs.append(self.pick)
            self.source_info = label('هنوز فایلی انتخاب نشده', 'muted')
            self.source_info.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            formbox.addWidget(self.source_info)
            formbox.addWidget(label('۲. فرمت خروجی', 'section'))
            self.format = QComboBox(); self.format.addItems(FORMATS)
            self.format.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.inputs.append(self.format); formbox.addWidget(self.format)
            self.hint = label('', 'muted', True); formbox.addWidget(self.hint)
            self.format.currentTextChanged.connect(self.format_hint); self.format_hint()
        else:
            formbox.addWidget(label('۱. لینک ویدیو', 'section'))
            self.url = QLineEdit(); self.url.setPlaceholderText('https://www.youtube.com/watch?v=…')
            self.url.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.url.setClearButtonEnabled(True); formbox.addWidget(self.url); self.inputs.append(self.url)
            formbox.addWidget(label('۲. کیفیت و خروجی', 'section'))
            self.format = QComboBox()
            for text, data in [('بهترین کیفیت موجود • MP4 / H.264', 'best'), ('حداکثر 1080p • MP4 / H.264', '1080'), ('حداکثر 720p • MP4 / H.264', '720'), ('حداکثر 480p • MP4 / H.264', '480'), ('فقط صدا • MP3', 'audio')]:
                self.format.addItem(text, data)
            formbox.addWidget(self.format); self.inputs.append(self.format)
            formbox.addWidget(label('ویدیو پس از دانلود به H.264 و صدای AAC تبدیل می‌شود.', 'muted', True))
        formbox.addWidget(label('۳. پوشهٔ خروجی', 'section'))
        row = QHBoxLayout()
        self.folder = QLineEdit(); self.folder.setReadOnly(True)
        self.folder.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        folder = window.settings.value('download_folder', str(Path.home() / 'Downloads')) if kind != 'convert' else self.custom_folder
        self.folder.setText(folder)
        self.folder.setPlaceholderText('کنار فایل ورودی ذخیره شود')
        self.browse = button('انتخاب پوشه', self.choose_folder)
        row.addWidget(self.folder, 1); row.addWidget(self.browse)
        formbox.addLayout(row); self.inputs.append(self.browse)
        if kind == 'convert':
            self.reset = button('استفاده از پوشهٔ فایل ورودی', self.reset_folder, 'link')
            formbox.addWidget(self.reset, 0, Qt.AlignmentFlag.AlignRight); self.inputs.append(self.reset)
        box.addWidget(form)
        actions = QHBoxLayout()
        self.start_button = button('شروع تبدیل' if kind == 'convert' else 'شروع دانلود', self.start, 'primary')
        self.start_button.setMinimumHeight(46)
        self.cancel_button = button('لغو', self.cancel)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.start_button, 1); actions.addWidget(self.cancel_button)
        if kind == 'download':
            self.update = button('به‌روزرسانی موتور', lambda: self.start(update=True))
            actions.addWidget(self.update); self.inputs.append(self.update)
        box.addLayout(actions)
        self.bar = QProgressBar(); self.bar.setTextVisible(False); self.bar.setValue(0)
        self.bar.setFixedHeight(6); box.addWidget(self.bar)
        statusrow = QHBoxLayout()
        self.status = label('آماده', 'muted', True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        statusrow.addWidget(self.status, 1)
        self.open_button = button('باز کردن پوشهٔ خروجی', self.open_folder, 'link')
        self.open_button.setEnabled(False); statusrow.addWidget(self.open_button)
        box.addLayout(statusrow)
        if kind == 'download':
            self.details = button('نمایش جزئیات', self.toggle_log, 'link'); box.addWidget(self.details, 0, Qt.AlignmentFlag.AlignRight)
            self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(500)
            self.log.setLayoutDirection(Qt.LayoutDirection.LeftToRight); self.log.setMaximumHeight(130)
            self.log.hide(); box.addWidget(self.log)
        box.addStretch()

    def format_hint(self):
        fmt = self.format.currentText()
        self.hint.setText('تصویر اصلی HEIC به‌صورت کامل خوانده می‌شود؛ برای ویدیو، فریم اول ذخیره می‌شود.' if fmt in IMAGES else 'استخراج صدای فایل ورودی' if fmt in {'MP3','WAV','FLAC'} else 'خروجی ویدیو با ابعاد اصلی و کیفیت متعادل')

    def set_source(self, path):
        if self.is_busy() or not Path(path).is_file():
            return
        self.source = Path(path).resolve()
        self.pick.setText(self.source.name + '\nبرای تغییر فایل کلیک کنید')
        self.pick.setToolTip(str(self.source))
        self.source_info.setText(self.source.suffix.upper().lstrip('.') + '  •  ' + f'{self.source.stat().st_size / 1048576:.1f} MB')
        if not self.custom_folder:
            self.folder.setText(str(self.source.parent))

    def choose_folder(self):
        value = QFileDialog.getExistingDirectory(self, 'انتخاب پوشهٔ خروجی', self.folder.text() or str(Path.home()))
        if value:
            self.folder.setText(value)
            key = 'converter_folder' if self.kind == 'convert' else 'download_folder'
            self.window.settings.setValue(key, value)
            if self.kind == 'convert':
                self.custom_folder = value

    def reset_folder(self):
        self.custom_folder = ''
        self.window.settings.remove('converter_folder')
        self.folder.setText(str(self.source.parent) if self.source else '')

    def toggle_log(self):
        show = self.log.isHidden(); self.log.setVisible(show)
        self.details.setText('بستن جزئیات' if show else 'نمایش جزئیات')

    def is_busy(self):
        return self.task is not None

    def start(self, update=False):
        if self.is_busy():
            return
        folder = self.folder.text().strip()
        if not update:
            if self.kind == 'convert' and (not self.source or not self.source.is_file()):
                QMessageBox.information(self, 'فایل ورودی', 'ابتدا یک فایل انتخاب کنید.'); return
            if self.kind == 'download' and not validate_url(self.url.text()):
                QMessageBox.information(self, 'لینک ویدیو', 'یک لینک معتبر با http یا https وارد کنید.'); return
            if not folder or not Path(folder).is_dir():
                QMessageBox.information(self, 'پوشهٔ خروجی', 'یک پوشهٔ موجود برای ذخیره انتخاب کنید.'); return
        options = dict(folder=folder)
        if self.kind == 'convert':
            options.update(source=str(self.source), format=self.format.currentText())
        else:
            options.update(url=self.url.text().strip(), quality=self.format.currentData())
            self.log.clear()
        self.output = None; self.open_button.setEnabled(False)
        self.set_busy(True)
        self.progress(None, 'به‌روزرسانی موتور…' if update else 'آماده‌سازی ابزارها؛ دریافت اولیه ممکن است چند دقیقه طول بکشد…')
        task = Task('update' if update else self.kind, options, self)
        self.task = task
        task.progress.connect(self.progress)
        if self.kind == 'download':
            task.log.connect(self.log.appendPlainText)
        task.succeeded.connect(self.success)
        task.failed.connect(self.failure)
        task.cancelled.connect(lambda: self.status.setText('عملیات لغو شد'))
        task.finished.connect(self.finished)
        task.start()

    def set_busy(self, value):
        for control in self.inputs + [self.start_button]:
            control.setEnabled(not value)
        self.cancel_button.setEnabled(value)

    def progress(self, value, text):
        self.status.setText(text)
        self.bar.setRange(0, 0 if value is None else 100)
        if value is not None:
            self.bar.setValue(round(value))
            self.status.setText(text + f'  •  {value:.0f}%')

    def success(self, value):
        self.output = Path(value) if value else None
        self.progress(100, 'فایل آماده شد' if value else 'موتور دانلود به‌روز شد')
        self.open_button.setEnabled(bool(value))
        if value:
            self.window.record(self.kind, value)

    def failure(self, text):
        self.status.setText('عملیات انجام نشد؛ جزئیات خطا را بررسی کنید.')
        if self.kind == 'download':
            self.log.appendPlainText(text); self.log.show(); self.details.setText('بستن جزئیات')
        if not self.window.closing:
            QMessageBox.warning(self, 'خطا', text)

    def finished(self):
        task = self.task
        self.task = None
        self.set_busy(False)
        self.bar.setRange(0, 100)
        if not self.output and self.bar.value() < 100:
            self.bar.setValue(0)
        if task:
            task.deleteLater()
        self.window.task_finished(self)

    def cancel(self):
        if self.task:
            self.task.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText('در حال توقف…')

    def open_folder(self):
        if self.output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output.parent)))


def tool_styles(theme):
    c = DARK if theme == 'dark' else LIGHT
    return ('''
        QWidget { background: %(bg)s; color: %(text)s; font-family: 'Segoe UI Variable', 'Segoe UI', 'Noto Sans Arabic'; font-size: 13px; }
        QScrollArea { border: none; }
        QLabel { background: transparent; }
        QLabel#muted { color: %(muted)s; font-size: 12px; }
        QLabel#pageTitle { font-size: 25px; font-weight: 600; letter-spacing: -0.5px; }
        QLabel#section { font-size: 12px; font-weight: 600; color: %(muted)s; }
        QFrame#panel { background: %(card)s; border: 1px solid %(border)s; border-radius: 18px; }
        QFrame#panel QWidget { background: transparent; }
        QFrame#separator { background: %(border)s; border: none; max-height: 1px; }
        QPushButton { background: %(card)s; border: 1px solid %(border)s; border-radius: 10px; padding: 9px 16px; font-weight: 500; }
        QPushButton:hover { background: %(hover)s; }
        QPushButton:pressed { background: %(border)s; }
        QPushButton:focus { border: 1px solid %(accent)s; }
        QPushButton:disabled { color: %(muted)s; border-color: %(border)s; }
        QPushButton#primary { background: %(accent)s; color: white; border: 1px solid %(accent)s; font-weight: 600; }
        QPushButton#primary:hover { background: #2997ff; border-color: #2997ff; }
        QPushButton#primary:pressed { background: #0062cc; }
        QPushButton#primary:disabled { background: %(hover)s; border-color: %(border)s; color: %(muted)s; }
        QPushButton#link { background: transparent; color: %(accent)s; border: none; padding: 6px; }
        QFrame#panel QPushButton#drop { background: %(input)s; color: %(muted)s; border: 1px dashed %(border)s; border-radius: 14px; padding: 20px; }
        QFrame#panel QPushButton#drop:hover { border-color: %(accent)s; color: %(accent)s; }
        QFrame#panel QLineEdit, QFrame#panel QComboBox, QLineEdit, QComboBox { background: %(input)s; border: 1px solid %(border)s; border-radius: 10px; padding: 10px 12px; min-height: 20px; selection-background-color: %(accent)s; selection-color: white; }
        QLineEdit:focus, QComboBox:focus { border-color: %(accent)s; }
        QLineEdit:disabled, QComboBox:disabled { color: %(muted)s; }
        QComboBox::drop-down { border: none; width: 28px; }
        QComboBox QAbstractItemView { background: %(card)s; border: 1px solid %(border)s; border-radius: 10px; selection-background-color: %(accent)s; selection-color: white; padding: 8px; }
        QProgressBar { background: %(border)s; border: none; border-radius: 3px; }
        QProgressBar::chunk { background: %(accent)s; border-radius: 3px; }
        QPlainTextEdit { background: %(input)s; border: 1px solid %(border)s; border-radius: 12px; padding: 12px; font-family: Consolas, monospace; font-size: 11px; }
        QScrollBar:vertical { background: transparent; width: 8px; }
        QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 30px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QToolTip { background: %(card)s; color: %(text)s; border: 1px solid %(border)s; padding: 8px; }
    ''' % c)


def main():
    from launcher import Window
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 10))
    window = Window(); window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
