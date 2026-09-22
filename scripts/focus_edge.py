import ctypes
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

user32 = ctypes.windll.user32

def list_and_focus():
    found = []
    def enum_windows_callback(hwnd, extra):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if 'NovaCut' in title or 'Edge' in title:
                    found.append((hwnd, title))
                    print(f"-> Tim thay: HWND {hwnd} | {title}")
                    # Show and bring to front
                    user32.ShowWindow(hwnd, 9) # SW_RESTORE
                    user32.ShowWindow(hwnd, 3) # SW_MAXIMIZE
                    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                    user32.SetForegroundWindow(hwnd)
        return True

    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(EnumProc(enum_windows_callback), 0)
    if not found:
        print("Khong tim thay cua so NovaCut/Edge nao tren desktop!")

if __name__ == "__main__":
    list_and_focus()
