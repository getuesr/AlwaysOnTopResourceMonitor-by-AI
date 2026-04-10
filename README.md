# Py 浮动窗口资源监视器
这个是DeepSeek写的基于py浮动窗口性能监视器(浮动窗口在活跃窗口上方) 原因是我找到很少的类似资源监视器 让AI写了一份 您可以下载 然后修改它 它是完全公开的。 它会在活跃窗口上显示一个浮动窗口 并显示程序的 PID CPU占用和内存占用
📦 依赖库清单
库名 最低版本 用途
PyQt5 5.15.0 创建浮动窗口、托盘图标、界面渲染
pywin32 305 调用 Windows API（获取窗口句柄、进程信息、注册表操作）

指令安装 pip install PyQt5 pywin32

exe是打包好的 直接运行就可以了 目前没有图标 托盘是小圆点 可以退出 或者开机自启动

# Py Floating Window Resource Monitor
This is a performance monitor with a floating window (floating above the active window) written by DeepSeek in Python. The reason is that I found very few similar resource monitors, so I had AI write one. You can download it and then modify it; it is completely open. It will display a floating window over the active window and show the program's PID, CPU usage, and memory usage.

📦 Dependency List
Library Name | Minimum Version | Purpose
PyQt5 | 5.15.0 | Create floating windows, tray icons, and render the interface
pywin32 | 305 | Call Windows API (get window handles, process information, registry operations)

Command to install: pip install PyQt5 pywin32

The exe is packaged and can be run directly. Currently, there is no icon; the tray shows a small dot. You can exit it or enable it to start on boot.
