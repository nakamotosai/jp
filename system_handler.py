import sys
import threading
import time
from typing import Optional, Set, Callable
import win32gui
import win32con

class SystemHandler:
    def __init__(self):
        self._last_active_window = None
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._my_window_hwnds: Set[int] = set()  # 支持多个窗口句柄
        self._tracking_started = False
        self._pending_paste_text = None  # 等待粘贴的文本
        self._pending_paste_callback = None  # 粘贴完成后的回调

    def is_likely_insertion(self, threshold=5.0) -> bool:
        """
        判断是否可能处于插入模式。
        直接使用 UIA 实时探测光标位置。
        
        Returns:
            True: 插入模式 (光标在中间, 禁止句号)
            False: 追加/新建模式 (光标在末尾或空, 允许句号)
        """
        try:
            is_at_end = self._check_caret_at_end_uia()
            if is_at_end is not None:
                # 如果明确知道光标在末尾 (True)，则不是插入模式 (返回 False)
                # 如果明确知道光标不在末尾 (False)，则是插入模式 (返回 True)
                # 使用 not 将 "是否在末尾" 转换为 "是否插入"
                return not is_at_end
        except Exception as e:
            pass

        # [Fallback] 如果 UIA 完全失败，默认假设是追加模式 (False)
        # 以满足用户"新输入框必须有句号"的强需求
        return False


                
    def is_text_input_focused(self) -> bool:
        """检查当前焦点是否是文本输入控件"""
        try:
            import uiautomation as auto
            auto.SetGlobalSearchTimeout(0.2)
            focused = auto.GetFocusedControl()
            if not focused: return False
            
            # 检查是否支持 TextPattern 或 ValuePattern
            if focused.GetPattern(auto.PatternId.TextPattern): return True
            if focused.GetPattern(auto.PatternId.ValuePattern): return True
            
            # 特殊情况：如果是 Edit 控件但没检测到模式，也算
            if focused.ControlTypeName == "EditControl" or focused.ControlTypeName == "DocumentControl":
                return True
                
            return False
        except:
            return False

    def _check_caret_at_end_uia(self) -> Optional[bool]:
        """
        使用 UIAutomation 检查光标是否在文本末尾。
        Returns:
            True: 在末尾 (允许句号)
            False: 不在末尾 (禁止句号)
            None: 无法判断
        """
        try:
            # 动态导入防止启动过慢
            import uiautomation as auto
            auto.SetGlobalSearchTimeout(0.2) # 快速超时，避免卡顿
            
            focused = auto.GetFocusedControl()
            if not focused: return None
            
            # [DEBUG LOG]
            try:
                with open("uia_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"\n[UIA] Focused: {focused.Name} ({focused.ControlTypeName})\n")
            except: pass

            # A. 尝试 TextPattern (Word, Notepad, Browser inputs)
            pattern = focused.GetPattern(auto.PatternId.TextPattern)
            if pattern:
                selections = pattern.GetSelection()
                if not selections: 
                    try:
                        with open("uia_debug.log", "a", encoding="utf-8") as f:
                            f.write(f"[UIA] TextPattern found but No Selection.\n")
                    except: pass
                    return None
                caret = selections[0]
                
                chk_range = caret.Clone()
                # [Fix V4] Move + Peek 策略
                # 即使 Move 返回 1，也可能是跨过了末尾的换行符或空格
                # 所以我们必须看看跨过去的到底是什么东西
                moved = chk_range.Move(auto.TextUnit.Character, 1)
                
                if moved == 0:
                    # 移不动，肯定是末尾
                    is_at_end = True
                    peek_char = "<End>"
                else:
                    # 移之后，Range 变成了一个点。扩展它以包含刚才跨过的字符
                    chk_range.ExpandToEnclosingUnit(auto.TextUnit.Character)
                    peek_char = chk_range.GetText()
                    
                    # 关键判定：如果右边的字符是空的或者是空白符(换行/空格)，我们认为它仍然是在"逻辑末尾"
                    # 只有右边是实实在在的文字时，才算插入
                    if not peek_char or peek_char.isspace():
                        is_at_end = True
                    else:
                        is_at_end = False

                try:
                    with open("uia_debug.log", "a", encoding="utf-8") as f:
                        f.write(f"[UIA] TextMethod: Move={moved}, Peek='{repr(peek_char)}', IsAtEnd={is_at_end}\n")
                except: pass

                return is_at_end
            
            # B. 尝试 ValuePattern (Simple Edit Controls)
            val_pattern = focused.GetPattern(auto.PatternId.ValuePattern)
            if val_pattern:
                val = val_pattern.Value
                is_empty = not val
                try:
                    with open("uia_debug.log", "a", encoding="utf-8") as f:
                        f.write(f"[UIA] ValuePattern: Value='{val[:20]}...', IsEmpty={is_empty}\n")
                except: pass
                
                if is_empty: # 空文本
                    return True
                # 如果不为空，无法确知光标位置，只能返回 None
                
            try:
                with open("uia_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"[UIA] No Pattern matched (Text/Value). Fallback.\n")
            except: pass
            return None
        except Exception as e:
            try:
                with open("uia_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"[UIA] Exception: {e}\n")
            except: pass
            return None


    def add_my_window_handle(self, hwnd):
        """Register an application window handle to ignore during tracking."""
        if hwnd:
            self._my_window_hwnds.add(int(hwnd))
            # [Added] Log for debugging
            try:
                title = win32gui.GetWindowText(int(hwnd))
                print(f"[SystemHandler] Registered ignore window: {hwnd} ({title})")
            except: pass

    def set_my_window_handle(self, hwnd):
        """Legacy method - adds a window handle."""
        self.add_my_window_handle(hwnd)

    def start_focus_tracking(self):
        """Start a background thread to track the actively focused window."""
        if self._tracking_started:
            return  # 防止重复启动
        self._tracking_started = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._track_focus_loop, daemon=True)
        self._monitor_thread.start()

    def stop_focus_tracking(self):
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join()
        self._tracking_started = False

    def _track_focus_loop(self):
        while not self._stop_event.is_set():
            hwnd = win32gui.GetForegroundWindow()
            # 只有当焦点窗口不是我们自己的任何窗口时才记录
            if hwnd and hwnd not in self._my_window_hwnds:
                # 如果有等待粘贴的文本，且检测到新的外部窗口获得焦点
                if self._pending_paste_text:
                    text = self._pending_paste_text
                    # 双重检查：确保当前窗口真的是有效的前台窗口
                    if win32gui.IsWindowVisible(hwnd):
                        print(f"[FocusTracker] Detected focus: {hwnd}, triggering delayed paste.")
                        self._pending_paste_text = None  # 清除，防止重复粘贴
                        time.sleep(0.2)  # 等待窗口完全激活
                        self._do_paste(text, should_send=False)
                        if self._pending_paste_callback:
                            try:
                                self._pending_paste_callback()
                            except:
                                pass
                            self._pending_paste_callback = None
                
                self._last_active_window = hwnd
            time.sleep(0.1)

    def get_last_active_window(self) -> Optional[int]:
        return self._last_active_window

    def has_target_window(self) -> bool:
        """检查是否有有效的目标窗口"""
        return self._last_active_window is not None and win32gui.IsWindow(self._last_active_window)

    def restore_focus_to_last_window(self) -> bool:
        """Switch focus back to the last separate application window. Returns True if successful."""
        if self._last_active_window and win32gui.IsWindow(self._last_active_window):
            try:
                win32gui.SetForegroundWindow(self._last_active_window)
                return True
            except Exception as e:
                print(f"Failed to restore focus: {e}")
        return False

    def set_pending_paste(self, text: str, callback: Callable = None):
        """设置等待粘贴的文本，当下一个外部窗口获得焦点时自动粘贴"""
        self._pending_paste_text = text
        self._pending_paste_callback = callback
        print(f"[SystemHandler] Pending paste set for text: {text[:10]}...")

    def clear_pending_paste(self):
        """清除等待粘贴的文本"""
        self._pending_paste_text = None
        self._pending_paste_callback = None

    def copy_to_clipboard(self, text: str):
        """只复制文本到剪贴板，不粘贴"""
        if not text: return
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception as e:
            print(f"Copy error: {e}")

    def _do_paste(self, text, should_send=False):
        """执行粘贴操作"""
        try:
            import pyperclip
            from pynput.keyboard import Controller, Key
            pyperclip.copy(text)
            time.sleep(0.05)
            keyboard = Controller()
            with keyboard.pressed(Key.ctrl):
                keyboard.press('v')
                keyboard.release('v')
            
            if should_send:
                time.sleep(0.05)
                keyboard.press(Key.enter)
                keyboard.release(Key.enter)
        except Exception as e:
            print(f"Paste error: {e}")

    def paste_text(self, text, should_send=False):
        # [DEBUG] Write to a specific log file to bypass buffering issues
        try:
            with open("paste_debug.log", "a", encoding="utf-8") as f:
                f.write(f"[Paste] Text='{text}', Send={should_send}\n")
        except: pass

        if not text: return
        
        # 1. 尝试恢复焦点
        print("[SystemHandler] Attempting to restore focus...")
        restored = self.restore_focus_to_last_window()
        
        # 2. 判断是否是有效的文本输入目标
        #    即使恢复焦点成功，从机制上也可能只是恢复到了桌面/Taskbar等无效窗口
        #    利用 UIA 判断当前焦点是否是真正的 Input/Edit 控件
        is_valid_input = False
        if restored:
            # 等待一小会儿确保 UIA 能获取到焦点
            time.sleep(0.05)
            is_valid_input = self.is_text_input_focused()

        # 3. 如果无法恢复焦点 OR 恢复但这并不是一个输入框 (智能延迟)
        if not restored or not is_valid_input:
            print(f"[SystemHandler] Delayed Paste Triggered. (Restored={restored}, IsEdit={is_valid_input})")
            # 先复制到剪贴板，以便用户手动粘贴
            self.copy_to_clipboard(text)
            # 设置挂起，等待用户点击真正的输入框
            self.set_pending_paste(text)
            return

        # 4. 如果成功恢复焦点且是有效的输入框，立即执行粘贴
        time.sleep(0.1) 
        self._do_paste(text, should_send) 

