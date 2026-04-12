#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import ctypes
import ctypes.wintypes
import json
import time
from datetime import datetime

try:
    import psutil
except ImportError:
    print("请安装: pip install psutil")
    sys.exit(1)

try:
    from PyQt5.QtCore import QTimer, Qt, QRect, QRectF, QPropertyAnimation, QEasingCurve
    from PyQt5.QtGui import (
        QPainterPath, QRegion, QFont, QIcon, QPixmap, QPainter, QColor,
        QPalette, QFontMetrics, QFontDatabase, QTextDocument
    )
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QHBoxLayout, QLabel, QVBoxLayout,
        QSystemTrayIcon, QMenu, QAction, QCheckBox, QSlider, QPushButton,
        QGroupBox, QFormLayout, QFrame, QStyleFactory, QMessageBox,
        QColorDialog, QLineEdit, QListWidget, QDialog, QAbstractItemView,
        QScrollArea
    )
    from PyQt5.QtNetwork import QLocalServer, QLocalSocket
except ImportError:
    print("请安装: pip install PyQt5")
    sys.exit(1)

# --------------------------
# Windows API
# --------------------------
user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

def get_foreground_window():
    return user32.GetForegroundWindow()

def get_window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom

def get_window_thread_process_id(hwnd):
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

def is_window_fullscreen(hwnd):
    if not hwnd:
        return False
    try:
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        style = user32.GetWindowLongW(hwnd, -16)
        if style & 0x00C00000:
            return False
        monitor = user32.MonitorFromWindow(hwnd, 2)
        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.DWORD),
                ("rcMonitor", ctypes.wintypes.RECT),
                ("rcWork", ctypes.wintypes.RECT),
                ("dwFlags", ctypes.wintypes.DWORD),
            ]
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(monitor, ctypes.byref(mi))
        mw = mi.rcMonitor.right - mi.rcMonitor.left
        mh = mi.rcMonitor.bottom - mi.rcMonitor.top
        return w >= mw and h >= mh
    except:
        return False

# --------------------------
# 配置文件（固定使用用户文档目录，确保可见）
# --------------------------
def get_config_path():
    # 使用 Documents 目录，默认不隐藏
    user_profile = os.path.expanduser("~")
    config_dir = os.path.join(user_profile, "Documents", "FloatingWindowMonitor")
    config_file = os.path.join(config_dir, "config.json")
    return config_dir, config_file

CONFIG_DIR, CONFIG_FILE = get_config_path()

DEFAULT_CONFIG = {
    "show_name": True,
    "show_pid": True,
    "show_cpu": True,
    "show_memory": True,
    "show_time": True,
    "show_date": False,
    "show_system_component": False,
    "opacity": 170,
    "corner_radius": 6,
    "dark_mode": True,
    "scroll_speed": 5,
    "remarks": []
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in loaded:
                        loaded[k] = v
                return loaded
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config, silent=False):
    for attempt in range(3):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            # 强制弹窗告知成功路径（便于用户直接打开）
            QMessageBox.information(
                None, "配置已保存",
                f"配置文件保存成功！\n\n路径：{CONFIG_FILE}\n\n点击确定后，程序将应用设置。"
            )
            return True
        except Exception as e:
            if attempt == 2:
                QMessageBox.critical(
                    None, "保存失败",
                    f"无法写入配置文件！\n\n路径：{CONFIG_FILE}\n错误：{str(e)}\n\n"
                    "请检查磁盘空间或关闭占用该文件的程序。"
                )
            time.sleep(0.5)
    return False

def is_system_component(pid):
    try:
        p = psutil.Process(pid)
        un = p.username().lower()
        if un in ('nt authority\\system', 'nt authority\\local service', 'nt authority\\network service'):
            return True
        exe = p.exe().lower()
        if exe.startswith(('c:\\windows\\system32', 'c:\\windows\\syswow64')):
            return True
    except:
        pass
    return False

