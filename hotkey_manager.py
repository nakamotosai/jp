import sys
from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard

class HotkeySignals(QObject):
    caps_pressed = pyqtSignal()
    caps_released = pyqtSignal()

class HotkeyManager(QObject):
    def __init__(self, callback=None):
        super().__init__()
        self.signals = HotkeySignals()
        self.callback = callback
        self.listener = None
        self._caps_pressed = False

    def start(self):
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()

    def _on_press(self, key):
        if key == keyboard.Key.caps_lock:
            if not self._caps_pressed:
                self._caps_pressed = True
                self.signals.caps_pressed.emit()

    def _on_release(self, key):
        if key == keyboard.Key.caps_lock:
            self._caps_pressed = False
            self.signals.caps_released.emit()

    def stop(self):
        if self.listener:
            self.listener.stop()
