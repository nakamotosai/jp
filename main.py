import sys, os, ctypes, json, multiprocessing, subprocess, re
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

from model_config import get_model_config, ASROutputMode, TranslatorEngineType
from asr_manager import ASRManager
from asr_mode import ASRModeWindow
from asr_jp_mode import ASRJpModeWindow
from ui_manager import TranslatorWindow
from hotkey_manager import HotkeyManager
from tray_icon import AppTrayIcon
from audio_recorder import AudioRecorder
from translator_engine import TranslationWorker, TranslatorEngine
from system_handler import SystemHandler

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
            
        self.window.show() # SHOW IMMEDIATELY!
        
        self.tray = AppTrayIcon()
        self.tray.set_mode_checked(self.app_mode)
        
        # 3. Deferred initialization for high performance
        QTimer.singleShot(50, self._deferred_init)

    def _deferred_init(self):
        """Second phase of loading: create background windows and start engines"""
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
            
        if hasattr(self.tr_window, 'requestTranslation'):
            self.tr_window.requestTranslation.connect(self.handle_translation_request)
            
        self.audio_recorder.started.connect(self.on_recording_state_changed)
        self.audio_recorder.stopped.connect(self.on_recording_state_changed)
        self.audio_recorder.audio_ready.connect(self.asr_manager.transcribe_async)
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

    def _connect_win_signals(self, win):
        win.requestSend.connect(self.handle_send_request)
        win.requestRecordStart.connect(self.on_record_pressed)
        win.requestRecordStop.connect(self.audio_recorder.stop_recording)
        
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

        if self.window:
            self.sys_handler.set_my_window_handle(int(self.window.winId()))
        self.sys_handler.start_focus_tracking()
        self.hotkey_mgr.start()

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
        self.window.update_recording_status(True)
        self.audio_recorder.start_recording()

    def on_asr_up(self):
        self.window.update_recording_status(False)
        self.audio_recorder.stop_recording()

    def toggle_main_ui(self):
        is_visible = self.window.isVisible()
        if is_visible:
            for win in self.all_windows: win.hide()
        else:
            self.window.show()
            self.window.activateWindow()
            self.window.raise_()
            if hasattr(self.window, "focus_input"):
                self.window.focus_input()

    def handle_asr_result(self, result):
        if not result: return
        self.window.update_segment(result)
        if self.app_mode == "asr":
             self.handle_send_request(result)
        elif self.app_mode == "asr_jp":
             self.handle_translation_request(result)

    def handle_translation_request(self, text):
        self.sig_do_translate.emit(text)

    def on_translation_finished(self, text):
        if not text: return
        
        if self.app_mode == "translation":
            self.tr_window.on_translation_ready(text)
        elif self.app_mode == "asr_jp":
            self.asr_jp_window.update_segment(text)
            self.handle_send_request(text)
            
        # TTS call with delay - 等待蓝牙耳机从 HFP 切回 Stereo 模式
        if tts_worker and self.m_cfg.auto_tts:
            # 取消之前挂起的 TTS 请求
            if hasattr(self, '_pending_tts_timer') and self._pending_tts_timer:
                self._pending_tts_timer.stop()
                # 如果有正在播放的语音，也中断它
                try:
                    tts_worker.stop()
                except:
                    pass
            
            # 延迟播放 TTS，等待蓝牙模式切换完成
            delay_ms = self.m_cfg.tts_delay_ms
            self._pending_tts_timer = QTimer()
            self._pending_tts_timer.setSingleShot(True)
            self._pending_tts_timer.timeout.connect(lambda t=text: self._play_tts_delayed(t))
            self._pending_tts_timer.start(delay_ms)

    def _play_tts_delayed(self, text):
        """延迟执行的 TTS 播放"""
        if tts_worker and text:
            import threading
            threading.Thread(target=tts_worker.say, args=(text,), daemon=True).start()

    def handle_send_request(self, text):
        if not text: return
        self.sys_handler.paste_text(text)

    def handle_audio_level(self, level):
        if hasattr(self.window, "update_audio_level"):
            self.window.update_audio_level(level)

    def on_worker_status_changed(self, status):
        # 过滤：如果当前是纯中文 ASR 模式，忽略翻译引擎的状态信号
        # 翻译引擎的状态信号通常是 "loading", "idle", 或具体的模型名
        # ASR 相关的信号通常包含 "asr_" 前缀或 "idle"
        
        is_trans_status = status in ["loading"] or status in [e.value for e in TranslatorEngineType] or "翻译" in status or "切换" in status
        
        if self.app_mode == "asr" and is_trans_status:
            # 中文 ASR 模式不需要翻译引擎的状态
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
        self.asr_manager.set_output_mode(mode)
        self.save_config()

    def handle_theme_change(self, theme):
        for win in self.all_windows:
            if hasattr(win, 'apply_theme'): win.apply_theme(theme)
        self.save_config()

    def handle_scale_change(self, scale):
        for win in self.all_windows:
            if hasattr(win, 'apply_scaling'): win.apply_scaling(scale, win.font_size_factor, win.current_font_name == "思源宋体")
        self.save_config()

    def handle_font_change(self, font_name):
        for win in self.all_windows:
            if hasattr(win, 'current_font_name'):
                win.current_font_name = font_name
            if hasattr(win, 'apply_scaling'):
                # Safe access to attributes for scaling
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
        # 隐藏主窗口
        active_window = self.window
        active_window.hide()
        
        from settings_window import SettingsWindow
        self._settings_window = SettingsWindow(self.tr_engine)
        
        # 实时响应变更
        self._settings_window.settingsChanged.connect(self._apply_global_settings)
        
        # 连接引擎切换信号 - 关键：这会触发实际的引擎加载
        self._settings_window.engineChangeRequested.connect(self.sig_change_engine.emit)
        
        # 连接引擎加载状态信号
        self.tr_worker.status_changed.connect(self._on_engine_status_for_settings)
        
        self._settings_window.exec()
        
        # 断开信号连接，防止内存泄漏
        try:
            self.tr_worker.status_changed.disconnect(self._on_engine_status_for_settings)
        except:
            pass
        
        self._settings_window = None
        
        # 恢复显示
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
        # 更新快捷键
        current_asr = self.hotkey_mgr.asr_key_str
        current_toggle = self.hotkey_mgr.toggle_ui_str
        # 使用正则确保只替换独立的 'win' 或 'meta'，不破坏已有的 'windows'
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
            # 使用 QTimer 确保异步重启，避免卡顿
            QTimer.singleShot(100, self.hotkey_mgr.start)
        
        # 刷新所有窗口外观
        theme = self.m_cfg.theme_mode
        scale = self.m_cfg.window_scale
        font = self.m_cfg.font_name
        
        for win in self.all_windows:
            if hasattr(win, "change_theme"): win.change_theme(theme)
            if hasattr(win, "set_scale_factor"): win.set_scale_factor(scale)
            if hasattr(win, "set_font_name"): win.set_font_name(font)

        # 翻译引擎的切换现在由设置窗口直接处理
        # 不再在这里触发，避免重复加载/卸载
        self._last_engine_id = self.m_cfg.current_translator_engine

    def save_config(self):
        """DEPRECATED: Now handled directly by m_cfg. setters"""
        self.m_cfg.save_config()

    def on_tray_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        from PyQt6.QtGui import QCursor
        if reason == QSystemTrayIcon.ActivationReason.Trigger: # Left Click
            self.toggle_main_ui()
        elif reason == QSystemTrayIcon.ActivationReason.Context: # Right Click
            active_win = self.get_active_window()
            if active_win:
                # 在显示菜单前激活窗口，这是 Windows 下托盘菜单能由于失去焦点而关闭的关键
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

    def on_record_pressed(self):
        if self.audio_recorder.is_recording:
            self.audio_recorder.stop_recording()
        else:
            self.audio_recorder.start_recording()

    def on_wake_up(self):
        """响应单实例唤醒请求"""
        if self.window:
            self.window.show()
            self.window.activateWindow()
            self.window.raise_()

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # 强制切换工作目录到脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # === 强力清理旧进程 ===
    # 为了解决托盘重叠问题，启动时自动杀掉其他所有 main.py 进程
    try:
        current_pid = os.getpid()
        print(f"正在清理旧进程... (Current PID: {current_pid})")
        # PowerShell 命令：查找所有包含 main.py 的 python 进程，除了当前进程，全部强制结束
        ps_cmd = (
            f"Get-WmiObject Win32_Process | "
            f"Where-Object {{ $_.CommandLine -like '*main.py*' -and $_.ProcessId -ne {current_pid} }} | "
            f"Stop-Process -Force"
        )
        subprocess.run(["powershell", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        print(f"清理旧进程失败: {e}")
    # ====================

    from PyQt6.QtWidgets import QApplication, QDialog
    from PyQt6.QtCore import QLockFile, QDir
    import tempfile
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # 1. 单实例检查与唤醒 (使用 QLocalServer)
    from PyQt6.QtNetwork import QLocalSocket, QLocalServer
    
    server_name = "AI_JP_Input_Unique_Server"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    
    if socket.waitForConnected(500):
        # 连接成功，说明已有实例在运行
        print("发现已有实例，尝试唤醒...")
        # 发送唤醒指令
        socket.write(b"SHOW")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        sys.exit(0)
    
    # 2. 检查向导
    from model_config import get_model_config
    from model_downloader import get_downloader
    
    cfg = get_model_config()
    downloader = get_downloader()
    
    needs_setup = not cfg.data.get("wizard_completed", False) or \
                  not downloader.is_model_installed("sensevoice_onnx")
                  
    if needs_setup:
        from setup_wizard import SetupWizard
        # 向导前也要清理可能的残留 Server (防意外)
        QLocalServer.removeServer(server_name)
        
        wizard = SetupWizard()
        if wizard.exec() == QDialog.DialogCode.Accepted:
            cfg.wizard_completed = True
        else:
            sys.exit(0)
            
    # 3. 启动主程序
    # 在 AppController 初始化后再启动 Server 监听，方便绑定信号
    controller = AppController(app)
    
    # 启动单实例监听服务
    server = QLocalServer()
    # 必须先移除（如上次非正常退出残留）
    QLocalServer.removeServer(server_name) 
    if server.listen(server_name):
        # 当收到新连接时（即第二个实例试图启动）
        def handle_new_connection():
            client = server.nextPendingConnection()
            if client.waitForReadyRead(100):
                cmd = client.readAll().data()
                if cmd == b"SHOW":
                    # 唤醒操作：打开设置窗口或显示主UI
                    # 通过 controller 执行
                    controller.on_wake_up()
                    
        server.newConnection.connect(handle_new_connection)
    else:
        print(f"Server Listen Error: {server.errorString()}")

    sys.exit(app.exec())
