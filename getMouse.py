import ctypes
import time

# 调用 Windows 底层 API 的准备工作
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_position():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

print("🎯 鼠标坐标探测器已启动！")
print("请把鼠标移动到你想截图的区域，记下坐标数字。")
print("按下 Ctrl + C 可以退出程序。\n")

try:
    while True:
        x, y = get_mouse_position()
        # \r 的作用是让文字在同一行不断刷新，而不会刷满整个屏幕
        print(f"\r当前鼠标坐标:  X: {x:<5}  Y: {y:<5}", end="", flush=True)
        time.sleep(0.1) # 每 0.1 秒刷新一次
except KeyboardInterrupt:
    print("\n\n⏹️ 探测已停止。")