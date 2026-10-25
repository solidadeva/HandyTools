"""Actual settings and update UI; network operations stay off the UI thread."""
import os
from pathlib import Path
import shutil
import sys
import threading

from PySide6.QtCore import Qt,QThread,Signal,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,
                               QProgressBar,QMessageBox,QFrame)
from app import tool_styles
from icons import set_button_icon, refresh_button_icons
from icons import IconComboBox as QComboBox
from updater import (latest_release,version_tuple,plan_update,stage_update,start_installer,UpdateCancelled)
from version import VERSION
from exe_updater import latest_exe_release, stage_exe_update, start_exe_installer
from mac_updater import latest_mac_release, stage_mac_update, staged_installer


class UpdateTask(QThread):
    result=Signal(object)
    failure=Signal(str)
    progress=Signal(object,str)

    def __init__(self,root,manifest=None,parent=None,executable=False,macos=False):
        super().__init__(parent);self.root=root;self.manifest=manifest;self.executable=executable;self.macos=macos;self.cancel_event=threading.Event()

    def run(self):
        try:
            if self.macos:
                if self.manifest is None:
                    manifest=latest_mac_release(self.cancel_event)
                    self.result.emit((manifest,dict(changed=[manifest['name']],bytes=manifest['size'])))
                else:
                    self.result.emit(stage_mac_update(self.manifest,self.cancel_event,
                        lambda percent,text:self.progress.emit(percent,text)))
            elif self.executable:
                if self.manifest is None:
                    manifest=latest_exe_release(self.cancel_event)
                    self.result.emit((manifest,dict(changed=[manifest['name']], bytes=manifest['size'])))
                else:
                    self.result.emit(stage_exe_update(self.manifest,self.cancel_event,
                        lambda percent,text:self.progress.emit(percent,text)))
            elif self.manifest is None:
                manifest=latest_release(self.cancel_event)
                plan=plan_update(self.root,manifest)
                self.result.emit((manifest,plan))
            else:
                self.result.emit(stage_update(self.root,self.manifest,plan_update(self.root,self.manifest),
                    self.cancel_event,lambda percent,text:self.progress.emit(percent,text)))
        except UpdateCancelled:
            self.failure.emit('بررسی یا دریافت آپدیت لغو شد.')
        except Exception as exc:
            self.failure.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(self,manager):
        super().__init__(manager)
        self.manager=manager;self.root=Path(__file__).resolve().parent
        self.macos=bool(getattr(sys,'frozen',False) and sys.platform=='darwin')
        self.executable=bool(getattr(sys,'frozen',False) and sys.platform!='darwin')
        self.task=None;self.manifest=None;self.stage=None;self.pending_close=False
        self.setWindowTitle('تنظیمات • Handy Tools App');self.resize(530,420);self.setMinimumWidth(430)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        box=QVBoxLayout(self);box.setContentsMargins(26,26,26,26);box.setSpacing(16)
        title=QLabel('تنظیمات');title.setObjectName('pageTitle');box.addWidget(title)
        box.addWidget(QLabel('ظاهر برنامه'))
        self.theme=QComboBox();self.theme.addItem('حالت تاریک','dark');self.theme.addItem('حالت روشن','light')
        self.theme.setCurrentIndex(0 if manager.theme=='dark' else 1)
        self.theme.currentIndexChanged.connect(self.change_theme);box.addWidget(self.theme)
        line=QFrame();line.setObjectName('separator');line.setFixedHeight(1);box.addWidget(line)
        box.addWidget(QLabel('به‌روزرسانی برنامه'))
        self.version_label=QLabel('نسخهٔ نصب‌شده: '+VERSION);box.addWidget(self.version_label)
        self.status=QLabel('فقط فایل‌های تغییرکرده دریافت می‌شوند؛ FFmpeg و فایل‌های شما حفظ می‌شوند.')
        self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.status)
        self.bar=QProgressBar();self.bar.setRange(0,100);self.bar.setValue(0);self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6);box.addWidget(self.bar)
        row=QHBoxLayout()
        self.action=QPushButton('بررسی آپدیت');self.action.setObjectName('primary');self.action.clicked.connect(self.action_clicked)
        self.cancel=QPushButton('لغو دریافت');self.cancel.setEnabled(False);self.cancel.clicked.connect(self.cancel_task)
        row.addWidget(self.action,1);row.addWidget(self.cancel);box.addLayout(row)
        set_button_icon(self.action, "refresh"); set_button_icon(self.cancel, "close")
        self.apply_theme()
        if self.macos:
            self.status.setText('نسخهٔ جدید مخصوص مک شما دریافت و بررسی می‌شود؛ نصب با کشیدن برنامه به Applications انجام می‌شود.')
        elif self.executable:
            self.status.setText('نسخهٔ جدید EXE دریافت و بررسی می‌شود؛ پس از نصب، برنامه دوباره باز می‌شود. FFmpeg، تنظیمات و فایل‌های شما حفظ می‌شوند.')

    def apply_theme(self):
        self.setStyleSheet(tool_styles(self.manager.theme))
        refresh_button_icons(self, self.manager.theme)
        target=0 if self.manager.theme=='dark' else 1
        self.theme.blockSignals(True);self.theme.setCurrentIndex(target);self.theme.blockSignals(False)

    def change_theme(self):
        desired=self.theme.currentData()
        if desired!=self.manager.theme:
            self.manager.toggle_theme()
        self.apply_theme()

    def action_clicked(self):
        if self.task:
            return
        if self.stage:
            if self.manager.setup_task or self.manager.external_busy() or any(p.is_busy() for p in self.manager.pages()):
                self.status.setText('ابتدا عملیات فعال را تمام یا لغو کنید؛ سپس نصب آپدیت را بزنید.');return
            try:
                if self.macos:
                    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(staged_installer(self.stage)))):
                        raise RuntimeError('نصاب مک باز نشد؛ دوباره تلاش کنید.')
                elif self.executable:
                    start_exe_installer(Path(sys.executable),self.stage,os.getpid())
                else:
                    start_installer(self.root,self.stage,os.getpid())
            except Exception as exc:
                self.status.setText(str(exc));return
            self.stage=None  # ownership transferred to the separate installer
            self.accept();self.manager.close();return
        self.action.setEnabled(False);self.cancel.setEnabled(True);self.bar.setRange(0,0)
        self.status.setText('در حال بررسی آخرین انتشار…' if self.manifest is None else 'در حال دریافت بستهٔ مک…' if self.macos else 'در حال دریافت نسخهٔ جدید EXE…' if self.executable else 'در حال دریافت فایل‌های تغییرکرده…')
        task=UpdateTask(self.root,self.manifest,self,executable=self.executable,macos=self.macos);self.task=task
        task.result.connect(self.received);task.failure.connect(self.failed)
        task.progress.connect(self.progress);task.finished.connect(self.worker_done);task.start()

    def progress(self,value,text):
        self.status.setText(text);self.bar.setRange(0,100);self.bar.setValue(round(value))

    def received(self,result):
        if isinstance(result,tuple):
            manifest,plan=result
            if version_tuple(manifest['version'])<=version_tuple(VERSION):
                self.manifest=None;self.status.setText('برنامه به‌روز است.');return
            self.manifest=manifest
            self.status.setText('نسخهٔ '+manifest['version']+' آماده است. '+
                ('دریافت بستهٔ کامل، حدود '+f"{plan['bytes']/1048576:.1f}"+' مگابایت.' if self.executable or self.macos else
                 str(len(plan['changed']))+' فایل، حدود '+f"{plan['bytes']/1024:.1f}"+' کیلوبایت دریافت می‌شود.')+
                ' پس از نصب، برنامه دوباره باز می‌شود.')
            if 'requirements.txt' in plan['changed']:
                self.status.setText(self.status.text()+' وابستگی‌های جدید نیز در صورت نیاز دریافت می‌شوند.')
            self.action.setText('دریافت آپدیت')
        else:
            self.stage=Path(result);self.status.setText('فایل‌ها دریافت و بررسی شدند. برای نصب، برنامه بسته و دوباره باز می‌شود.')
            self.action.setText('باز کردن نصاب مک' if self.macos else 'نصب و راه‌اندازی مجدد');self.bar.setValue(100)
            if self.macos:self.status.setText('بسته بررسی شد. نصاب را باز کنید و برنامه را به Applications بکشید؛ سپس نسخهٔ نصب‌شده را اجرا کنید.')

    def failed(self,text):
        self.status.setText('آپدیت انجام نشد: '+text)

    def worker_done(self):
        task=self.task;self.task=None;self.action.setEnabled(True);self.cancel.setEnabled(False)
        self.bar.setRange(0,100)
        if task:
            task.deleteLater()
        if self.pending_close:
            self.reject()
        self.manager.finish_close()

    def cancel_task(self):
        if self.task:
            self.task.cancel_event.set();self.cancel.setEnabled(False);self.status.setText('در حال لغو…')

    def reject(self):
        if self.task:
            self.pending_close=True;self.cancel_task();return
        if self.stage:
            shutil.rmtree(self.stage,ignore_errors=True);self.stage=None
        super().reject()

    def closeEvent(self,e):
        if self.task:
            self.pending_close=True;self.cancel_task();e.ignore()
        else:
            self.reject();e.accept()
