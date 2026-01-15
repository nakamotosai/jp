import ctypes
import ctypes.wintypes
import time

def get_caret_context():
    # 尝试通过 OLEACC 获取光标前后的信息
    # 这是一个非常简化的尝试，仅供调试
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        
        # 尝试获取 GUI 线程信息
        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.DWORD),
                ("flags", ctypes.wintypes.DWORD),
                ("hwndActive", ctypes.wintypes.HWND),
                ("hwndFocus", ctypes.wintypes.HWND),
                ("hwndCapture", ctypes.wintypes.HWND),
                ("hwndMenuOwner", ctypes.wintypes.HWND),
                ("hwndMoveSize", ctypes.wintypes.HWND),
                ("hwndCaret", ctypes.wintypes.HWND),
                ("rcCaret", ctypes.wintypes.RECT),
            ]
        
        gui = GUITHREADINFO()
        gui.cbSize = ctypes.sizeof(GUITHREADINFO)
        if user32.GetGUIThreadInfo(0, ctypes.byref(gui)):
            print(f"Focused HWND: {gui.hwndFocus}")
            print(f"Caret HWND: {gui.hwndCaret}")
            print(f"Caret Rect: {gui.rcCaret.left}, {gui.rcCaret.top}")
            
        return gui.hwndFocus
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    print("请在 3 秒内切换到其他窗口...")
    time.sleep(3)
    get_caret_context()
