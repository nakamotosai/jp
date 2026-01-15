import sys, os, ctypes, json, multiprocessing, subprocess, re
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

from model_config import get_model_config, ASROutputMode, TranslatorEngineType
from asr_manager import ASRManager
from asr_mode import ASRModeWindow
from asr_jp_mode import ASRJpModeWindow
from ui_manager import TranslatorWindow, FloatingVoiceIndicator
from hotkey_manager import HotkeyManager
from tray_icon import AppTrayIcon
from audio_recorder import AudioRecorder
from translator_engine import TranslationWorker, TranslatorEngine
from system_handler import SystemHandler
from update_manager import UpdateManager
from settings_window import SettingsWindow
from ui_components import TeachingTip

try:
    import tts_worker
except ImportError:
    tts_worker = None

class AppController(QObject):
    sig_do_translate = pyqtSignal(str)
    sig_change_engine = pyqtSignal(str)

    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.m_cfg = get_model_config()
        self._last_engine_id = self.m_cfg.current_translator_engine # 记录上一次的引擎ID
        self._settings_window = None  # 设置窗口引用
        self._is_translating = False # 翻译状态标志
        
        # 1. Models & Managers
        self.asr_manager = ASRManager()
        self.tr_engine = TranslatorEngine()
        self.audio_recorder = AudioRecorder()
        self.sys_handler = SystemHandler()
        
        # 2. UI - Progressive Creation
        self.app_mode = self.m_cfg.data.get("app_mode", "asr")
        
        # Create ONLY the active window first for instant feedback
        self.asr_window = None
        self.asr_jp_window = None
        self.tr_window = None
        
        if self.app_mode == "asr":
            self.asr_window = ASRModeWindow()
            self.window = self.asr_window
        elif self.app_mode == "asr_jp":
            self.asr_jp_window = ASRJpModeWindow()
            self.window = self.asr_jp_window
        else:
            self.tr_window = TranslatorWindow()
            self.window = self.tr_window
            
        if self.m_cfg.get_show_on_start():
            self.window.show()
        
        self.tray = AppTrayIcon()
        self.tray.set_mode_checked(self.app_mode)
        
        # 悬浮录音指示器 (隐藏界面时使用)
        self.voice_indicator = FloatingVoiceIndicator()
        
        # 3. Deferred initialization for high performance
        QTimer.singleShot(50, self._deferred_init)
        
        # 4. First-time Teaching Tip
        if not self.m_cfg.tip_shown:
            QTimer.singleShot(1500, self._show_teaching_tip)

    def _show_teaching_tip(self):
        self.tip = TeachingTip()
        self.tip.show_beside(self.window)
        self.m_cfg.tip_shown = True # Mark as shown
        self.m_cfg.save_config()

    def _deferred_init(self):
        """Second phase of loading: create background windows and start engines"""
        # 0. Check for updates (Async)
        QTimer.singleShot(2000, lambda: UpdateManager.check_for_updates(self.window))

        # Create windows that weren't created yet
        if not self.asr_window: self.asr_window = ASRModeWindow()
        if not self.asr_jp_window: self.asr_jp_window = ASRJpModeWindow()
        if not self.tr_window: self.tr_window = TranslatorWindow()
        self.all_windows = [self.asr_window, self.asr_jp_window, self.tr_window]

        # 4. Hotkey Manager (Start after UI is shown)
        self.hotkey_mgr = HotkeyManager(
            asr_key_str=self.m_cfg.hotkey_asr,
            toggle_ui_str=self.m_cfg.hotkey_toggle_ui
        )
        self.hotkey_mgr.signals.asr_pressed.connect(self.on_asr_down)
        self.hotkey_mgr.signals.asr_released.connect(self.on_asr_up)
        self.hotkey_mgr.signals.toggle_ui.connect(self.toggle_main_ui)
        self.hotkey_mgr.signals.backspace_pressed.connect(self.check_correction)
        self.hotkey_mgr.signals.period_pressed.connect(self.check_force_period_learning)

        # 5. Async Worker
        self.tr_thread = QThread()
        self.tr_worker = TranslationWorker(self.tr_engine)
        self.tr_worker.moveToThread(self.tr_thread)
        self.sig_do_translate.connect(self.tr_worker.on_translate_requested)
        self.sig_change_engine.connect(self.tr_worker.on_engine_change_requested)
        self.tr_worker.result_ready.connect(self.on_translation_finished)
        self.tr_worker.status_changed.connect(self.on_worker_status_changed)
        self.tr_thread.start()
        
        # Connect UI Signals for all windows
        self.tray.activated.connect(self.on_tray_activated)
        for win in self.all_windows:
            self._connect_win_signals(win)
            # 注册所有窗口句柄，确保焦点追踪能正确排除它们
            self.sys_handler.add_my_window_handle(int(win.winId()))
        
        # 启动焦点追踪和热键监听（在窗口注册完成后）
        self.sys_handler.start_focus_tracking()
        self.hotkey_mgr.start()
            
        if hasattr(self.tr_window, 'requestTranslation'):
            self.tr_window.requestTranslation.connect(self.handle_translation_request)
            
        self.audio_recorder.started.connect(self.on_recording_state_changed)
        self.audio_recorder.stopped.connect(self.on_recording_state_changed)
        self.audio_recorder.audio_ready.connect(self._handle_audio_ready)
        self.audio_recorder.level_updated.connect(self.handle_audio_level)
        
        self.asr_manager.model_ready.connect(lambda: self.on_worker_status_changed("idle"))
        self.asr_manager.result_ready.connect(self.handle_asr_result)
        self.asr_manager.error.connect(lambda e: print(f"ASR Error: {e}"))

        # 6. Trigger engine loads after a short buffer
        QTimer.singleShot(200, lambda: self.asr_manager.start())
        QTimer.singleShot(400, lambda: self.sig_change_engine.emit(self.m_cfg.current_translator_engine))
        
        # Hotkey Watchdog
        self.hotkey_watchdog = QTimer()
        self.hotkey_watchdog.timeout.connect(self.check_hotkey_status)
        self.hotkey_watchdog.start(30000)
        
        self.on_worker_status_changed("asr_loading")
        self.handle_mode_change(self.app_mode) # Refresh state
        
        # [Task] 初始化托盘菜单
        self._update_tray_menu()

    def _update_tray_menu(self):
        """Update the tray context menu using shared logic"""
        from ui_manager import create_context_menu
        from PyQt6.QtCore import pyqtSignal, QObject
        
        # Create a proxy object to map menu signals to Main methods
        class TrayProxy(QObject):
            requestAppModeChange = pyqtSignal(str) # [Fix] Added mode change signal
            requestScaleChange = pyqtSignal(float)
            requestThemeChange = pyqtSignal(str)
            requestFontChange = pyqtSignal(str)
            requestOpenSettings = pyqtSignal()
            requestRestart = pyqtSignal()
            requestQuit = pyqtSignal()
            
        self.tray_proxy = TrayProxy()
        self.tray_proxy.requestAppModeChange.connect(self.handle_mode_change) # [Fix] Connect mode change
        self.tray_proxy.requestScaleChange.connect(self.handle_scale_change)
        self.tray_proxy.requestThemeChange.connect(self.handle_theme_change)
        self.tray_proxy.requestFontChange.connect(self.handle_font_change)
        self.tray_proxy.requestOpenSettings.connect(self.open_settings)
        self.tray_proxy.requestRestart.connect(self.restart_app)
        self.tray_proxy.requestQuit.connect(self.app.quit)
        
        # [Task] Fix tray focus and sync issues
        # Remove static context menu assignment
        # self.tray_menu = create_context_menu(None, self.m_cfg, self.tray_proxy)
        # self.tray.setContextMenu(self.tray_menu)
        
        try: self.tray.activated.disconnect()
        except: pass
        self.tray.activated.connect(self.on_tray_activated)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context:
            # Dynamically create menu to ensure sync
            from ui_manager import create_context_menu
            from PyQt6.QtGui import QCursor
            import ctypes
            
            # Create fresh menu
            menu = create_context_menu(None, self.m_cfg, self.tray_proxy)
            
            # [Fix] Force foreground to solve focus/closing issue
            try:
                ctypes.windll.user32.SetForegroundWindow(int(self.window.winId()))
            except: pass
            
            menu.exec(QCursor.pos())

    def _connect_win_signals(self, win):
        win.requestSend.connect(self.handle_send_request)
        win.requestRecordStart.connect(self.on_asr_down)
        win.requestRecordStop.connect(self.on_asr_up)
        
        if hasattr(win, "requestAppModeChange"): win.requestAppModeChange.connect(self.handle_mode_change)
        if hasattr(win, "requestASREngineChange"): win.requestASREngineChange.connect(self.handle_asr_engine_change)
        if hasattr(win, "requestTranslatorEngineChange"): win.requestTranslatorEngineChange.connect(self.handle_engine_change)
        if hasattr(win, "requestASROutputModeChange"): win.requestASROutputModeChange.connect(self.handle_asr_output_mode_change)
        if hasattr(win, "requestAutoTTSChange"): win.requestAutoTTSChange.connect(self.handle_auto_tts_change)
        if hasattr(win, "requestTTSDelayChange"): win.requestTTSDelayChange.connect(self.handle_tts_delay_change)
        if hasattr(win, "requestThemeChange"): win.requestThemeChange.connect(self.handle_theme_change)
        if hasattr(win, "requestScaleChange"): win.requestScaleChange.connect(self.handle_scale_change)
        if hasattr(win, "requestFontChange"): win.requestFontChange.connect(self.handle_font_change)
        if hasattr(win, "requestFontSizeChange"): win.requestFontSizeChange.connect(self.handle_font_size_change)
        if hasattr(win, "requestRestart"): win.requestRestart.connect(self.restart_app)
        if hasattr(win, "requestQuit"): win.requestQuit.connect(self.app.quit)
        if hasattr(win, "requestPersonalityChange"): win.requestPersonalityChange.connect(self.handle_personality_change)
        if hasattr(win, "requestHotkeyChange"): win.requestHotkeyChange.connect(self.handle_hotkey_change)
        if hasattr(win, "requestOpenSettings"): win.requestOpenSettings.connect(self.open_settings)
        
        # 中日双显模式特有信号
        if hasattr(win, "sigTranslationStarted"):
            win.sigTranslationStarted.connect(self.on_translation_started)

        self._caps_was_on = False
        self.handle_mode_change(self.app_mode) # Refresh state

    def check_hotkey_status(self):
        """Monitor the health of the hotkey listener and restart if dead."""
        if not self.hotkey_mgr.is_alive():
            print("[Watchdog] Hotkey listener died. Restarting...")
            self.hotkey_mgr.start()

    def _get_active_window(self):
        if self.app_mode == "asr": return self.asr_window
        if self.app_mode == "asr_jp": return self.asr_jp_window
        return self.tr_window

    def handle_mode_change(self, mode_id):
        self.app_mode = mode_id
        for win in self.all_windows: win.hide()
        self.window = self._get_active_window()
        self.window.show()
        self.tray.set_mode_checked(mode_id)
        self.m_cfg.app_mode = mode_id # 这会自动触发 save_config

    def on_asr_down(self):
        # [Async] 按下瞬间立即触发光标探测
        self.sys_handler.trigger_insertion_check()
        
        self.window.update_recording_status(True)
        self.audio_recorder.start_recording()
        
        # 如果当前是 ASR 模式且界面是隐藏的，显示悬浮指示器
        if self.app_mode in ["asr", "asr_jp"] and not self.window.isVisible():
            self.voice_indicator.show()

    def on_asr_up(self):
        self.window.update_recording_status(False)
        self.audio_recorder.stop_recording()
        
        # 隐藏悬浮指示器
        self.voice_indicator.hide()
        
        # 中日双显模式：录音结束后保持窗口焦点
        if self.app_mode == "translation":
            self.window.activateWindow()
            self.window.raise_()
            if hasattr(self.window, "focus_input"):
                self.window.focus_input()

    def toggle_main_ui(self):
        is_visible = self.window.isVisible()
        if is_visible:
            for win in self.all_windows: win.hide()
        else:
            # 确保窗口从任何状态恢复（包括最小化）并置顶
            self.window.show()
            self.window.showNormal() 
            self.window.raise_()
            self.window.activateWindow()
            
            # 针对 Windows 的强力激活：解决显示后点击不响应的问题
            if sys.platform == "win32":
                try:
                    import ctypes
                    # 尝试设置前台窗口
                    hwnd = int(self.window.winId())
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except:
                    pass

            if hasattr(self.window, "focus_input"):
                self.window.focus_input()

    def _handle_audio_ready(self, audio_data):
        # [Async] 使用按下时已经开启探测并缓存的结果
        # 此时探测线程应该早已完成
        is_ins = self.sys_handler.get_cached_insertion()
        self.asr_manager.transcribe_async(audio_data, is_insertion=is_ins)

    def handle_asr_result(self, result):
        print(f"[Main] Received ASR result: '{result}'")
        if not result: return
        self.window.update_segment(result)
        if self.app_mode == "asr":
             self.handle_send_request(result)
        elif self.app_mode == "asr_jp":
             self.handle_translation_request(result)
        elif self.app_mode == "translation":
             # 标记当前翻译是由 ASR 触发的，翻译完成后需要自动粘贴
             self._is_asr_triggered_translation = True
             # 注意：translation 模式下 UI 已经通过信号监听了文本变化并触发翻译
             # 所以这里不需要手动调用 handle_translation_request，除非 debounce 太长
             # 但为了稳妥，我们可以直接触发翻译以提高即时性
             self.handle_translation_request(result)

    def on_translation_started(self):
        """当用户开始在中日双显模式输入时调用"""
        self._is_translating = True

    def handle_translation_request(self, text):
        # 新翻译请求时重置TTS记录，确保新文本可以播放
        if hasattr(self, '_last_tts_text') and self._last_tts_text != text:
            self._last_tts_text = None
        
        self._is_translating = True # 标记正在翻译
        self.sig_do_translate.emit(text)

    def on_translation_finished(self, text):
        self._is_translating = False # 翻译结束
        if not text: return
        
        if self.app_mode == "translation":
            self.tr_window.on_translation_ready(text)
            # 中日双显模式：自动复制日文到剪贴板
            self.sys_handler.copy_to_clipboard(text)
            
            # 如果是 ASR 触发的翻译，自动粘贴到目标窗口
            if getattr(self, '_is_asr_triggered_translation', False):
                self._is_asr_triggered_translation = False
                self.sys_handler.paste_text(text, should_send=False)
        elif self.app_mode == "asr_jp":
            self.asr_jp_window.update_segment(text)
            self.handle_send_request(text)
            
        # TTS 逻辑：每次收到新翻译都打断之前的朗读，重新开始计时
        # 只有停止输入一段时间后才朗读最终结果
        if tts_worker and self.m_cfg.auto_tts:
            # 1. 打断之前正在进行的朗读
            # 1. 移除手动 stop调用，交给 worker 内部处理
            # 避免多线程竞争导致新任务被误杀
            pass
            
            # 2. 取消之前的延迟 timer
            if hasattr(self, '_pending_tts_timer') and self._pending_tts_timer:
                self._pending_tts_timer.stop()
            
            # 3. 创建新的延迟 timer（用户停止输入后才朗读）
            delay_ms = self.m_cfg.tts_delay_ms
            self._pending_tts_timer = QTimer(self)
            self._pending_tts_timer.setSingleShot(True)
            self._pending_tts_timer.timeout.connect(lambda t=text: self._play_tts_delayed(t))
            self._pending_tts_timer.start(delay_ms)

    def _play_tts_delayed(self, text):
        """延迟执行的 TTS 播放 - 只播放一次"""
        # [Safe Fix] 增加防抖逻辑
        import time
        now = time.time()
        last_text = getattr(self, '_last_tts_text_played', None)
        last_time = getattr(self, '_last_tts_time_played', 0)
        
        if text == last_text and (now - last_time) < 3.0:
            print(f"[Main] 忽略重复 TTS 请求: {text}")
            return
            
        self._last_tts_text_played = text
        self._last_tts_time_played = now

        if tts_worker and text:
            import threading
            threading.Thread(target=tts_worker.say, args=(text,), daemon=True).start()

    def handle_send_request(self, text):
        print(f"[Main] Handling send request for '{text}', Mode={self.app_mode}")
        if not text: return
        
        if self.app_mode == "translation":
            # 如果正在翻译中，禁止发送（防止发送上一句翻译）
            if self._is_translating:
                print("[Main] 正在翻译中，忽略发送请求")
                return
            # 中日双显模式特有逻辑
            # 只清空中文输入，保留日文显示
            if hasattr(self.window, "clear_input"):
                self.window.clear_input()
            
            # 检查是否有目标窗口
            if self.sys_handler.has_target_window():
                # 有目标窗口：粘贴+发送+refocus
                self.sys_handler.paste_text(text, should_send=True)
                def refocus():
                    self.window.activateWindow()
                    self.window.raise_()
                    if hasattr(self.window, "focus_input"):
                        self.window.focus_input()
                QTimer.singleShot(100, refocus)
            else:
                # 没有目标窗口：设置待粘贴，等下一个窗口获得焦点时自动粘贴
                def on_paste_done():
                    # 粘贴完成后重新聚焦中日说
                    QTimer.singleShot(200, lambda: self._refocus_translation_window())
                self.sys_handler.set_pending_paste(text, on_paste_done)
                # 立即 refocus 输入框
                self.window.activateWindow()
                self.window.raise_()
                if hasattr(self.window, "focus_input"):
                    self.window.focus_input()
        else:
            # ASR 模式：只粘贴，不发送 Enter
            self.sys_handler.paste_text(text, should_send=False)
            
        # 记录最后粘贴的内容和时间，用于自我学习
        import time
        self.last_pasted_text = text
        self.last_paste_time = time.time()

    def check_correction(self):
        """检查用户是否执行了纠错操作（删除了句号）"""
        try:
            import time
            if not hasattr(self, 'last_pasted_text') or not self.last_pasted_text:
                return
                
            # 只有在粘贴后 5 秒内的回删才被视为纠错
            if time.time() - getattr(self, 'last_paste_time', 0) > 5.0:
                return

            text = self.last_pasted_text.strip()
            # 检查是否以句号/问号/叹号结尾
            if text and text[-1] in "。！？":
                # 获取标点前面的词
                # 简单策略：获取最后2-4个字，或者根据分词？
                # 这里简单提取标点前的最后1-4个中文字符
                content = text[:-1]
                if not content: return
                
                # 提取最后几个字作为"触发词"
                # 例如 "我觉得他。" -> "我觉得他"
                # 为了防止提取太长，只取最后 4 个字内的部分
                # 比如 "这真的很illegal，所以。" -> "所以"
                
                # 使用正则查找最后的“词块”
                # 优先匹配汉字或英文单词
                match = re.search(r'([\u4e00-\u9fa5a-zA-Z]+)$', content)
                if match:
                    last_word = match.group(1)
                    # 限制长度，太长的句子不记录
                    if len(last_word) <= 5:
                        print(f"[Learning] Detected user deletion of period after '{last_word}'")
                        self.m_cfg.learn_no_period_rule(last_word)
                        self.last_pasted_text = None # 清除，防止重复触发
        except Exception as e:
            print(f"[Learning] Check correction failed: {e}")

    def check_force_period_learning(self):
        """检查用户是否执行了补充句号操作"""
        try:
            import time
            if not hasattr(self, 'last_pasted_text') or not self.last_pasted_text:
                return
                
            # 只有在粘贴后 5 秒内的输入才被视为纠错
            if time.time() - getattr(self, 'last_paste_time', 0) > 5.0:
                return

            text = self.last_pasted_text.strip()
            # 检查是否*没有*结尾标点
            if text and text[-1] not in "。！？":
                # 获取最后的分词
                # 简单策略：提取标点前的最后1-4个中文字符
                content = text
                if not content: return
                
                match = re.search(r'([\u4e00-\u9fa5a-zA-Z]+)$', content)
                if match:
                    last_word = match.group(1)
                    if len(last_word) <= 5:
                        print(f"[Learning] Detected manual period addition after '{last_word}'")
                        self.m_cfg.learn_force_period_rule(last_word)
                        self.last_pasted_text = None 
        except Exception as e:
            print(f"[Learning] Check force period failed: {e}")
    
    def _refocus_translation_window(self):
        """重新聚焦中日双显窗口"""
        if self.app_mode == "translation" and self.tr_window:
            self.tr_window.activateWindow()
            self.tr_window.raise_()
            if hasattr(self.tr_window, "focus_input"):
                self.tr_window.focus_input()

    def handle_audio_level(self, level):
        if hasattr(self.window, "update_audio_level"):
            self.window.update_audio_level(level)
        # 同时更新悬浮指示器的音量
        if self.voice_indicator and self.voice_indicator.isVisible():
            self.voice_indicator.set_level(level)

    def on_worker_status_changed(self, status):
        # 过滤：如果当前是纯中文 ASR 模式，忽略翻译引擎的状态信号
        is_trans_status = status in ["loading"] or status in [e.value for e in TranslatorEngineType] or "翻译" in status or "切换" in status
        
        if self.app_mode == "asr" and is_trans_status:
            return
            
        for win in self.all_windows:
            if hasattr(win, "update_status"): win.update_status(status)

    def handle_asr_engine_change(self, engine_id):
        self.asr_manager.switch_engine(engine_id)
        self.save_config()

    def handle_engine_change(self, engine_id):
        self.m_cfg.current_translator_engine = engine_id
        self.sig_change_engine.emit(engine_id)
        self.save_config()

    def handle_asr_output_mode_change(self, mode):
        self.m_cfg.asr_output_mode = mode
        self.save_config()

    def handle_theme_change(self, theme):
        for win in self.all_windows:
            if hasattr(win, 'apply_theme'): win.apply_theme(theme)
        self.save_config()

    def handle_scale_change(self, scale):
        self.m_cfg.window_scale = scale # [Fix] Update config
        for win in self.all_windows:
            if hasattr(win, 'apply_scaling'): win.apply_scaling(scale, win.font_size_factor, win.current_font_name == "思源宋体")
        self.save_config()

    def handle_font_change(self, font_name):
        self.m_cfg.font_name = font_name # [Fix] Update config
        for win in self.all_windows:
            if hasattr(win, 'current_font_name'):
                win.current_font_name = font_name
            if hasattr(win, 'apply_scaling'):
                scale = getattr(win, 'window_scale', 1.0)
                factor = getattr(win, 'font_size_factor', 1.0)
                win.apply_scaling(scale, factor, font_name == "思源宋体")
        self.save_config()

    def handle_font_size_change(self, factor):
        for win in self.all_windows:
            if hasattr(win, 'font_size_factor'):
                win.font_size_factor = factor
            if hasattr(win, 'apply_scaling'):
                scale = getattr(win, 'window_scale', 1.0)
                font_name = getattr(win, 'current_font_name', "思源宋体")
                win.apply_scaling(scale, factor, font_name == "思源宋体")
        self.save_config()

    def handle_personality_change(self, scheme_id):
        self.m_cfg.set_personality_scheme(scheme_id)
        self.on_worker_status_changed("idle")
        self.save_config()

    def handle_hotkey_change(self, asr_key, toggle_ui):
        self.m_cfg.hotkey_asr = asr_key
        self.m_cfg.hotkey_toggle_ui = toggle_ui
        self.hotkey_mgr.set_hotkeys(asr_key, toggle_ui)
        self.save_config()

    def handle_auto_tts_change(self, enabled):
        self.m_cfg.auto_tts = enabled
        self.save_config()

    def handle_tts_delay_change(self, delay_ms):
        self.m_cfg.tts_delay_ms = delay_ms
        print(f"[TTS] 语音延迟设置为: {delay_ms/1000:.0f} 秒")
        self.save_config()

    def open_settings(self):
        """打开设置窗口"""
        active_window = self.window
        active_window.hide()
        
        self._settings_window = SettingsWindow(self.tr_engine)
        self._settings_window.settingsChanged.connect(self._apply_global_settings)
        self._settings_window.engineChangeRequested.connect(self.sig_change_engine.emit)
        self.tr_worker.status_changed.connect(self._on_engine_status_for_settings)
        
        self._settings_window.exec()
        
        try:
            self.tr_worker.status_changed.disconnect(self._on_engine_status_for_settings)
        except:
            pass
        
        self._settings_window = None
        QTimer.singleShot(100, active_window.show)
    
    def _on_engine_status_for_settings(self, status: str):
        """处理引擎状态变化，更新设置窗口"""
        if self._settings_window:
            self._settings_window.on_engine_loaded(status)

    def _on_settings_changed(self):
        self._apply_global_settings()
        
    def _apply_global_settings(self):
        """应用全局设置"""
        print("[Main] 应用全局配置...")
        current_asr = self.hotkey_mgr.asr_key_str
        current_toggle = self.hotkey_mgr.toggle_ui_str
        def normalize_hotkey(s):
            s = s.lower()
            s = re.sub(r'\bmeta\b', 'windows', s)
            s = re.sub(r'\bwin\b', 'windows', s)
            return s
        new_asr = normalize_hotkey(self.m_cfg.hotkey_asr)
        new_toggle = normalize_hotkey(self.m_cfg.hotkey_toggle_ui)
        
        if new_asr != current_asr or new_toggle != current_toggle:
            print(f"[Main] 检测到热键变更: {current_asr}->{new_asr}, {current_toggle}->{new_toggle}")
            self.hotkey_mgr.stop()
            self.hotkey_mgr.set_hotkeys(self.m_cfg.hotkey_asr, self.m_cfg.hotkey_toggle_ui)
            QTimer.singleShot(100, self.hotkey_mgr.start)
        
        theme = self.m_cfg.theme_mode
        scale = self.m_cfg.window_scale
        font = self.m_cfg.font_name
        
        for win in self.all_windows:
            if hasattr(win, "change_theme"): win.change_theme(theme)
            if hasattr(win, "set_scale_factor"): win.set_scale_factor(scale)
            if hasattr(win, "set_font_name"): win.set_font_name(font)

        self._last_engine_id = self.m_cfg.current_translator_engine

    def save_config(self):
        self.m_cfg.save_config()

    def on_tray_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        from PyQt6.QtGui import QCursor
        if reason == QSystemTrayIcon.ActivationReason.Trigger: # Left Click
            self.toggle_main_ui()
        elif reason == QSystemTrayIcon.ActivationReason.Context: # Right Click
            active_win = self.get_active_window()
            if active_win:
                active_win.activateWindow()
                active_win.show_context_menu(QCursor.pos())

    def get_active_window(self):
        if self.app_mode == "translation": return self.tr_window
        if self.app_mode == "asr": return self.asr_window
        if self.app_mode == "asr_jp": return self.asr_jp_window
        return None

    def restart_app(self):
        os.execl(sys.executable, sys.executable, *sys.argv)

    def on_recording_state_changed(self):
        pass

    def on_wake_up(self):
        """响应单实例唤醒请求"""
        if self.window:
            self.window.show()
            self.window.activateWindow()
            self.window.raise_()

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    import sys
    import os
    if getattr(sys, 'frozen', False):
        from model_config import get_model_config
        cfg = get_model_config()
        log_path = os.path.join(cfg.DATA_DIR, "runtime_error.log")
        try:
            sys.stdout = open(log_path, 'a', encoding='utf-8')
            sys.stderr = sys.stdout
        except:
            pass
            
        import subprocess
        _real_popen = subprocess.Popen
        def _silent_popen(*args, **kwargs):
            if 'creationflags' not in kwargs:
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            return _real_popen(*args, **kwargs)
        subprocess.Popen = _silent_popen
            
    multiprocessing.freeze_support()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtNetwork import QLocalSocket, QLocalServer
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    server_name = "CNJP_Input_Server"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    
    if socket.waitForConnected(500):
        print("已有实例运行中，正在唤醒...")
        socket.write(b"SHOW")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        sys.exit(0)
    
    server = QLocalServer()
    QLocalServer.removeServer(server_name)
    
    if not server.listen(server_name):
        print(f"单实例服务启动失败: {server.errorString()}")
    
    from model_config import get_model_config
    cfg = get_model_config()
    
    controller = AppController(app)
    
    def handle_new_connection():
        client = server.nextPendingConnection()
        if client and client.waitForReadyRead(100):
            cmd = client.readAll().data()
            if cmd == b"SHOW":
                controller.on_wake_up()
    
    server.newConnection.connect(handle_new_connection)
    
    sys.exit(app.exec())
