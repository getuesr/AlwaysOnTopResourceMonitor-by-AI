# Py 浮动窗口资源监视器
这个是DeepSeek写的基于py浮动窗口性能监视器(浮动窗口在活跃窗口上方) 原因是我找到很少的类似资源监视器 让AI写了一份 您可以下载 然后修改它 它是完全公开的。 它会在活跃窗口上显示一个浮动窗口 并显示程序的 PID CPU占用和内存占用
出现严重的问题是豆包修复的 代码无毒

📦 依赖库清单
库名 最低版本 用途
PyQt5 5.15.0 创建浮动窗口、托盘图标、界面渲染
pywin32 305 调用 Windows API（获取窗口句柄、进程信息、注册表操作）

指令安装 pip install PyQt5 pywin32

exe是打包好的 直接运行就可以了 目前没有图标 托盘是小圆点 可以退出 或者开机自启动


# Py Floating Window Resource Monitor
This is a Py floating window performance monitor written by DeepSeek (the floating window appears above the active window). The reason is that I found very few similar resource monitors, so I had AI write one. You can download it and then modify it; it is completely open. It will display a floating window on top of the active window and show the program's PID, CPU usage, and memory usage.

Serious issues have been fixed by Doubao. The code is harmless.

📦 Dependency List
Library Name  Minimum Version  Purpose
PyQt5         5.15.0           Create floating window, tray icon, UI rendering
pywin32       305              Call Windows API (get window handles, process information, registry operations)

Install command: pip install PyQt5 pywin32

The exe is packaged and can be run directly. Currently, there is no icon; the tray is a small dot. You can exit or set it to run on startup.
