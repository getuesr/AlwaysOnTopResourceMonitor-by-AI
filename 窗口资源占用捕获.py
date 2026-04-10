#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Window Resource Monitor
实时显示前台窗口的 PID、CPU 和内存占用的浮动工具。
支持系统托盘，可设置开机自启动。
仅支持 Windows 系统。
"""

import sys
import ctypes
import ctypes.wintypes
import winreg
from time import perf_counter

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import (
    QPainterPath, QRegion, QFont, QIcon, QPixmap, QPainter, QColor
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QLabel,
    QSystemTrayIcon, QMenu, QAction
)

# ---------- Windows API 封装 ----------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

# 设置 DPI 感知
ctypes.windll.shcore.SetProcessDpiAwareness(1)

# 常量
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("PageFaultCount", ctypes.wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]

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

def open_process(pid):
    return kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)

def get_process_memory_info(handle):
    meminfo = PROCESS_MEMORY_COUNTERS_EX()
    meminfo.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    if psapi.GetProcessMemoryInfo(handle, ctypes.byref(meminfo), meminfo.cb):
        return meminfo.WorkingSetSize
    return 0

def get_process_times(handle):
    creation = ctypes.c_ulonglong()
    exit = ctypes.c_ulonglong()
    kernel = ctypes.c_ulonglong()
    user = ctypes.c_ulonglong()
    if kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit),
                                ctypes.byref(kernel), ctypes.byref(user)):
        return kernel.value + user.value
    return 0

def get_system_times():
    idle = ctypes.c_ulonglong()
    kernel = ctypes.c_ulonglong()
    user = ctypes.c_ulonglong()
    if kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return kernel.value + user.value
    return 0

def is_window_fullscreen(hwnd):
    if not hwnd:
        return False
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    style = user32.GetWindowLongW(hwnd, -16)
    if style & 0x00C00000:  # WS_CAPTION
        return False
    monitor = user32.MonitorFromWindow(hwnd, 2)
    if not monitor:
        return False
    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.wintypes.DWORD),
        ]
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
        return False
    monitor_width = mi.rcMonitor.right - mi.rcMonitor.left
    monitor_height = mi.rcMonitor.bottom - mi.rcMonitor.top
    return width >= monitor_width and height >= monitor_height

# ---------- CPU 计算器 ----------
class ProcessCpuCalculator:
    def __init__(self):
        self.last_process_time = {}
        self.last_system_time = {}
        self.last_check = {}

    def get_cpu_percent(self, pid):
        now = perf_counter()
        h_process = open_process(pid)
        if not h_process:
            return 0.0
        try:
            proc_time = get_process_times(h_process)
            sys_time = get_system_times()
            if pid in self.last_process_time:
                dt = now - self.last_check[pid]
                if dt > 0.1:
                    proc_diff = proc_time - self.last_process_time[pid]
                    sys_diff = sys_time - self.last_system_time[pid]
                    cpu = (proc_diff / sys_diff) * 100.0 if sys_diff > 0 else 0.0
                else:
                    cpu = 0.0
            else:
                cpu = 0.0
            self.last_process_time[pid] = proc_time
            self.last_system_time[pid] = sys_time
            self.last_check[pid] = now
            return cpu
        finally:
            kernel32.CloseHandle(h_process)

cpu_calc = ProcessCpuCalculator()

# ---------- 浮动窗口 ----------
class OverlayWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(50)

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)
        self.label = QLabel()
        self.label.setFont(QFont("Segoe UI", 10))
        self.label.setStyleSheet("color: white; background-color: rgba(0, 0, 0, 180);")
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.last_hwnd = None
        self.tray_icon = None
        self.create_tray_icon()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_overlay)
        self.timer.start(500)

    def create_tray_icon(self):
        """创建系统托盘图标和菜单"""
        # 生成蓝色圆点图标（16x16）
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor(0, 120, 215))  # Windows 蓝
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        icon = QIcon(pixmap)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Window Resource Monitor")

        menu = QMenu()
        self.autostart_action = QAction("开机自启动", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.is_autostart_enabled())
        self.autostart_action.triggered.connect(self.toggle_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_app)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def toggle_autostart(self, checked):
        self.set_autostart(checked)

    def is_autostart_enabled(self):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "WindowResourceMonitor"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, app_name)
                return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def set_autostart(self, enable):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "WindowResourceMonitor"
        if getattr(sys, 'frozen', False):
            target_path = sys.executable
        else:
            target_path = sys.argv[0]
        try:
            if enable:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{target_path}"')
            else:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, app_name)
        except Exception:
            pass

    def quit_app(self):
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage(
                "Window Resource Monitor",
                "程序已最小化到系统托盘",
                QSystemTrayIcon.Information,
                1000
            )

    def resizeEvent(self, event):
        """重绘窗口形状：上方圆角、下方直角"""
        rect = self.rect()
        radius = 8
        path = QPainterPath()
        # 从左下角开始，逆时针绘制
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + radius)
        # 左上圆角
        path.arcTo(rect.left(), rect.top(), radius * 2, radius * 2, 180, -90)
        path.lineTo(rect.right() - radius, rect.top())
        # 右上圆角
        path.arcTo(rect.right() - radius * 2, rect.top(), radius * 2, radius * 2, 90, -90)
        path.lineTo(rect.right(), rect.bottom())
        path.closeSubpath()
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        super().resizeEvent(event)

    def update_overlay(self):
        hwnd = get_foreground_window()
        if not hwnd:
            self.hide()
            return
        if is_window_fullscreen(hwnd):
            self.hide()
            self.last_hwnd = None
            return
        left, top, right, bottom = get_window_rect(hwnd)
        width = right - left
        if width <= 0:
            self.hide()
            return
        offset = 2
        self.setGeometry(left, top - self.height() - offset, width, self.height())

        pid = get_window_thread_process_id(hwnd)
        cpu = cpu_calc.get_cpu_percent(pid)
        mem_bytes = 0
        h_process = open_process(pid)
        if h_process:
            mem_bytes = get_process_memory_info(h_process)
            kernel32.CloseHandle(h_process)
        mem_mb = mem_bytes / (1024 * 1024)

        self.label.setText(f"PID: {pid} | CPU: {cpu:.1f}% | MEM: {mem_mb:.1f} MB")
        self.show()
        self.last_hwnd = hwnd

# ---------- 主程序 ----------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = OverlayWidget()
    overlay.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()