# --------------------------
# 滚动标签
# --------------------------
class ScrollingLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_html = ""
        self.plain_text = ""
        self.offset = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self.step)
        self.scroll_speed = 5
        self.scroll_enabled = False
        self.text_width = 0
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:transparent;")
        font = QFont("Microsoft YaHei", 9)
        if not font.exactMatch():
            font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
            font.setPointSize(9)
        self.setFont(font)

    def setText(self, text):
        self.full_html = text
        import re
        self.plain_text = re.sub(r'<[^>]+>', '', text)
        self.update_text_width()
        was_enabled = self.scroll_enabled
        self.check_enable()
        if not was_enabled or not self.scroll_enabled:
            self.offset = 0.0
        super().setText(text)
        self.update()

    def setScrollSpeed(self, s):
        self.scroll_speed = max(1, min(10, s))

    def update_text_width(self):
        fm = QFontMetrics(self.font())
        self.text_width = fm.horizontalAdvance(self.plain_text)

    def check_enable(self):
        if self.width() <= 10 or not self.plain_text:
            self.scroll_enabled = False
            self.setAlignment(Qt.AlignCenter)
            self.timer.stop()
            return
        if self.text_width > self.width() - 20:
            self.scroll_enabled = True
            self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if not self.timer.isActive():
                self.timer.start(30)
        else:
            self.scroll_enabled = False
            self.setAlignment(Qt.AlignCenter)
            self.timer.stop()

    def step(self):
        if not self.scroll_enabled:
            return
        step = max(0.5, self.scroll_speed / 4.0)
        self.offset += step
        if self.offset >= self.text_width + 50:
            self.offset = -self.width()
        self.update()

    def paintEvent(self, event):
        if not self.scroll_enabled:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QColor(255, 255, 255))
        doc = QTextDocument()
        doc.setHtml(self.full_html)
        doc.setDefaultFont(self.font())
        doc.setTextWidth(100000)
        doc_height = doc.size().height()
        r = self.rect()
        y = (r.height() - doc_height) / 2
        painter.save()
        painter.translate(-self.offset, y)
        doc.drawContents(painter, QRectF(0, 0, doc.idealWidth(), doc_height))
        painter.restore()

    def resizeEvent(self, e):
        self.update_text_width()
        self.check_enable()
        super().resizeEvent(e)

