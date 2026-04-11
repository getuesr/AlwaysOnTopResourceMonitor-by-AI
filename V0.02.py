#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import ctypes
import ctypes.wintypes
import json
from datetime import datetime

try:
    import psutil
except ImportError:
    print("请安装: pip install psutil")
    sys.exit(1)

try:
    from PyQt5.QtCore import QTimer, Qt, QRect
    from PyQt5.QtGui import (
        QPainterPath, QRegion, QFont, QIcon, QPixmap, QPainter, QColor,
        QPalette, QFontMetrics
    )
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QHBoxLayout, QLabel, QVBoxLayout,
        QSystemTrayIcon, QMenu, QAction, QCheckBox, QSlider, QPushButton,
        QGroupBox, QFormLayout, QFrame, QStyleFactory, QMessageBox,
        QColorDialog, QLineEdit, QListWidget, QDialog, QAbstractItemView,
        QScrollArea
    )
except ImportError:
    print("请安装: pip install PyQt5")
    sys.exit(1)

# Windows API
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

# 配置
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
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

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except:
        pass

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

# ==============================
# 修复：平滑循环滚动 + 暂停2秒
# ==============================
class ScrollingLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = ""
        self.offset = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self.step)
        self.scroll_speed = 5
        self.scroll_enabled = False
        self.text_width = 0
        self.paused = False
        self.pause_timer = QTimer()
        self.pause_timer.setSingleShot(True)
        self.pause_timer.timeout.connect(self.resume_scroll)
        
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setStyleSheet("background:transparent;")

    def setText(self, text):
        self.full_text = text
        self.offset = 0.0
        self.paused = False
        self.update_text_width()
        self.check_enable()
        self.update()

    def setScrollSpeed(self, s):
        self.scroll_speed = max(1, min(10, s))

    def update_text_width(self):
        if self.full_text:
            fm = QFontMetrics(self.font())
            self.text_width = fm.horizontalAdvance(self.full_text)
        else:
            self.text_width = 0

    def check_enable(self):
        if self.width() <= 10 or not self.full_text:
            self.scroll_enabled = False
            self.timer.stop()
            return
        if self.text_width > self.width() - 20:
            self.scroll_enabled = True
            if not self.timer.isActive():
                self.timer.start(25)
        else:
            self.scroll_enabled = False
            self.timer.stop()
            self.offset = 0.0

    def step(self):
        if not self.scroll_enabled or self.paused:
            return
        
        # 平滑步长
        step = max(0.5, self.scroll_speed / 1.8)
        self.offset += step

        # 滚到底 → 暂停2秒
        if self.offset >= self.text_width + 30:
            self.paused = True
            self.timer.stop()
            self.pause_timer.start(2000)

        self.update()

    def resume_scroll(self):
        # 从右侧重新开始循环
        self.offset = -self.width()
        self.paused = False
        self.timer.start(25)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.WindowText))
        painter.setRenderHint(QPainter.TextAntialiasing)
        r = self.rect()

        if not self.scroll_enabled:
            painter.drawText(r, Qt.AlignCenter, self.full_text)
            return

        # 循环滚动绘制
        x = int(-self.offset)
        painter.drawText(
            QRect(x, 0, self.text_width + 200, r.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            self.full_text
        )

    def resizeEvent(self, e):
        self.update_text_width()
        self.check_enable()
        super().resizeEvent(e)

# 备注对话框
class RemarkDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data or {}
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(420, 420)
        self.text_color = self.data.get("textColor", "#FFFFFF")
        self.bg_color = self.data.get("bgColor", "#2A2A2A")
        self.initUI()

    def initUI(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QFrame()
        title.setFixedHeight(40)
        title.setStyleSheet("background:#2d2d2d; border-radius:12px 12px 0 0;")
        tlay = QHBoxLayout(title)
        tlay.setContentsMargins(20, 0, 15, 0)
        tlay.addWidget(QLabel("📝 程序备注").setStyleSheet("color:white; font-weight:bold;"))
        tlay.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet("background:transparent; color:white; border:none;")
        close_btn.clicked.connect(self.reject)
        tlay.addWidget(close_btn)
        lay.addWidget(title)

        content = QFrame()
        content.setStyleSheet("background:#3c3c3c; border-radius:0 0 12px 12px;")
        clayout = QVBoxLayout(content)
        clayout.setSpacing(15)
        clayout.setContentsMargins(25, 20, 25, 25)

        clayout.addWidget(QLabel("进程名").setStyleSheet("color:#ddd;"))
        self.proc_input = QLineEdit()
        self.proc_input.setText(self.data.get("proc", ""))
        self.proc_input.setStyleSheet("padding:8px; background:#1e1e3e; color:white; border:1px solid #666; border-radius:6px;")
        clayout.addWidget(self.proc_input)

        clayout.addWidget(QLabel("备注").setStyleSheet("color:#ddd;"))
        self.remark_input = QLineEdit()
        self.remark_input.setText(self.data.get("remark", ""))
        self.remark_input.setStyleSheet(self.proc_input.styleSheet())
        clayout.addWidget(self.remark_input)

        clayout.addWidget(QLabel("文字颜色").setStyleSheet("color:#ddd;"))
        cr1 = QHBoxLayout()
        self.text_color_btn = QPushButton()
        self.text_color_btn.setFixedSize(50, 36)
        self.text_color_btn.setStyleSheet(f"background:{self.text_color}; border:1px solid #888; border-radius:6px;")
        self.text_color_btn.clicked.connect(lambda: self.pick_color("text"))
        cr1.addWidget(self.text_color_btn)
        cr1.addStretch()
        clayout.addLayout(cr1)

        clayout.addWidget(QLabel("背景颜色").setStyleSheet("color:#ddd;"))
        cr2 = QHBoxLayout()
        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setFixedSize(50, 36)
        self.bg_color_btn.setStyleSheet(f"background:{self.bg_color}; border:1px solid #888; border-radius:6px;")
        self.bg_color_btn.clicked.connect(lambda: self.pick_color("bg"))
        cr2.addWidget(self.bg_color_btn)
        cr2.addStretch()
        clayout.addLayout(cr2)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet("background:#0078d4; color:white; padding:8px 20px; border-radius:20px;")
        save_btn.clicked.connect(self.on_save)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("background:#555; color:white; padding:8px 20px; border-radius:20px;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        clayout.addLayout(btn_layout)

        lay.addWidget(content)

    def pick_color(self, target):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            hex_color = color.name().upper()
            if target == "text":
                self.text_color = hex_color
                self.text_color_btn.setStyleSheet(f"background:{hex_color}; border:1px solid #888;")
            else:
                self.bg_color = hex_color
                self.bg_color_btn.setStyleSheet(f"background:{hex_color}; border:1px solid #888;")

    def on_save(self):
        proc = self.proc_input.text().strip()
        remark = self.remark_input.text().strip()
        if not proc or not remark:
            QMessageBox.warning(self, "提示", "进程名和备注不能为空")
            return
        self.data = {"proc": proc, "remark": remark, "textColor": self.text_color, "bgColor": self.bg_color}
        self.accept()

# 设置窗口
class SettingsWindow(QWidget):
    def __init__(self, cfg, callback, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.callback = callback
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(480, 680)
        self.remarks = cfg.get("remarks", [])
        self.initUI()

    def initUI(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        title = QFrame()
        title.setFixedHeight(50)
        title.setStyleSheet("background:#2d2d2d; border-radius:12px 12px 0 0;")
        tlay = QHBoxLayout(title)
        tlay.setContentsMargins(20, 0, 15, 0)
        tlay.addWidget(QLabel("⚙️ 设置").setStyleSheet("color:white; font-size:16px; font-weight:bold;"))
        tlay.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setStyleSheet("background:transparent; color:white; border:none; font-size:16px;")
        close_btn.clicked.connect(self.close)
        tlay.addWidget(close_btn)
        main.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:#3c3c3c; border: none; }")
        content = QFrame()
        content.setStyleSheet("background:#3c3c3c;")
        clayout = QVBoxLayout(content)
        clayout.setSpacing(24)
        clayout.setContentsMargins(28, 24, 28, 28)

        g1 = QGroupBox("📺 显示项")
        g1.setStyleSheet("color:white; font-weight:bold; border:1px solid #5a5a5a; border-radius:10px; margin-top:12px;")
        g1lay = QVBoxLayout(g1)
        g1lay.setSpacing(8)
        self.cb_name = QCheckBox("程序名称")
        self.cb_pid  = QCheckBox("PID")
        self.cb_cpu  = QCheckBox("CPU 占用")
        self.cb_mem  = QCheckBox("内存占用")
        self.cb_time = QCheckBox("时间")
        self.cb_date = QCheckBox("日期")
        self.cb_sys  = QCheckBox("系统组件标识")
        for cb in [self.cb_name, self.cb_pid, self.cb_cpu, self.cb_mem, self.cb_time, self.cb_date, self.cb_sys]:
            cb.setStyleSheet("color:#f0f0f0; font-size:14px;")
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
        g2lay.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(50, 255)
        self.opacity_slider.setValue(self.cfg.get("opacity", 170))
        g2lay.addRow(QLabel("透明度：").setStyleSheet("color:white; min-width:70px;"), self.opacity_slider)

        self.radius_slider = QSlider(Qt.Horizontal)
        self.radius_slider.setRange(0, 16)
        self.radius_slider.setValue(self.cfg.get("corner_radius", 6))
        g2lay.addRow(QLabel("圆角：").setStyleSheet("color:white; min-width:70px;"), self.radius_slider)

        self.scroll_slider = QSlider(Qt.Horizontal)
        self.scroll_slider.setRange(1, 10)
        self.scroll_slider.setValue(self.cfg.get("scroll_speed", 5))
        g2lay.addRow(QLabel("滚动速度：").setStyleSheet("color:white; min-width:70px;"), self.scroll_slider)
        clayout.addWidget(g2)

        g3 = QGroupBox("🏷️ 备注管理")
        g3.setStyleSheet(g1.styleSheet())
        g3lay = QVBoxLayout(g3)
        self.remark_list = QListWidget()
        self.remark_list.setStyleSheet("background:#1e1e1e; color:white; border:1px solid #555; border-radius:8px;")
        self.remark_list.setFixedHeight(140)
        self.refresh_remark_list()
        g3lay.addWidget(self.remark_list)
        bl = QHBoxLayout()
        add_btn = QPushButton("添加")
        edit_btn = QPushButton("修改")
        del_btn = QPushButton("删除")
        for btn in (add_btn, edit_btn, del_btn):
            btn.setStyleSheet("background:#0078d4; color:white; padding:8px 16px; border-radius:18px;")
        add_btn.clicked.connect(self.add_remark)
        edit_btn.clicked.connect(self.edit_remark)
        del_btn.clicked.connect(self.delete_remark)
        bl.addWidget(add_btn)
        bl.addWidget(edit_btn)
        bl.addWidget(del_btn)
        g3lay.addLayout(bl)
        clayout.addWidget(g3)

        save_btn = QPushButton("保存设置")
        save_btn.setStyleSheet("background:#0078d4; color:white; padding:14px; border-radius:26px; font-weight:bold; font-size:15px;")
        save_btn.clicked.connect(self.save_and_close)
        clayout.addWidget(save_btn)

        scroll.setWidget(content)
        main.addWidget(scroll)

    def refresh_remark_list(self):
        self.remark_list.clear()
        for r in self.remarks:
            self.remark_list.addItem(f"{r['proc']} | {r['remark']}")

    def add_remark(self):
        dlg = RemarkDialog(self)
        if dlg.exec_():
            self.remarks.append(dlg.data)
            self.refresh_remark_list()

    def edit_remark(self):
        row = self.remark_list.currentRow()
        if row >= 0:
            dlg = RemarkDialog(self, self.remarks[row])
            if dlg.exec_():
                self.remarks[row] = dlg.data
                self.refresh_remark_list()

    def delete_remark(self):
        row = self.remark_list.currentRow()
        if row >= 0:
            del self.remarks[row]
            self.refresh_remark_list()

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
        save_config(self.cfg)
        self.callback()
        self.close()

# 主窗口
class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(50)

        # 布局修复：自动适应最小宽度
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)
        
        self.label = ScrollingLabel()
        self.label.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.proc_cache = {}
        self.cpu_init = set()
        self.make_tray()
        self.update_style()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_info)
        self.timer.start(500)

    def make_tray(self):
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setBrush(QColor(0, 120, 212))
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 12, 12)
        p.end()
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(pix))
        self.tray.setToolTip("AlwaysOnTop")
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#2b2b2b; color:white; }
            QMenu::item:selected { background:#0078d4; }
        """)
        act_set = QAction("⚙️ 设置", self)
        act_set.triggered.connect(self.open_settings)
        act_auto = QAction("🚀 开机自启", self)
        act_auto.setCheckable(True)
        act_auto.setChecked(self.is_autostart_enabled())
        act_auto.triggered.connect(self.toggle_autostart)
        act_exit = QAction("❌ 退出", self)
        act_exit.triggered.connect(self.quit)
        menu.addAction(act_set)
        menu.addAction(act_auto)
        menu.addSeparator()
        menu.addAction(act_exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_click)
        self.tray.show()

    def on_tray_click(self, reason):
        if reason == QSystemTrayIcon.Context:
            self.tray.contextMenu().exec_(self.tray.geometry().center())

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
        self.label.setStyleSheet(f"color:{tc}; background:{bg}; border-radius:6px;")

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

    def update_info(self):
        try:
            hwnd = get_foreground_window()
            if not hwnd or is_window_fullscreen(hwnd):
                self.hide()
                return

            l, t, r, b = get_window_rect(hwnd)
            w = r - l

            # 窗口宽度自适应修复（最小宽度 260）
            final_w = max(260, w)
            self.setFixedWidth(final_w)
            self.setGeometry(l, t - self.height() - 3, final_w, self.height())

            pid = get_window_thread_process_id(hwnd)
            name = "N/A"
            cpu = 0.0
            mem = 0.0

            if pid > 0:
                try:
                    if pid not in self.proc_cache:
                        self.proc_cache[pid] = psutil.Process(pid)
                    p = self.proc_cache[pid]
                    name = p.name()
                    if pid not in self.cpu_init:
                        p.cpu_percent(interval=0)
                        self.cpu_init.add(pid)
                    cpu = p.cpu_percent()
                    mem = p.memory_info().rss / 1024 / 1024
                except:
                    pass

            # 备注
            remark_str = ""
            for r in self.cfg.get("remarks", []):
                if r["proc"].lower() == name.lower():
                    remark_str = f"[{r['remark']}] "
                    break

            parts = []
            if self.cfg.get("show_name"): parts.append(name)
            if self.cfg.get("show_pid"): parts.append(f"PID:{pid}")
            if self.cfg.get("show_cpu"): parts.append(f"CPU:{cpu:.0f}%")
            if self.cfg.get("show_memory"): parts.append(f"MEM:{mem:.0f}MB")
            if self.cfg.get("show_time"): parts.append(datetime.now().strftime("%H:%M:%S"))

            display = remark_str + "  |  ".join(parts)
            self.label.setText(display)
            self.label.setScrollSpeed(self.cfg.get("scroll_speed", 5))
            self.show()
        except Exception:
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
    overlay = Overlay()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
