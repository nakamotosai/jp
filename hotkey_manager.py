import sys
from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard

class HotkeySignals(QObject):
    asr_pressed = pyqtSignal()
    asr_released = pyqtSignal()
    toggle_ui = pyqtSignal()

class HotkeyManager(QObject):
    def __init__(self, asr_key_str="caps_lock", toggle_ui_str="alt+z"):
        super().__init__()
        self.signals = HotkeySignals()
        self.listener = None
        
        self.asr_key_str = asr_key_str.lower()
        self.toggle_ui_str = toggle_ui_str.lower()
        
        self.current_pressed = set()
        self._asr_active = False

    def set_hotkeys(self, asr_key, toggle_ui):
        self.asr_key_str = asr_key.lower()
        self.toggle_ui_str = toggle_ui.lower()

    def _get_key_str(self, key):
        """Convert pynput key to consistent string representation."""
        if hasattr(key, 'char') and key.char:
            return key.char.lower()
        if hasattr(key, 'name'):
            name = key.name.lower()
            if name in ['alt_l', 'alt_gr', 'alt_r']: return 'alt'
            if name in ['ctrl_l', 'ctrl_r']: return 'ctrl'
            if name in ['shift_l', 'shift_r']: return 'shift'
            if name in ['cmd', 'cmd_l', 'cmd_r', 'meta']: return 'meta'
            return name
        return str(key).lower()

    def _is_match(self, combo_str):
        """Check if current_pressed matches the combo_str (e.g. 'alt+z')."""
        target_keys = set(combo_str.split('+'))
        pressed_keys = {self._get_key_str(k) for k in self.current_pressed}
        # For combos like alt+z, we check if all target keys are in pressed_keys
        # and if the total count matches to avoid 'ctrl+alt+z' matching 'alt+z'
        return target_keys == pressed_keys

    def start(self):
        if self.listener and self.listener.is_alive():
            return
        
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()

    def is_alive(self):
        return self.listener and self.listener.is_alive()

    def _on_press(self, key):
        try:
            self.current_pressed.add(key)
            
            # 1. Check ASR (Hold mode) - Support both single key and combinations
            if '+' in self.asr_key_str:
                if self._is_match(self.asr_key_str):
                    if not self._asr_active:
                        self._asr_active = True
                        self.signals.asr_pressed.emit()
            else:
                if self._get_key_str(key) == self.asr_key_str:
                    if not self._asr_active:
                        self._asr_active = True
                        self.signals.asr_pressed.emit()
                    
            # 2. Check UI Toggle (Combination or single key)
            if '+' in self.toggle_ui_str:
                if self._is_match(self.toggle_ui_str):
                    # UI toggle is usually a one-shot trigger on press
                    self.signals.toggle_ui.emit()
            else:
                if self._get_key_str(key) == self.toggle_ui_str:
                    self.signals.toggle_ui.emit()
        except Exception as e:
            print(f"[HotkeyManager] Error in _on_press: {e}")

    def _on_release(self, key):
        try:
            k_str = self._get_key_str(key)
            
            # ASR Release logic
            if self._asr_active:
                # If any part of the combination is released, or the single key is released
                if '+' in self.asr_key_str:
                    if k_str in self.asr_key_str.split('+'):
                        self._asr_active = False
                        self.signals.asr_released.emit()
                else:
                    if k_str == self.asr_key_str:
                        self._asr_active = False
                        self.signals.asr_released.emit()
                
            if key in self.current_pressed:
                self.current_pressed.remove(key)
        except Exception as e:
            print(f"[HotkeyManager] Error in _on_release: {e}")

    def stop(self):
        if self.listener:
            self.listener.stop()
