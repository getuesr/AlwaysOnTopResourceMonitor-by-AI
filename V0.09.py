#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import ctypes
import ctypes.wintypes
import json
import time
import re
import subprocess
import math
import tempfile
from datetime import datetime

try:
    import psutil
except ImportError:
    print("请安装: pip install psutil")
    sys.exit(1)

try:
    from PyQt5.QtCore import (
        QTimer, Qt, QRect, QRectF, QPropertyAnimation, QEasingCurve, QPoint
    )
    from PyQt5.QtGui import (
        QPainterPath, QRegion, QFont, QIcon, QPixmap, QPainter, QColor,
        QPalette, QFontMetrics, QFontDatabase, QTextDocument
    )
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QHBoxLayout, QLabel, QVBoxLayout,
        QSystemTrayIcon, QMenu, QAction, QCheckBox, QSlider, QPushButton,
        QGroupBox, QFormLayout, QFrame, QStyleFactory, QMessageBox,
        QColorDialog, QLineEdit, QListWidget, QDialog, QAbstractItemView,
        QScrollArea, QSpinBox, QRadioButton, QButtonGroup
    )
    from PyQt5.QtNetwork import QLocalServer, QLocalSocket
except ImportError:
    print("请安装: pip install PyQt5")
    sys.exit(1)

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

def get_config_path():
    user_profile = os.path.expanduser("~")
    config_dir = os.path.join(user_profile, "AppData", "Local", "FloatingWindowMonitor")
    config_file = os.path.join(config_dir, "config.json")
    if not os.path.exists(config_dir):
        try:
            os.makedirs(config_dir, exist_ok=True)
            if os.name == 'nt':
                subprocess.run(['attrib', '-h', config_dir], capture_output=True)
        except:
            pass
    return config_dir, config_file

CONFIG_DIR, CONFIG_FILE = get_config_path()

DEFAULT_CONFIG = {
    "show_name": True,
    "show_pid": True,
    "show_cpu": True,
    "show_memory": True,
    "show_time": True,
    "opacity": 170,
    "corner_radius": 6,
    "dark_mode": True,
    "scroll_speed": 5,
    "remarks": [],
    "high_usage_alert": False,
    "cpu_threshold": 50,
    "memory_threshold": 2048,
    "memory_threshold_type": "percent",
    "memory_threshold_percent": 50,
    "cpu_display_mode": "total",
    "memory_display_percent": False,
    "remark_hide_name": False,
    "autostart": False,
    "global_offset_enabled": False,
    "global_offset": 2,
    "per_process_offsets": {}
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

def save_config(config):
    config_dir = os.path.dirname(CONFIG_FILE)
    try:
        os.makedirs(config_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix='.json')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        if os.name == 'nt':
            try:
                subprocess.run(['attrib', '-h', tmp_path], capture_output=True)
            except:
                pass
        os.replace(tmp_path, CONFIG_FILE)
        msg = QMessageBox()
        msg.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool | Qt.FramelessWindowHint)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("保存成功")
        msg.setText(f"配置已保存至：\n{CONFIG_FILE}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.show()
        msg.raise_()
        msg.activateWindow()
        msg.exec_()
        return True
    except Exception:
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
            if self.parent():
                self.setFixedWidth(self.parent().width() - 20)
            return
        fm = QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.plain_text)
        parent_width = self.parent().width() if self.parent() else self.width()
        available_width = parent_width - 20
        if text_width > available_width:
            self.scroll_enabled = True
            self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.setFixedWidth(available_width)
            if not self.timer.isActive():
                self.timer.start(30)
        else:
            self.scroll_enabled = False
            self.setAlignment(Qt.AlignCenter)
            self.timer.stop()
            self.setFixedWidth(available_width)

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
            self.list_widget.addItem(f"{r['proc']} — {r['remark']}")

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

class ProcessOffsetEditDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data or {}
        self.setWindowTitle("单独程序偏移设置")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.resize(400, 200)
        self.initUI()

    def initUI(self):
        layout = QFormLayout(self)
        layout.setSpacing(15)
        self.edit_proc = QLineEdit()
        self.edit_proc.setText(self.data.get("proc", ""))
        self.edit_proc.setPlaceholderText("如 chrome.exe")
        layout.addRow("进程名:", self.edit_proc)
        self.offset_slider = QSlider(Qt.Horizontal)
        self.offset_slider.setRange(0, 300)
        self.offset_slider.setValue(self.data.get("offset", 0))
        self.offset_label = QLabel(f"{self.offset_slider.value()} px")
        self.offset_slider.valueChanged.connect(lambda v: self.offset_label.setText(f"{v} px"))
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(self.offset_slider)
        offset_layout.addWidget(self.offset_label)
        layout.addRow("偏移高度:", offset_layout)
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addRow(btn_box)

    def get_data(self):
        return {
            "proc": self.edit_proc.text().strip(),
            "offset": self.offset_slider.value()
        }