# --------------------------
# 备注编辑对话框
# --------------------------
class RemarkEditDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data or {}
        self.setWindowTitle("编辑备注")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.resize(400, 300)
        self.text_color = self.data.get("textColor", "#FFFFFF")
        self.bg_color = self.data.get("bgColor", "#2A2A2A")
        self.initUI()

    def initUI(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.edit_proc = QLineEdit()
        self.edit_proc.setText(self.data.get("proc", ""))
        self.edit_proc.setPlaceholderText("如 chrome.exe")
        layout.addRow("进程名:", self.edit_proc)

        self.edit_remark = QLineEdit()
        self.edit_remark.setText(self.data.get("remark", ""))
        self.edit_remark.setPlaceholderText("备注文字")
        layout.addRow("备注:", self.edit_remark)

        self.btn_text_color = QPushButton()
        self.btn_text_color.setFixedSize(60, 30)
        self.btn_text_color.setStyleSheet(f"background-color: {self.text_color}; border:1px solid #888;")
        self.btn_text_color.clicked.connect(self.pick_text_color)
        layout.addRow("文字颜色:", self.btn_text_color)

        self.btn_bg_color = QPushButton()
        self.btn_bg_color.setFixedSize(60, 30)
        self.btn_bg_color.setStyleSheet(f"background-color: {self.bg_color}; border:1px solid #888;")
        self.btn_bg_color.clicked.connect(self.pick_bg_color)
        layout.addRow("背景颜色:", self.btn_bg_color)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addRow(btn_box)

    def pick_text_color(self):
        color = QColorDialog.getColor(QColor(self.text_color), self, "选择文字颜色")
        if color.isValid():
            self.text_color = color.name().upper()
            self.btn_text_color.setStyleSheet(f"background-color: {self.text_color}; border:1px solid #888;")

    def pick_bg_color(self):
        color = QColorDialog.getColor(QColor(self.bg_color), self, "选择背景颜色")
        if color.isValid():
            self.bg_color = color.name().upper()
            self.btn_bg_color.setStyleSheet(f"background-color: {self.bg_color}; border:1px solid #888;")

    def get_data(self):
        return {
            "proc": self.edit_proc.text().strip(),
            "remark": self.edit_remark.text().strip(),
            "textColor": self.text_color,
            "bgColor": self.bg_color
        }

# --------------------------
# 备注管理窗口
# --------------------------
class RemarkManagerDialog(QDialog):
    def __init__(self, remarks, parent=None):
        super().__init__(parent)
        self.remarks = remarks.copy()
        self.setWindowTitle("程序备注管理")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.resize(500, 400)
        self.initUI()
        self.refresh_list()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_add = QPushButton("添加")
        btn_edit = QPushButton("修改")
        btn_delete = QPushButton("删除")
        btn_save = QPushButton("保存并关闭")
        btn_cancel = QPushButton("取消")

        btn_add.clicked.connect(self.add_remark)
        btn_edit.clicked.connect(self.edit_remark)
        btn_delete.clicked.connect(self.delete_remark)
        btn_save.clicked.connect(self.save_and_close)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def refresh_list(self):
        self.list_widget.clear()
        for r in self.remarks:
            item_text = f"{r['proc']} — {r['remark']} (文字:{r['textColor']} / 背景:{r['bgColor']})"
            self.list_widget.addItem(item_text)

    def add_remark(self):
        dlg = RemarkEditDialog(self)
        if dlg.exec_():
            self.remarks.append(dlg.get_data())
            self.refresh_list()

    def edit_remark(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            dlg = RemarkEditDialog(self, self.remarks[row])
            if dlg.exec_():
                self.remarks[row] = dlg.get_data()
                self.refresh_list()

    def delete_remark(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            del self.remarks[row]
            self.refresh_list()

    def save_and_close(self):
        self.accept()

    def get_remarks(self):
        return self.remarks

# --------------------------
# 设置窗口（可拖动）
# --------------------------
class SettingsWindow(QWidget):
    def __init__(self, cfg, callback, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.callback = callback
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(460, 580)
        self.remarks = cfg.get("remarks", [])
        self.drag_pos = None
        self.initUI()

    def initUI(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        title = QFrame()
        title.setFixedHeight(45)
        title.setStyleSheet("""
            QFrame {
                background: #2d2d2d;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
        """)
        tlay = QHBoxLayout(title)
        tlay.setContentsMargins(20, 0, 15, 0)

        title_label = QLabel("⚙️ 设置")
        title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        tlay.addWidget(title_label)
        tlay.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #c42b1c;
                border-radius: 6px;
            }
        """)
        close_btn.clicked.connect(self.close)
        tlay.addWidget(close_btn)
        main.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: #3c3c3c; border: none; }")
        content = QFrame()
        content.setStyleSheet("background: #3c3c3c; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        clayout = QVBoxLayout(content)
        clayout.setSpacing(20)
        clayout.setContentsMargins(24, 20, 24, 24)

        g1 = QGroupBox("📺 显示项")
        g1.setStyleSheet("""
            QGroupBox {
                color: white;
                font-weight: bold;
                border: 1px solid #5a5a5a;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; }
        """)
        g1lay = QVBoxLayout(g1)
        self.cb_name = QCheckBox("程序名称")
        self.cb_pid  = QCheckBox("PID")
        self.cb_cpu  = QCheckBox("CPU 占用")
        self.cb_mem  = QCheckBox("内存占用")
        self.cb_time = QCheckBox("时间")
        self.cb_date = QCheckBox("日期")
        self.cb_sys  = QCheckBox("系统组件标识")
        for cb in [self.cb_name, self.cb_pid, self.cb_cpu, self.cb_mem, self.cb_time, self.cb_date, self.cb_sys]:
            cb.setStyleSheet("color: #f0f0f0; spacing: 8px;")
            g1lay.addWidget(cb)
        self.cb_name.setChecked(self.cfg.get("show_name", True))
        self.cb_pid.setChecked(self.cfg.get("show_pid", True))
        self.cb_cpu.setChecked(self.cfg.get("show_cpu", True))
        self.cb_mem.setChecked(self.cfg.get("show_memory", True))
        self.cb_time.setChecked(self.cfg.get("show_time", True))
        self.cb_date.setChecked(self.cfg.get("show_date", False))
        self.cb_sys.setChecked(self.cfg.get("show_system_component", False))
        clayout.addWidget(g1)

        g2 = QGroupBox("🎨 外观")
        g2.setStyleSheet(g1.styleSheet())
        g2lay = QFormLayout(g2)
        g2lay.setSpacing(12)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(50, 255)
        self.opacity_slider.setValue(self.cfg.get("opacity", 170))
        g2lay.addRow(QLabel("透明度:"), self.opacity_slider)
        self.radius_slider = QSlider(Qt.Horizontal)
        self.radius_slider.setRange(0, 16)
        self.radius_slider.setValue(self.cfg.get("corner_radius", 6))
        g2lay.addRow(QLabel("圆角:"), self.radius_slider)
        self.scroll_slider = QSlider(Qt.Horizontal)
        self.scroll_slider.setRange(1, 10)
        self.scroll_slider.setValue(self.cfg.get("scroll_speed", 5))
        g2lay.addRow(QLabel("滚动速度:"), self.scroll_slider)
        for i in range(g2lay.rowCount()):
            item = g2lay.itemAt(i, QFormLayout.LabelRole)
            if item and item.widget():
                item.widget().setStyleSheet("color: #e0e0e0;")
        clayout.addWidget(g2)

        g3 = QGroupBox("🏷️ 程序备注")
        g3.setStyleSheet(g1.styleSheet())
        g3lay = QVBoxLayout(g3)
        btn_manage = QPushButton("管理备注...")
        btn_manage.setStyleSheet("padding: 8px;")
        btn_manage.clicked.connect(self.open_remark_manager)
        g3lay.addWidget(btn_manage)
        clayout.addWidget(g3)

        save_btn = QPushButton("💾 保存设置")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                padding: 12px;
                border-radius: 24px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background: #1084e0; }
        """)
        save_btn.clicked.connect(self.save_and_close)
        clayout.addWidget(save_btn)

        scroll.setWidget(content)
        main.addWidget(scroll)

        title.mousePressEvent = self.mouse_press
        title.mouseMoveEvent = self.mouse_move

    def mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos()

    def mouse_move(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            delta = event.globalPos() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPos()

    def open_remark_manager(self):
        dlg = RemarkManagerDialog(self.remarks, self)
        if dlg.exec_():
            self.remarks = dlg.get_remarks()

    def save_and_close(self):
        self.cfg["show_name"] = self.cb_name.isChecked()
        self.cfg["show_pid"] = self.cb_pid.isChecked()
        self.cfg["show_cpu"] = self.cb_cpu.isChecked()
        self.cfg["show_memory"] = self.cb_mem.isChecked()
        self.cfg["show_time"] = self.cb_time.isChecked()
        self.cfg["show_date"] = self.cb_date.isChecked()
        self.cfg["show_system_component"] = self.cb_sys.isChecked()
        self.cfg["opacity"] = self.opacity_slider.value()
        self.cfg["corner_radius"] = self.radius_slider.value()
        self.cfg["scroll_speed"] = self.scroll_slider.value()
        self.cfg["remarks"] = self.remarks
        if save_config(self.cfg):
            self.callback()
            self.close()
        # save_config 内部已弹窗，此处无需重复

# --------------------------
# 主悬浮窗
# --------------------------
class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(46)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 10, 0)
        self.label = ScrollingLabel()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.proc_cache = {}
        self.cpu_init = set()

        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(150)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        self.last_hwnd = 0
        self.last_rect = (0, 0, 0, 0)
        self.stable_count = 0
        self.is_visible = True

        self.make_tray()
        self.update_style()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_info)
        self.timer.start(500)

        self.server = QLocalServer(self)
        self.server.newConnection.connect(self.handle_new_connection)
        self.server.listen("AlwaysOnTopMonitor_Instance")

    def handle_new_connection(self):
        socket = self.server.nextPendingConnection()
        if socket.waitForReadyRead(1000):
            data = socket.readAll().data().decode()
            if data == "show_settings":
                self.open_settings()
        socket.disconnectFromServer()

    def make_tray(self):
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setBrush(QColor(0, 120, 215))
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 12, 12)
        p.end()
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(pix))
        self.tray.setToolTip("AlwaysOnTop")
        menu = QMenu()
        act_set = QAction("设置", self)
        act_set.triggered.connect(self.open_settings)
        act_auto = QAction("开机自启", self)
        act_auto.setCheckable(True)
        act_auto.setChecked(self.is_autostart_enabled())
        act_auto.triggered.connect(self.toggle_autostart)
        act_exit = QAction("退出", self)
        act_exit.triggered.connect(self.quit)
        menu.addAction(act_set)
        menu.addAction(act_auto)
        menu.addSeparator()
        menu.addAction(act_exit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def open_settings(self):
        self.settings_win = SettingsWindow(self.cfg, self.on_config_change)
        self.settings_win.show()

    def on_config_change(self):
        self.cfg = load_config()
        self.update_style()
        self.label.setScrollSpeed(self.cfg.get("scroll_speed", 5))

    def update_style(self):
        op = self.cfg.get("opacity", 170)
        dark = self.cfg.get("dark_mode", True)
        tc = "white" if dark else "black"
        bg = f"rgba(0,0,0,{op})" if dark else f"rgba(255,255,255,{op})"
        self.label.setStyleSheet(f"color:{tc}; background:{bg}; border-radius:4px;")

    def is_autostart_enabled(self):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "AlwaysOnTopMonitor")
            return True
        except:
            return False

    def toggle_autostart(self, enable):
        try:
            import winreg
            path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, "AlwaysOnTopMonitor", 0, winreg.REG_SZ, f'"{path}"')
            else:
                winreg.DeleteValue(key, "AlwaysOnTopMonitor")
        except:
            pass

    def quit(self):
        self.tray.hide()
        QApplication.quit()

    def fade_out(self):
        if self.is_visible:
            self.fade_anim.stop()
            self.fade_anim.setStartValue(self.windowOpacity())
            self.fade_anim.setEndValue(0.0)
            self.fade_anim.start()
            self.is_visible = False

    def fade_in(self):
        if not self.is_visible:
            self.fade_anim.stop()
            self.fade_anim.setStartValue(self.windowOpacity())
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.start()
            self.is_visible = True

    def update_info(self):
        try:
            hwnd = get_foreground_window()
            if not hwnd or is_window_fullscreen(hwnd):
                self.fade_out()
                self.hide()
                self.stable_count = 0
                return

            l, t, r, b = get_window_rect(hwnd)
            w = r - l
            if w < 100:
                self.fade_out()
                self.hide()
                self.stable_count = 0
                return

            rect_now = (l, t, r, b)
            hwnd_changed = (hwnd != self.last_hwnd)
            rect_changed = (rect_now != self.last_rect)

            if hwnd_changed or rect_changed:
                self.fade_out()
                self.stable_count = 0
                self.last_hwnd = hwnd
                self.last_rect = rect_now
                return

            self.stable_count += 1
            if self.stable_count >= 2:
                self.setGeometry(l, t - self.height() - 2, w, self.height())
                pid = get_window_thread_process_id(hwnd)

                name = "N/A"
                cpu = 0.0
                mem = 0.0
                if pid > 0:
                    try:
                        if pid in self.proc_cache:
                            p = self.proc_cache[pid]
                            if not p.is_running():
                                p = psutil.Process(pid)
                                self.proc_cache[pid] = p
                                self.cpu_init.discard(pid)
                        else:
                            p = psutil.Process(pid)
                            self.proc_cache[pid] = p
                        name = p.name()
                        if pid not in self.cpu_init:
                            p.cpu_percent()
                            self.cpu_init.add(pid)
                        cpu = p.cpu_percent()
                        mem = p.memory_info().rss / 1024 / 1024
                    except:
                        if pid in self.proc_cache:
                            del self.proc_cache[pid]
                            self.cpu_init.discard(pid)

                remark_html = ""
                for r in self.cfg.get("remarks", []):
                    if r["proc"].lower() == name.lower():
                        remark_html = f"<span style='background-color:{r['bgColor']}; color:{r['textColor']}; padding:2px 8px; border-radius:12px; margin-right:6px;'>📌 {r['remark']}</span> "
                        break

                parts = []
                if self.cfg.get("show_name"): parts.append(name)
                if self.cfg.get("show_pid"): parts.append(f"PID:{pid}")
                if self.cfg.get("show_cpu"): parts.append(f"CPU:{cpu:.0f}%")
                if self.cfg.get("show_memory"): parts.append(f"MEM:{mem:.0f}MB")
                if self.cfg.get("show_time"): parts.append(datetime.now().strftime("%H:%M:%S"))

                display = remark_html + " | ".join(parts)
                self.label.setText(display)
                self.label.setScrollSpeed(self.cfg.get("scroll_speed", 5))
                self.label.update_text_width()
                self.label.check_enable()

                if self.label.scroll_enabled:
                    self.label.setStyleSheet("color: black; background: rgba(255, 255, 255, 0.85); border-radius:4px; padding:2px;")
                else:
                    self.update_style()

                self.show()
                self.fade_in()
        except:
            self.fade_out()
            self.hide()

    def resizeEvent(self, e):
        try:
            rad = self.cfg.get("corner_radius", 6)
            path = QPainterPath()
            path.addRoundedRect(self.rect(), rad, rad)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        except:
            pass

# --------------------------
# 主程序
# --------------------------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    socket = QLocalSocket()
    socket.connectToServer("AlwaysOnTopMonitor_Instance")
    if socket.waitForConnected(500):
        reply = QMessageBox.question(
            None, "程序已在运行",
            "您已经打开一个程序了。\n\n是否打开已有实例的设置窗口？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            socket.write(b"show_settings")
            socket.flush()
            socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        sys.exit(0)

    overlay = Overlay()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()