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
from icons import set_button_icon, refresh_button_icons, IconStyle
from icons import IconComboBox as QComboBox

DARK = dict(bg='#1c1c1e', side='#242426', card='#2c2c2e', hover='#3a3a3c', text='#f5f5f7',
            muted='#a1a1a6', border='#444446', accent='#0a84ff', ink='#ffffff', input='#242426', hero='#303034')
LIGHT = dict(bg='#f5f5f7', side='#f2f2f4', card='#ffffff', hover='#e8e8ed', text='#1d1d1f',
             muted='#6e6e73', border='#d9d9df', accent='#007aff', ink='#ffffff', input='#ffffff', hero='#eaf3ff')


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
        result = QFrame(); result.setObjectName('resultPanel')
        resultbox = QVBoxLayout(result); resultbox.setContentsMargins(18, 16, 18, 16); resultbox.setSpacing(12)
        self.status = label('آماده', 'resultStatus', True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        resultbox.addWidget(self.status)
        self.output_name = label('فایل آماده‌شده اینجا نمایش داده می‌شود.', 'muted', True)
        self.output_name.setTextFormat(Qt.TextFormat.PlainText)
        self.output_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.output_name.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        resultbox.addWidget(self.output_name)
        resultactions = QHBoxLayout(); resultactions.setSpacing(10)
        self.open_button = button('پوشهٔ خروجی', self.open_folder)
        self.open_file_button = button('باز کردن فایل', self.open_file)
        self.open_file_button.setEnabled(False)
        resultactions.addWidget(self.open_button); resultactions.addWidget(self.open_file_button)
        if kind == 'download':
            self.details = button('نمایش جزئیات', self.toggle_log)
            self.details.setCheckable(True)
            resultactions.addWidget(self.details)
        resultactions.addStretch()
        resultbox.addLayout(resultactions); box.addWidget(result)
        if kind == 'download':
            self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(500)
            self.log.setLayoutDirection(Qt.LayoutDirection.LeftToRight); self.log.setMaximumHeight(150)
            self.log.hide(); box.addWidget(self.log)
            set_button_icon(self.details, 'details')
            set_button_icon(self.update, 'refresh')
        else:
            set_button_icon(self.pick, 'upload'); set_button_icon(self.reset, 'refresh')
        for control, glyph in ((self.browse, 'folder'), (self.open_button, 'folder'),
                               (self.open_file_button, 'file'), (self.cancel_button, 'close'),
                               (self.start_button, kind)):
            set_button_icon(control, glyph)
        self.folder.textChanged.connect(self.refresh_output_actions)
        self.refresh_output_actions()
        refresh_button_icons(self, window.theme)
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
        self.details.setChecked(show)

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
        self.output = None; self.refresh_output_actions()
        self.output_name.setText('پس از پایان عملیات، فایل آماده‌شده اینجا نمایش داده می‌شود.')
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
            self.status.setText(('دریافت کامل شد؛ در حال نهایی‌سازی فایل…' if self.kind == 'download' and text.startswith('دانلود') and value >= 100 else text) + f'  •  {value:.0f}%')

    def success(self, value):
        self.output = Path(value) if value else None
        self.progress(100, 'فایل آماده شد' if value else 'موتور دانلود به‌روز شد')
    self.refresh_output_actions()
        self.output_name.setText(self.output.name if self.output else 'موتور دانلود آمادهٔ استفاده است.')
        self.output_name.setToolTip(str(self.output or ''))
        if value:
            self.window.record(self.kind, value)

    def failure(self, text):
        self.status.setText('عملیات انجام نشد؛ جزئیات خطا را بررسی کنید.')
        if self.kind == 'download':
            self.log.appendPlainText(text); self.log.show(); self.details.setText('بستن جزئیات'); self.details.setChecked(True)
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

    def refresh_output_actions(self):
        folder = self.output.parent if self.output else Path(self.folder.text()) if self.folder.text().strip() else None
        self.open_button.setEnabled(bool(folder and folder.is_dir()))
        self.open_button.setToolTip(str(folder) if folder else 'ابتدا پوشهٔ خروجی را انتخاب کنید.')
        self.open_file_button.setEnabled(bool(self.output and self.output.is_file()))

    def open_path(self, path):
        try:
            if not path or not path.exists():
                raise OSError('این مسیر دیگر وجود ندارد؛ ممکن است فایل یا پوشه جابه‌جا شده باشد.')
            # Shell association handles Windows Unicode paths and Explorer reliably.
            if sys.platform == 'win32':
                os.startfile(str(path.resolve()))
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
                raise OSError('سیستم‌عامل نتوانست این مسیر را باز کند.')
        except OSError as exc:
            self.refresh_output_actions()
            QMessageBox.warning(self, 'باز کردن خروجی', str(exc))

    def open_folder(self):
        folder = self.output.parent if self.output else Path(self.folder.text()) if self.folder.text().strip() else None
        self.open_path(folder)

    def open_file(self):
        self.open_path(self.output)


def tool_styles(theme):
    c = DARK if theme == 'dark' else LIGHT
    return ('''
        QWidget { background: %(bg)s; color: %(text)s; font-family: 'Segoe UI Variable', 'Segoe UI', 'Noto Sans Arabic'; font-size: 13px; }
        QScrollArea { border: none; }
        QLabel { background: transparent; }
        QLabel#muted { color: %(muted)s; font-size: 12px; }
        QLabel#pageTitle { font-size: 25px; font-weight: 600; letter-spacing: -0.5px; }
        QLabel#section { font-size: 12px; font-weight: 600; color: %(muted)s; }
        QFrame#resultPanel { background: %(card)s; border: 1px solid %(border)s; border-radius: 16px; }
        QFrame#resultPanel QLabel { background: transparent; }
        QLabel#resultStatus { font-weight: 600; }
        QPushButton:checked { background: %(hover)s; border-color: %(accent)s; }
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
        QComboBox::down-arrow { image: none; width: 0px; height: 0px; }
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


def main(smoke_report=None):
    from launcher import Window
    app = QApplication(sys.argv)
    app.setStyle(IconStyle('Fusion'))
    app.setFont(QFont('Segoe UI', 10))
    if smoke_report:
        import json
        import tempfile
        from icons import ART, app_icon
        import pillow_heif
        from workers import resource_path
        with tempfile.TemporaryDirectory(prefix='handy-smoke-') as temp:
            window = Window(QSettings(str(Path(temp)/'settings.ini'), QSettings.Format.IniFormat), prepare=False)
            window.show()
            for name in ART:
                if app_icon(name).pixmap(32,32).isNull():
                    raise RuntimeError('Cannot render bundled icon: ' + name)
            if app_icon('genyconnect').pixmap(64,64).isNull():
                raise RuntimeError('Bundled GenyConnect icon is missing.')
            for name in ('downloader/Engine.ps1', 'downloader/Compatibility.ps1', 'downloader/ExeUpdate.ps1'):
                if not resource_path(name).is_file():
                    raise RuntimeError('Bundled resource is missing: ' + name)
            for name in ('converter', 'downloader'):
                tool_window = window.open_tool(name)
                if tool_window.grab().isNull():
                    raise RuntimeError('Cannot render bundled tool: ' + name)
            window.open_settings()
            if not window.settings_dialog.action.isEnabled():
                raise RuntimeError('Update checking is disabled in this build.')
            window.toggle_theme()
            app.processEvents()
            QTimer.singleShot(max(250,min(10000,int(os.environ.get('HANDY_SMOKE_DELAY_MS','250')))), window.close)
            result = app.exec()
            if result == 0:
                Path(smoke_report).write_text(json.dumps(dict(version=__import__('version').VERSION,
                    frozen=bool(getattr(sys,'frozen',False)), ok=True)), encoding='utf-8')
            return result
    window = Window(); window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
