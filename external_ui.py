"""Cancellable on-demand download and native install UI for third-party apps."""
from pathlib import Path
import threading
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QProgressBar
from PySide6.QtCore import Qt
from app import tool_styles
from external_apps import (get_release,select_package,download_package,install_package,app_storage,
                           launch_installed,InstallCancelled,cancelled)


class InstallTask(QThread):
    progress=Signal(object,str)
    phase=Signal(str)
    success=Signal(str)
    failure=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.stop_event=threading.Event();self.installing=False;self.lock=threading.Lock()
    def cancel(self):
        with self.lock:
            if self.installing:return False
            self.stop_event.set();return True
    def run(self):
        try:
            cancelled(self.stop_event);release=get_release();asset=select_package(release)
            self.phase.emit('download')
            package=download_package(release,asset,app_storage()/'downloads',self.stop_event,
                lambda value,text:self.progress.emit(value,text))
            with self.lock:
                cancelled(self.stop_event);self.installing=True
            self.phase.emit('install')
            self.progress.emit(None,'در حال نصب GenyConnect؛ تأیید دسترسی سیستم‌عامل را انجام دهید…')
            result=install_package(package,release);self.success.emit(str(result))
        except InstallCancelled:self.failure.emit('دریافت لغو شد؛ تغییری در نصب انجام نشد.')
        except Exception as exc:self.failure.emit(str(exc))


class ExternalDialog(QDialog):
    def __init__(self,manager):
        super().__init__(manager);self.manager=manager;self.task=None;self.pending_close=False
        self.setWindowTitle('GenyConnect');self.resize(490,250);self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        box=QVBoxLayout(self);box.setContentsMargins(26,26,26,26);box.setSpacing(16)
        title=QLabel('GenyConnect');title.setObjectName('pageTitle');box.addWidget(title)
        self.status=QLabel('در حال بررسی بستهٔ رسمی مناسب سیستم‌عامل…');self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.status)
        self.bar=QProgressBar();self.bar.setRange(0,0);self.bar.setTextVisible(False);self.bar.setFixedHeight(6);box.addWidget(self.bar)
        self.action=QPushButton('لغو دریافت');self.action.clicked.connect(self.action_clicked);box.addWidget(self.action)
        self.apply_theme()
    def apply_theme(self):self.setStyleSheet(tool_styles(self.manager.theme))
    def start(self):
        if self.task:return
        self.pending_close=False;self.bar.setRange(0,0);self.action.setText('لغو دریافت');self.action.setEnabled(True)
        self.status.setText('در حال بررسی بستهٔ رسمی مناسب سیستم‌عامل…')
        task=InstallTask(self);self.task=task
        task.progress.connect(self.progress);task.phase.connect(self.phase);task.success.connect(self.success)
        task.failure.connect(self.failed);task.finished.connect(self.worker_done);task.start()
    def progress(self,value,text):
        self.status.setText(text);self.bar.setRange(0,0 if value is None else 100)
        if value is not None:self.bar.setValue(round(value))
    def phase(self,value):
        self.manager.carousel.external_status=value;self.manager.carousel.update()
        if value=='install':self.action.setEnabled(False);self.action.setText('نصب در حال انجام…')
    def success(self,value):
        self.manager.refresh_external_state();self.progress(100,'GenyConnect نصب شد و آمادهٔ اجراست.')
        self.action.setText('بستن')
        if not self.manager.closing and not self.pending_close:
            try:launch_installed(Path(value))
            except Exception as exc:self.status.setText('نصب انجام شد؛ اجرای برنامه ناموفق بود: '+str(exc))
    def failed(self,text):
        self.status.setText(text);self.bar.setRange(0,100);self.bar.setValue(0);self.action.setText('تلاش دوباره')
    def worker_done(self):
        task=self.task;self.task=None;self.action.setEnabled(True)
        self.manager.carousel.external_status='';self.manager.refresh_external_state()
        if task:task.deleteLater()
        if self.pending_close:self.reject()
        self.manager.finish_close()
    def action_clicked(self):
        if self.task:self.reject()
        elif self.action.text()=='تلاش دوباره':self.start()
        else:self.reject()
    def reject(self):
        if self.task:
            if not self.task.cancel():
                self.status.setText('نصاب در حال اجراست؛ تا پایان نصب صبر کنید.');return
            self.pending_close=True;self.status.setText('در حال لغو دریافت…');self.action.setEnabled(False);return
        super().reject()
    def closeEvent(self,e):
        if self.task:self.reject();e.ignore()
        else:e.accept()