class ProcessOffsetManagerDialog(QDialog):
    def __init__(self, offsets, parent=None):
        super().__init__(parent)
        self.offsets = offsets.copy()
        self.setWindowTitle("单独程序偏移管理")
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
        btn_add.clicked.connect(self.add_offset)
        btn_edit.clicked.connect(self.edit_offset)
        btn_delete.clicked.connect(self.delete_offset)
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
        for proc, offset in self.offsets.items():
            self.list_widget.addItem(f"{proc} — {offset} px")

    def add_offset(self):
        dlg = ProcessOffsetEditDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            if data["proc"]:
                self.offsets[data["proc"]] = data["offset"]
                self.refresh_list()

    def edit_offset(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            proc = list(self.offsets.keys())[row]
            offset = self.offsets[proc]
            dlg = ProcessOffsetEditDialog(self, {"proc": proc, "offset": offset})
            if dlg.exec_():
                data = dlg.get_data()
                if data["proc"]:
                    del self.offsets[proc]
                    self.offsets[data["proc"]] = data["offset"]
                    self.refresh_list()

    def delete_offset(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            proc = list(self.offsets.keys())[row]
            del self.offsets[proc]
            self.refresh_list()

    def save_and_close(self):
        self.accept()

    def get_offsets(self):
        return self.offsets

class SettingsWindow(QWidget):
    def __init__(self, cfg, callback, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.callback = callback
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 880)
        self.remarks = cfg.get("remarks", [])
        self.per_process_offsets = cfg.get("per_process_offsets", {})
        self.drag_pos = None
        self.initUI()

    def initUI(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        title = QFrame()
        title.setFixedHeight(45)
        title.setStyleSheet("background:#2d2d2d; border-top-left-radius:12px; border-top-right-radius:12px;")
        tlay = QHBoxLayout(title)
        tlay.setContentsMargins(20, 0, 15, 0)
        title_label = QLabel("⚙️ 设置")
        title_label.setStyleSheet("color:white; font-size:16px; font-weight:bold;")
        tlay.addWidget(title_label)
        tlay.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet("background:transparent; color:white; border:none; font-size:16px;")
        close_btn.clicked.connect(self.close)
        tlay.addWidget(close_btn)
        main.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:#3c3c3c; border:none; }")
        content = QFrame()
        content.setStyleSheet("background:#3c3c3c; border-bottom-left-radius:12px; border-bottom-right-radius:12px;")
        clayout = QVBoxLayout(content)
        clayout.setSpacing(15)
        clayout.setContentsMargins(24, 20, 24, 24)

        self.autostart_cb = QCheckBox("开机自启动")
        self.autostart_cb.setStyleSheet("color:#f0f0f0; font-weight:bold;")
        self.autostart_cb.setChecked(self.cfg.get("autostart", False))
        clayout.addWidget(self.autostart_cb)

        g1 = QGroupBox("📺 显示项")
        g1.setStyleSheet("color:white; font-weight:bold; border:1px solid #5a5a5a; border-radius:10px; margin-top:12px; padding-top:12px;")
        g1lay = QVBoxLayout(g1)
        self.cb_name = QCheckBox("程序名称")
        self.cb_pid = QCheckBox("PID")
        self.cb_cpu = QCheckBox("CPU 占用")
        self.cb_mem = QCheckBox("内存占用")
        self.cb_time = QCheckBox("时间")
        for cb in [self.cb_name, self.cb_pid, self.cb_cpu, self.cb_mem, self.cb_time]:
            cb.setStyleSheet("color:#f0f0f0;")
            g1lay.addWidget(cb)
        self.cb_name.setChecked(self.cfg.get("show_name", True))
        self.cb_pid.setChecked(self.cfg.get("show_pid", True))
        self.cb_cpu.setChecked(self.cfg.get("show_cpu", True))
        self.cb_mem.setChecked(self.cfg.get("show_memory", True))
        self.cb_time.setChecked(self.cfg.get("show_time", True))
        self.cb_cpu.toggled.connect(self.toggle_cpu_options)
        self.cb_mem.toggled.connect(self.toggle_mem_options)
        clayout.addWidget(g1)

        self.cpu_display_mode_group = QGroupBox("CPU 显示方式")
        self.cpu_display_mode_group.setStyleSheet(g1.styleSheet())
        cpu_mode_layout = QVBoxLayout(self.cpu_display_mode_group)
        self.cpu_mode_total = QRadioButton("总CPU利用率（多线程累计）")
        self.cpu_mode_single = QRadioButton("单线程平均百分比")
        cpu_mode_layout.addWidget(self.cpu_mode_total)
        cpu_mode_layout.addWidget(self.cpu_mode_single)
        self.cpu_mode_total.setChecked(self.cfg.get("cpu_display_mode", "total") == "total")
        self.cpu_mode_single.setChecked(self.cfg.get("cpu_display_mode") == "single")
        clayout.addWidget(self.cpu_display_mode_group)
        self.cpu_display_mode_group.setVisible(self.cfg.get("show_cpu", True))

        self.mem_display_percent_cb = QCheckBox("内存显示为百分比")
        self.mem_display_percent_cb.setStyleSheet("color:#f0f0f0;")
        self.mem_display_percent_cb.setChecked(self.cfg.get("memory_display_percent", False))
        clayout.addWidget(self.mem_display_percent_cb)
        self.mem_display_percent_cb.setVisible(self.cfg.get("show_memory", True))

        self.remark_hide_name_cb = QCheckBox("备注程序只显示备注（隐藏进程名）")
        self.remark_hide_name_cb.setStyleSheet("color:#f0f0f0;")
        self.remark_hide_name_cb.setChecked(self.cfg.get("remark_hide_name", False))
        clayout.addWidget(self.remark_hide_name_cb)

        g2 = QGroupBox("🎨 外观")
        g2.setStyleSheet(g1.styleSheet())
        g2lay = QFormLayout(g2)
        g2lay.setSpacing(10)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(50, 255)
        self.opacity_slider.setValue(self.cfg.get("opacity", 170))
        self.opacity_slider.setFocusPolicy(Qt.NoFocus)
        g2lay.addRow(QLabel("透明度:"), self.opacity_slider)
        self.radius_slider = QSlider(Qt.Horizontal)
        self.radius_slider.setRange(0, 16)
        self.radius_slider.setValue(self.cfg.get("corner_radius", 6))
        self.radius_slider.setFocusPolicy(Qt.NoFocus)
        g2lay.addRow(QLabel("圆角:"), self.radius_slider)
        self.scroll_slider = QSlider(Qt.Horizontal)
        self.scroll_slider.setRange(1, 10)
        self.scroll_slider.setValue(self.cfg.get("scroll_speed", 5))
        self.scroll_slider.setFocusPolicy(Qt.NoFocus)
        g2lay.addRow(QLabel("滚动速度:"), self.scroll_slider)
        for i in range(g2lay.rowCount()):
            item = g2lay.itemAt(i, QFormLayout.LabelRole)
            if item and item.widget():
                item.widget().setStyleSheet("color:#e0e0e0; min-width:70px;")
        clayout.addWidget(g2)

        g_offset_global = QGroupBox("📏 全局悬浮窗偏移 (默认2px)")
        g_offset_global.setStyleSheet(g1.styleSheet())
        offset_global_layout = QVBoxLayout(g_offset_global)
        self.global_offset_enabled_cb = QCheckBox("启用全局偏移调节")
        self.global_offset_enabled_cb.setStyleSheet("color:#f0f0f0;")
        self.global_offset_enabled_cb.setChecked(self.cfg.get("global_offset_enabled", False))
        self.global_offset_enabled_cb.toggled.connect(self.toggle_global_offset)
        offset_global_layout.addWidget(self.global_offset_enabled_cb)
        offset_slider_layout = QHBoxLayout()
        offset_slider_layout.addWidget(QLabel("偏移距离:"))
        self.global_offset_slider = QSlider(Qt.Horizontal)
        self.global_offset_slider.setRange(0, 300)
        self.global_offset_slider.setValue(self.cfg.get("global_offset", 2))
        self.global_offset_slider.setFocusPolicy(Qt.NoFocus)
        self.global_offset_label = QLabel(f"{self.global_offset_slider.value()} px")
        self.global_offset_slider.valueChanged.connect(lambda v: self.global_offset_label.setText(f"{v} px"))
        offset_slider_layout.addWidget(self.global_offset_slider)
        offset_slider_layout.addWidget(self.global_offset_label)
        offset_global_layout.addLayout(offset_slider_layout)
        clayout.addWidget(g_offset_global)
        self.toggle_global_offset(self.cfg.get("global_offset_enabled", False))

        g_per_proc_offset = QGroupBox("📌 单独程序偏移")
        g_per_proc_offset.setStyleSheet(g1.styleSheet())
        pp_layout = QVBoxLayout(g_per_proc_offset)
        btn_manage_offset = QPushButton("管理单独偏移...")
        btn_manage_offset.setStyleSheet("padding:8px;")
        btn_manage_offset.clicked.connect(self.open_process_offset_manager)
        pp_layout.addWidget(btn_manage_offset)
        clayout.addWidget(g_per_proc_offset)

        self.alert_cb = QCheckBox("高资源占用提示")
        self.alert_cb.setStyleSheet("color:#f0f0f0; font-weight:bold;")
        self.alert_cb.setChecked(self.cfg.get("high_usage_alert", False))
        self.alert_cb.toggled.connect(self.toggle_alert_options)
        clayout.addWidget(self.alert_cb)

        self.alert_group = QGroupBox("警报阈值设置")
        self.alert_group.setStyleSheet(g1.styleSheet())
        alert_layout = QVBoxLayout(self.alert_group)

        cpu_thresh_layout = QHBoxLayout()
        cpu_thresh_layout.addWidget(QLabel("CPU阈值 (%):"))
        self.cpu_thresh_slider = QSlider(Qt.Horizontal)
        self.cpu_thresh_slider.setRange(1, 100)
        self.cpu_thresh_slider.setValue(self.cfg.get("cpu_threshold", 50))
        self.cpu_thresh_slider.setFocusPolicy(Qt.NoFocus)
        self.cpu_thresh_label = QLabel(str(self.cpu_thresh_slider.value()))
        self.cpu_thresh_slider.valueChanged.connect(lambda v: self.cpu_thresh_label.setText(str(v)))
        cpu_thresh_layout.addWidget(self.cpu_thresh_slider)
        cpu_thresh_layout.addWidget(self.cpu_thresh_label)
        alert_layout.addLayout(cpu_thresh_layout)
        cpu_hint = QLabel("※ 阈值根据上方选择的CPU显示方式判断")
        cpu_hint.setStyleSheet("color:#aaa; font-size:11px;")
        alert_layout.addWidget(cpu_hint)

        mem_mode_layout = QHBoxLayout()
        self.mem_mode_group = QButtonGroup(self)
        self.mem_percent_radio = QRadioButton("百分比")
        self.mem_absolute_radio = QRadioButton("固定大小(MB)")
        self.mem_mode_group.addButton(self.mem_percent_radio, 0)
        self.mem_mode_group.addButton(self.mem_absolute_radio, 1)
        mem_mode_layout.addWidget(self.mem_percent_radio)
        mem_mode_layout.addWidget(self.mem_absolute_radio)
        alert_layout.addLayout(mem_mode_layout)

        mem_percent_layout = QHBoxLayout()
        mem_percent_layout.addWidget(QLabel("内存阈值 (%):"))
        self.mem_percent_slider = QSlider(Qt.Horizontal)
        self.mem_percent_slider.setRange(1, 100)
        self.mem_percent_slider.setValue(self.cfg.get("memory_threshold_percent", 50))
        self.mem_percent_slider.setFocusPolicy(Qt.NoFocus)
        self.mem_percent_label = QLabel(str(self.mem_percent_slider.value()))
        self.mem_percent_slider.valueChanged.connect(lambda v: self.mem_percent_label.setText(str(v)))
        mem_percent_layout.addWidget(self.mem_percent_slider)
        mem_percent_layout.addWidget(self.mem_percent_label)
        alert_layout.addLayout(mem_percent_layout)

        mem_abs_layout = QHBoxLayout()
        mem_abs_layout.addWidget(QLabel("内存阈值 (MB):"))
        self.mem_abs_spin = QSpinBox()
        total_mem = psutil.virtual_memory().total // (1024 * 1024)
        self.mem_abs_spin.setRange(1, total_mem)
        self.mem_abs_spin.setValue(self.cfg.get("memory_threshold", 2048))
        self.mem_abs_spin.setFocusPolicy(Qt.NoFocus)
        mem_abs_layout.addWidget(self.mem_abs_spin)
        mem_abs_layout.addStretch()
        alert_layout.addLayout(mem_abs_layout)

        if self.cfg.get("memory_threshold_type", "percent") == "percent":
            self.mem_percent_radio.setChecked(True)
        else:
            self.mem_absolute_radio.setChecked(True)
        self.mem_mode_group.buttonClicked.connect(self.update_mem_inputs)
        clayout.addWidget(self.alert_group)
        self.toggle_alert_options(self.cfg.get("high_usage_alert", False))
        self.update_mem_inputs()

        g4 = QGroupBox("🏷️ 程序备注")
        g4.setStyleSheet(g1.styleSheet())
        g4lay = QVBoxLayout(g4)
        btn_manage = QPushButton("管理备注...")
        btn_manage.setStyleSheet("padding:8px;")
        btn_manage.clicked.connect(self.open_remark_manager)
        g4lay.addWidget(btn_manage)
        clayout.addWidget(g4)

        btn_about = QPushButton("关于")
        btn_about.setStyleSheet("padding:8px; background:#444; color:white; border-radius:12px;")
        btn_about.clicked.connect(self.show_about)
        clayout.addWidget(btn_about)

        save_btn = QPushButton("💾 保存设置")
        save_btn.setStyleSheet("background:#0078d4; color:white; padding:12px; border-radius:24px; font-weight:bold;")
        save_btn.clicked.connect(self.save_and_close)
        clayout.addWidget(save_btn)

        scroll.setWidget(content)
        main.addWidget(scroll)
        title.mousePressEvent = self.mouse_press
        title.mouseMoveEvent = self.mouse_move

    def toggle_cpu_options(self, checked):
        self.cpu_display_mode_group.setVisible(checked)

    def toggle_mem_options(self, checked):
        self.mem_display_percent_cb.setVisible(checked)

    def toggle_alert_options(self, checked):
        self.alert_group.setVisible(checked)

    def toggle_global_offset(self, checked):
        self.global_offset_slider.setEnabled(checked)

    def update_mem_inputs(self):
        is_percent = self.mem_percent_radio.isChecked()
        self.mem_percent_slider.setEnabled(is_percent)
        self.mem_abs_spin.setEnabled(not is_percent)

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

    def open_process_offset_manager(self):
        dlg = ProcessOffsetManagerDialog(self.per_process_offsets, self)
        if dlg.exec_():
            self.per_process_offsets = dlg.get_offsets()

    def show_about(self):
        QMessageBox.about(self, "关于",
            "<b>浮动窗口资源监视器</b><br><br>"
            "GitHub 开源项目<br>"
            "发布人: getuesr<br>"
            "纯使用 Deepseek 和豆包 俩AI制作<br>"
            "浮动在活动窗口上的资源监视器"
        )

    def save_and_close(self):
        if self.mem_abs_spin.isEnabled() and self.mem_abs_spin.value() > self.mem_abs_spin.maximum():
            QMessageBox.warning(self, "输入错误", "内存数值超出物理内存上限")
            return
        self.cfg["autostart"] = self.autostart_cb.isChecked()
        self.cfg["show_name"] = self.cb_name.isChecked()
        self.cfg["show_pid"] = self.cb_pid.isChecked()
        self.cfg["show_cpu"] = self.cb_cpu.isChecked()
        self.cfg["show_memory"] = self.cb_mem.isChecked()
        self.cfg["show_time"] = self.cb_time.isChecked()
        self.cfg["opacity"] = self.opacity_slider.value()
        self.cfg["corner_radius"] = self.radius_slider.value()
        self.cfg["scroll_speed"] = self.scroll_slider.value()
        self.cfg["remarks"] = self.remarks
        self.cfg["high_usage_alert"] = self.alert_cb.isChecked()
        self.cfg["cpu_threshold"] = self.cpu_thresh_slider.value()
        self.cfg["memory_threshold_type"] = "percent" if self.mem_percent_radio.isChecked() else "absolute"
        self.cfg["memory_threshold_percent"] = self.mem_percent_slider.value()
        self.cfg["memory_threshold"] = self.mem_abs_spin.value()
        self.cfg["cpu_display_mode"] = "total" if self.cpu_mode_total.isChecked() else "single"
        self.cfg["memory_display_percent"] = self.mem_display_percent_cb.isChecked()
        self.cfg["remark_hide_name"] = self.remark_hide_name_cb.isChecked()
        self.cfg["global_offset_enabled"] = self.global_offset_enabled_cb.isChecked()
        self.cfg["global_offset"] = self.global_offset_slider.value()
        self.cfg["per_process_offsets"] = self.per_process_offsets
        if save_config(self.cfg):
            self.callback()
            self.close()
        else:
            QMessageBox.warning(self, "保存失败", "配置文件写入失败，请检查权限。")

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(46)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 10, 0)
        self.label = ScrollingLabel()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.proc_cache = {}
        self.cpu_init = set()
        self.alert_cooldown = 0
        self.alert_timer = QTimer()
        self.alert_timer.timeout.connect(self._alert_shake_step)
        self.alert_shake_count = 0
        self.alert_original_pos = None

        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(150)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        self.last_hwnd = 0
        self.last_rect = (0, 0, 0, 0)
        self.stable_count = 0
        self.is_visible = True

        self.self_hwnd = int(self.winId())
        self.warning_active = False
        self.saved_text = ""

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
        act_auto.setChecked(self.cfg.get("autostart", False))
        act_auto.triggered.connect(self.toggle_autostart)
        act_exit = QAction("退出", self)
        act_exit.triggered.connect(self.quit)
        menu.addAction(act_set)
        menu.addAction(act_auto)
        menu.addSeparator()
        menu.addAction(act_exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.tray.contextMenu().popup(self.tray.geometry().center())
        elif reason == QSystemTrayIcon.Context:
            self.tray.contextMenu().popup(self.tray.geometry().center())

    def open_settings(self):
        self.settings_win = SettingsWindow(self.cfg, self.on_config_change)
        self.settings_win.show()

    def on_config_change(self):
        self.cfg = load_config()
        self.update_style()
        self.label.setScrollSpeed(self.cfg.get("scroll_speed", 5))
        self.tray.contextMenu().actions()[1].setChecked(self.cfg.get("autostart", False))
        self.apply_autostart(self.cfg.get("autostart", False))

    def update_style(self):
        if self.warning_active:
            self.label.setStyleSheet("color: black; background: #FFCC00; border-radius:4px;")
            return
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
        self.cfg["autostart"] = enable
        save_config(self.cfg)
        self.apply_autostart(enable)

    def apply_autostart(self, enable):
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

    def trigger_alert(self):
        if self.alert_cooldown > 0 or self.alert_timer.isActive():
            return
        self.alert_cooldown = 20
        self.alert_shake_count = 0
        self.alert_original_pos = self.pos()
        self.alert_timer.start(20)

    def _alert_shake_step(self):
        if self.alert_shake_count >= 100:
            self.alert_timer.stop()
            self.move(self.alert_original_pos)
            self.alert_original_pos = None
            return
        t = self.alert_shake_count / 100.0
        offset = int(8 * math.sin(t * 20 * math.pi) * (1 - t))
        self.move(self.alert_original_pos + QPoint(offset, 0))
        self.alert_shake_count += 1

    def _apply_dynamic_style(self, cpu, mem_val, mem_percent):
        if self.warning_active:
            return
        if self.alert_timer.isActive() and self.cfg.get("high_usage_alert"):
            self.label.setStyleSheet("color: white; background: rgba(255, 0, 0, 255); border-radius:4px; padding:2px;")
        elif self.label.scroll_enabled:
            self.label.setStyleSheet("color: black; background: rgba(255, 255, 255, 0.85); border-radius:4px; padding:2px;")
        else:
            self.update_style()

    def update_info(self):
        try:
            if self.alert_cooldown > 0:
                self.alert_cooldown -= 1

            hwnd = get_foreground_window()
            
            if hwnd == self.self_hwnd:
                if not self.warning_active:
                    self.warning_active = True
                    self.saved_text = self.label.full_html if hasattr(self.label, 'full_html') else self.label.text()
                    self.label.setText("/////// 请勿聚焦悬浮窗 //////")
                    self.update_style()
                return
            else:
                if self.warning_active:
                    self.warning_active = False
                    self.label.setText(self.saved_text)
                    self.update_style()

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
                self.stable_count = 2
                self.last_hwnd = hwnd
                self.last_rect = rect_now
                pid = get_window_thread_process_id(hwnd)
                name = "N/A"
                cpu = 0.0
                mem_val = 0.0
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
                        mem_val = p.memory_info().rss / 1024 / 1024
                    except:
                        if pid in self.proc_cache:
                            del self.proc_cache[pid]
                            self.cpu_init.discard(pid)
                total_mem_mb = psutil.virtual_memory().total / (1024 * 1024)
                mem_percent = (mem_val / total_mem_mb) * 100 if total_mem_mb > 0 else 0
                self._apply_dynamic_style(cpu, mem_val, mem_percent)
                return

            self.stable_count += 1
            if self.stable_count >= 2:
                base_offset = 2
                if self.cfg.get("global_offset_enabled", False):
                    base_offset = self.cfg.get("global_offset", 2)
                pid = get_window_thread_process_id(hwnd)
                name = "N/A"
                cpu = 0.0
                mem_val = 0.0
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
                        mem_val = p.memory_info().rss / 1024 / 1024
                    except:
                        if pid in self.proc_cache:
                            del self.proc_cache[pid]
                            self.cpu_init.discard(pid)

                per_proc_offsets = self.cfg.get("per_process_offsets", {})
                for k, v in per_proc_offsets.items():
                    if k.lower() == name.lower():
                        base_offset = v
                        break

                self.setGeometry(l, t - self.height() - base_offset, w, self.height())
                self.setFixedWidth(w)
                self.label.setFixedWidth(w - 20)

                total_mem_mb = psutil.virtual_memory().total / (1024 * 1024)
                mem_percent = (mem_val / total_mem_mb) * 100 if total_mem_mb > 0 else 0

                if self.cfg.get("high_usage_alert") and self.alert_cooldown == 0:
                    cpu_exceed = False
                    if self.cfg.get("cpu_display_mode") == "total":
                        cpu_exceed = cpu > self.cfg.get("cpu_threshold", 50)
                    else:
                        single_cpu = cpu / psutil.cpu_count() if psutil.cpu_count() else cpu
                        cpu_exceed = single_cpu > self.cfg.get("cpu_threshold", 50)
                    mem_exceed = False
                    if self.cfg.get("memory_threshold_type") == "percent":
                        mem_exceed = mem_percent > self.cfg.get("memory_threshold_percent", 50)
                    else:
                        mem_exceed = mem_val > self.cfg.get("memory_threshold", 2048)
                    if cpu_exceed or mem_exceed:
                        self.trigger_alert()

                remark_html = ""
                matched_remark = None
                for r in self.cfg.get("remarks", []):
                    if r["proc"].lower() == name.lower():
                        matched_remark = r
                        break
                if matched_remark:
                    remark_text = matched_remark['remark']
                    remark_html = f"<span style='background-color:{matched_remark['bgColor']}; color:{matched_remark['textColor']}; padding:2px 8px; border-radius:12px; margin-right:6px;'>📌 {remark_text}</span> "

                parts = []
                if self.cfg.get("show_name") and not (matched_remark and self.cfg.get("remark_hide_name")):
                    parts.append(name)
                if self.cfg.get("show_pid"):
                    parts.append(f"PID:{pid}")
                if self.cfg.get("show_cpu"):
                    cpu_val = cpu
                    if self.cfg.get("cpu_display_mode") == "single":
                        cpu_val = cpu_val / psutil.cpu_count() if psutil.cpu_count() else cpu_val
                    parts.append(f"CPU:{cpu_val:.0f}%")
                if self.cfg.get("show_memory"):
                    if self.cfg.get("memory_display_percent"):
                        parts.append(f"MEM:{mem_percent:.1f}%")
                    else:
                        parts.append(f"MEM:{mem_val:.0f}MB")
                if self.cfg.get("show_time"):
                    parts.append(datetime.now().strftime("%H:%M:%S"))

                display = remark_html + " | ".join(parts)
                self.label.setText(display)
                self.label.setScrollSpeed(self.cfg.get("scroll_speed", 5))
                self.label.update_text_width()
                self.label.check_enable()

                self._apply_dynamic_style(cpu, mem_val, mem_percent)
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

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    socket = QLocalSocket()
    socket.connectToServer("AlwaysOnTopMonitor_Instance")
    if socket.waitForConnected(500):
        reply = QMessageBox.question(
            None, "程序已在运行",
            "您已经打开一个程序了",
            QMessageBox.Yes | QMessageBox.是的, QMessageBox.Yes
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