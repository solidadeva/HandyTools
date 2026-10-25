import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QMimeData, QUrl, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from launcher import Window, ToolSpec, ToolWindow
from workers import Task, validate_url, parse_report


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from icons import IconStyle
        cls.app.setStyle(IconStyle('Fusion'))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.settings = QSettings(str(self.folder/'settings.ini'), QSettings.Format.IniFormat)
        self.w = Window(self.settings)
        self.w.show(); self.app.processEvents()
        self.addCleanup(self.w.close)

    def wait_until(self, predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertTrue(predicate(), 'timed out')

    def test_launcher_theme_and_state(self):
        self.assertEqual(self.w.carousel.selected, 0)
        screen = self.w.screen().availableGeometry()
        self.assertLess((self.w.frameGeometry().center()-screen.center()).manhattanLength(), 4)
        QTest.keyClick(self.w, Qt.Key.Key_Right)
        self.assertEqual(self.w.carousel.selected, 1)
        QTest.keyClick(self.w, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertTrue(self.w.windows['converter'].isVisible())
        converter = self.w.windows['converter']
        converter.page.folder.setText(str(self.folder))
        self.assertIs(self.w.open_tool('converter'), converter)
        downloader = self.w.open_tool('downloader')
        self.assertIsNot(converter, downloader)
        self.assertTrue(converter.isWindow() and downloader.isWindow())
        for _ in range(2):
            self.w.toggle_theme(); self.app.processEvents()
            self.assertFalse(self.w.grab().isNull())
            self.assertEqual(converter.page.folder.text(), str(self.folder))
        self.w.toggle_theme(); self.settings.sync()
        self.assertEqual(QSettings(self.settings.fileName(), QSettings.Format.IniFormat).value('theme'), 'light')
        converter.close(); self.app.processEvents()
        self.assertTrue(self.w.isVisible())
        self.assertFalse(converter.isVisible())
        self.assertIs(self.w.open_tool('converter'), converter)

    def test_carousel_mouse_drag_wheel_and_future_apps(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QWheelEvent
        carousel = self.w.carousel
        # Clicking the actual app tile opens an independent tool window.
        QTest.mouseClick(carousel, Qt.MouseButton.LeftButton, pos=carousel.item_rect(0).center().toPoint())
        self.assertTrue(self.w.windows['downloader'].isVisible())
        QTest.mouseClick(carousel, Qt.MouseButton.LeftButton, pos=carousel.arrow_rect(True).center().toPoint())
        self.assertEqual(carousel.selected, 1)
        QTest.mouseClick(carousel, Qt.MouseButton.LeftButton, pos=carousel.arrow_rect(True).center().toPoint())
        self.assertEqual(carousel.selected, 2)
        QTest.mouseClick(carousel, Qt.MouseButton.LeftButton, pos=carousel.arrow_rect(True).center().toPoint())
        self.assertEqual(carousel.selected, 0)
        QTest.mousePress(carousel, Qt.MouseButton.LeftButton, pos=QPoint(600,230))
        QTest.mouseRelease(carousel, Qt.MouseButton.LeftButton, pos=QPoint(480,230))
        self.assertEqual(carousel.selected, 1)
        wheel = QWheelEvent(QPointF(100,100), QPointF(100,100), QPoint(0,0), QPoint(0,-120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
        carousel.wheelEvent(wheel)
        self.assertEqual(carousel.selected, 2)
        carousel.select(0)
        initial_count=len(carousel.tools)
        for i in range(7):
            self.w.register_tool(ToolSpec('extra'+str(i),'Extra '+str(i),'convert','#8879cc','convert'), ToolWindow)
        self.assertEqual(len(carousel.tools), initial_count+7)
        last=len(carousel.tools)-1
        carousel.select(last); QTest.qWait(260)
        self.assertEqual(carousel.offset, len(carousel.tools)-3)
        self.assertTrue(carousel.rect().contains(carousel.item_rect(last).center().toPoint()))
        carousel.step(1); self.assertEqual(carousel.selected, 0)
        with self.assertRaises(ValueError):
            self.w.register_tool(carousel.tools[0], ToolWindow)

    def test_real_settings_update_check_and_saved_resize(self):
        QTest.mouseClick(self.w.settings_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        dialog=self.w.settings_dialog
        self.assertTrue(dialog.isVisible())
        dialog.theme.setCurrentIndex(1)
        self.assertEqual(self.w.theme,'light')
        self.w.resize(600,280);self.app.processEvents()
        self.assertEqual([int(n) for n in self.settings.value('launcher_size')],[600,280])
        self.assertTrue(self.w.resize_grip.isVisible())
        with patch('update_ui.latest_release',return_value={'version':'0.5.0'}), patch('update_ui.plan_update',return_value={'changed':['app.py'],'bytes':1024}):
            QTest.mouseClick(dialog.action,Qt.MouseButton.LeftButton)
            self.wait_until(lambda:dialog.task is None)
        self.assertIn('0.5.0',dialog.status.text())
        self.assertEqual(dialog.action.text(),'دریافت آپدیت')
        dialog.close()

    def test_window_controls_and_triangle_pulse(self):
        normal=self.w.size()
        QTest.mouseClick(self.w.maximize_button,Qt.MouseButton.LeftButton)
        self.app.processEvents();self.assertTrue(self.w.isMaximized())
        self.assertFalse(self.w.resize_grip.isVisible())
        QTest.mouseClick(self.w.maximize_button,Qt.MouseButton.LeftButton)
        self.app.processEvents();self.assertFalse(self.w.isMaximized())
        self.assertEqual(self.w.size(),normal)
        self.assertEqual(self.w.resize_grip.pulse.duration(),5000)
        self.w.resize_grip.pulse.setCurrentTime(0);dim=self.w.resize_grip.get_pulse()
        self.w.resize_grip.pulse.setCurrentTime(2500)
        self.assertGreater(self.w.resize_grip.get_pulse(),dim)

    def test_genyconnect_is_on_demand_and_opens_installed_app(self):
        from external_ui import InstallTask
        spec=next(x for x in self.w.carousel.tools if x.id=='genyconnect')
        self.assertTrue(spec.external)
        self.assertNotIn('genyconnect',self.w.carousel.installed_ids)
        def fake_install(task):
            task.phase.emit('download');task.failure.emit('test offline')
        with patch.object(InstallTask,'run',fake_install):
            self.w.open_tool('genyconnect')
            self.wait_until(lambda:not self.w.external_busy())
        self.assertTrue(self.w.external_dialog.isVisible())
        self.assertIn('test offline',self.w.external_dialog.status.text())
        self.w.external_dialog.close()
        installed=self.folder/'GenyConnect.exe';installed.write_bytes(b'app')
        with patch('external_apps.detect_installed',return_value=installed), patch('external_apps.launch_installed') as launch:
            self.w.open_tool('genyconnect');launch.assert_called_once_with(installed)
        self.assertIn('genyconnect',self.w.carousel.installed_ids)
        task=InstallTask();self.assertTrue(task.cancel())
        task=InstallTask();task.installing=True;self.assertFalse(task.cancel())

    def test_drop_paths_and_reject_multiple_or_disabled(self):
        source = self.folder/'فایل فارسی with spaces.txt'; source.write_text('test')
        page = self.w.open_tool('converter').page
        pick = page.pick
        def drop(paths):
            data = QMimeData(); data.setUrls([QUrl.fromLocalFile(str(x)) for x in paths])
            e = QDropEvent(QPointF(10,10), Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            pick.dropEvent(e)
        drop([source, source]); self.assertIsNone(page.source)
        drop([source]); self.assertEqual(page.source, source)
        second = self.folder/'second.txt'; second.write_text('x')
        pick.setEnabled(False); drop([second]); self.assertEqual(page.source, source)
        self.assertEqual(page.folder.text(), str(source.parent))

    def test_real_conversion_navigation_and_history(self):
        from engine import inspect
        source = self.folder/'ویدیو source.mkv'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=12:duration=1',
                        '-f','lavfi','-i','sine=duration=1','-c:v','ffv1','-c:a','pcm_s16le',str(source)], check=True)
        p = self.w.open_tool('converter').page; p.set_source(str(source)); p.start()
        self.assertTrue(p.is_busy()); self.assertFalse(p.pick.isEnabled())
        self.w.open_tool('downloader'); self.w.toggle_theme(); self.w.raise_()
        self.wait_until(lambda: not p.is_busy())
        self.assertTrue(p.output.is_file()); self.assertTrue(p.open_button.isEnabled())
        streams = inspect(p.output)['streams']
        self.assertEqual(streams[0]['codec_name'], 'h264')
        self.assertEqual(streams[0]['pix_fmt'], 'yuv420p')
        self.assertEqual(streams[1]['codec_name'], 'aac')
        self.assertEqual(len(self.w.history), 1)
        output = p.output; self.w.clear_recent(); self.assertTrue(output.is_file())

    def test_output_buttons_open_paths_and_report_errors(self):
        page = self.w.open_tool('downloader').page
        page.folder.setText(str(self.folder))
        self.assertTrue(page.open_button.isEnabled())  # usable before the download completes
        self.assertFalse(page.open_file_button.isEnabled())
        with patch('app.sys.platform', 'win32'), patch('app.os.startfile', create=True) as opened:
            QTest.mouseClick(page.open_button, Qt.MouseButton.LeftButton)
            opened.assert_called_once_with(str(self.folder.resolve()))
        output = self.folder / 'خروجی with spaces & [video].mp4'
        output.write_bytes(b'output')
        page.success(str(output))
        # Editing the next destination must not redirect the previous result's folder.
        page.folder.setText(str(self.folder / 'missing'))
        with patch('app.QDesktopServices.openUrl', return_value=True) as opened:
            QTest.mouseClick(page.open_file_button, Qt.MouseButton.LeftButton)
            QTest.mouseClick(page.open_button, Qt.MouseButton.LeftButton)
            self.assertEqual([x.args[0].toLocalFile() for x in opened.call_args_list],
                             [str(output.resolve()), str(self.folder.resolve())])
        with patch('app.QDesktopServices.openUrl', return_value=False), patch('app.QMessageBox.warning') as warning:
            page.open_file(); warning.assert_called_once()
        with patch('app.sys.platform', 'win32'), patch('app.os.startfile', create=True, side_effect=OSError('association missing')), patch('app.QMessageBox.warning') as warning:
            page.open_file(); warning.assert_called_once()
        output.unlink()
        with patch('app.QMessageBox.warning') as warning:
            page.open_file(); warning.assert_called_once()
        self.assertFalse(page.open_file_button.isEnabled())
        for _ in range(2):
            QTest.mouseClick(page.details, Qt.MouseButton.LeftButton)
            self.assertEqual(page.details.isChecked(), not page.log.isHidden())

    def test_vector_icons_render_at_native_dpi_and_follow_theme(self):
        from icons import ART, app_icon
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        for name in ART:
            icon = app_icon(name, '#007aff')
            for scale in (1, 1.25, 1.5, 2, 3):
                pm = icon.pixmap(QSize(24,24), scale)
                self.assertFalse(pm.isNull(), name)
                self.assertEqual(pm.width(), round(24*scale), name)
                self.assertEqual(pm.devicePixelRatio(), scale, name)
            normal = icon.pixmap(QSize(24,24)).toImage()
            disabled = icon.pixmap(QSize(24,24), QIcon.Mode.Disabled).toImage()
            self.assertGreater(sum(normal.pixelColor(x,y).alpha() for x in range(24) for y in range(24)),
                               sum(disabled.pixelColor(x,y).alpha() for x in range(24) for y in range(24)))
        page = self.w.open_tool('downloader').page
        before = page.open_button.icon().pixmap(24,24).toImage()
        self.w.toggle_theme()
        self.assertNotEqual(before, page.open_button.icon().pixmap(24,24).toImage())

    def test_worker_failure_and_cancel_signals(self):
        task = Task('convert', dict(source='missing-file', folder=str(self.folder), format='MP4'))
        errors = []; task.failed.connect(errors.append)
        task.start(); self.wait_until(lambda: not task.isRunning()); self.app.processEvents()
        self.assertEqual(len(errors), 1)
        cancelled = []
        task = Task('convert', {}); task.cancel(); task.cancelled.connect(lambda: cancelled.append(True))
        task.start(); self.wait_until(lambda: not task.isRunning()); self.app.processEvents()
        self.assertEqual(cancelled, [True])

    def test_url_and_engine_reports(self):
        for good in ['https://www.youtube.com/watch?v=abc&x=2', 'http://example.com/video']:
            self.assertTrue(validate_url(good))
        for bad in ['file:///c:/a.mp4', 'https://', 'https://[', 'powershell.exe', 'javascript:alert(1)']:
            self.assertFalse(validate_url(bad))
        self.assertEqual(parse_report('DL| 42.5%|2MiB/s|00:04')[1][0], 42.5)
        self.assertEqual(parse_report('DL| NA|NA|NA')[1][0], None)
        self.assertEqual(parse_report('CV|51.7')[1][0], 51.7)
        self.assertEqual(parse_report('FILE|C:\\ویدیو with spaces.mp4'), ('file', 'C:\\ویدیو with spaces.mp4'))


if __name__ == '__main__':
    unittest.main()
