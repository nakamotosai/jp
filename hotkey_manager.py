import sys
from PyQt6.QtCore import QObject, pyqtSignal
import keyboard

class HotkeySignals(QObject):
    asr_pressed = pyqtSignal()
    asr_released = pyqtSignal()
    toggle_ui = pyqtSignal()

class HotkeyManager(QObject):
    def __init__(self, asr_key_str="ctrl+windows", toggle_ui_str="alt+windows"):
        super().__init__()
        self.signals = HotkeySignals()
        self.asr_key_str = asr_key_str
        self.toggle_ui_str = toggle_ui_str
        self._is_hooked = False
        self._asr_active = False

    def set_hotkeys(self, asr_key, toggle_ui):
        # 使用正则确保只替换独立的 'win' 或 'meta'，不破坏已有的 'windows'
        import re
        def normalize_hotkey(s):
            s = s.lower()
            s = re.sub(r'\bmeta\b', 'windows', s)
            s = re.sub(r'\bwin\b', 'windows', s)
            return s
        self.asr_key_str = normalize_hotkey(asr_key)
        self.toggle_ui_str = normalize_hotkey(toggle_ui)

    def start(self):
        if not self._is_hooked:
            try:
                # 开启全局 Hook
                keyboard.hook(self._on_key_event, suppress=False) 
                self._is_hooked = True
                print("[HotkeyManager] Keyboard hook started")
            except Exception as e:
                print(f"[HotkeyManager] Start hook failed: {e}")

    def stop(self):
        if self._is_hooked:
            try:
                keyboard.unhook(self._on_key_event)
                self._is_hooked = False
            except Exception as e:
                print(f"[HotkeyManager] Stop hook failed: {e}")

    def is_alive(self):
        return self._is_hooked

    def _on_key_event(self, e):
        """
        处理所有键盘事件。
        返回 False 表示拦截该事件（不传递给其他App），
        返回 True 表示放行。
        """
        try:
            # 1. 检测 ASR (按住触发)
            try:
                is_asr_pressed = keyboard.is_pressed(self.asr_key_str)
            except ValueError:
                is_asr_pressed = False # 快捷键格式错误

            # 状态翻转检测
            if is_asr_pressed and not self._asr_active:
                # 从未激活变为激活
                self._asr_active = True
                self.signals.asr_pressed.emit()
                return False # 拦截，实现独占

            if not is_asr_pressed and self._asr_active:
                # 从激活变为未激活 (松开)
                self._asr_active = False
                self.signals.asr_released.emit()
                # 释放事件暂时不拦截，避免某些修饰键卡死
                return True 
                
            # 如果处于激活状态中，拦截所有相关事件防止冲突
            if self._asr_active:
                # 简单拦截所有事件可能太激进，但为了保证"独占"，拦截最后按下的键是关键。
                # 由于我们这里是在 hook 中，如果 is_asr_pressed 为真，说明都在按着。
                # 拦截当前事件。
                return False

            # 2. 检测 Toggle UI (按下触发)
            if e.event_type == 'down':
                try:
                    if keyboard.is_pressed(self.toggle_ui_str):
                        self.signals.toggle_ui.emit()
                        return False # 拦截
                except ValueError:
                    pass

        except Exception as err:
            print(f"[HotkeyManager] Event error: {err}")
            
        return True

