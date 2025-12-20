import sys
import threading
import time
from typing import Optional
import win32gui

class SystemHandler:
    def __init__(self):
        self._last_active_window = None
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._my_window_hwnd = None

    def set_my_window_handle(self, hwnd):
        """Register the application's own window handle to ignore it during tracking."""
        self._my_window_hwnd = hwnd

    def start_focus_tracking(self):
        """Start a background thread to track the actively focused window."""
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._track_focus_loop, daemon=True)
        self._monitor_thread.start()

    def stop_focus_tracking(self):
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join()

    def _track_focus_loop(self):
        while not self._stop_event.is_set():
            hwnd = win32gui.GetForegroundWindow()
            if hwnd and hwnd != self._my_window_hwnd:
                # Add check to ensure it's not a temporary tooltip or menu if possible,
                # but for now, just tracking non-self windows is enough.
                self._last_active_window = hwnd
            time.sleep(0.1)

    def get_last_active_window(self) -> Optional[int]:
        return self._last_active_window

    def restore_focus_to_last_window(self):
        """Switch focus back to the last separate application window."""
        if self._last_active_window and win32gui.IsWindow(self._last_active_window):
            try:
                # Sometimes SetForegroundWindow fails if not allowed, simpler approach is usually best
                win32gui.SetForegroundWindow(self._last_active_window)
            except Exception as e:
                print(f"Failed to restore focus: {e}")

    def paste_text(self, text):
        if not text: return
        try:
            import pyperclip
            from pynput.keyboard import Controller, Key
            pyperclip.copy(text)
            self.restore_focus_to_last_window()
            time.sleep(0.1)
            keyboard = Controller()
            with keyboard.pressed(Key.ctrl):
                keyboard.press('v')
                keyboard.release('v')
        except Exception as e:
            print(f"Paste error: {e}")
