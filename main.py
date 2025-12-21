import sys, os, ctypes, json, multiprocessing
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

from model_config import get_model_config, ASROutputMode
from asr_manager import ASRManager
from asr_mode import ASRModeWindow
from asr_jp_mode import ASRJpModeWindow
from ui_manager import TranslatorWindow
from hotkey_manager import HotkeyManager
from tray_icon import AppTrayIcon
from audio_recorder import AudioRecorder
from translator_engine import TranslationWorker, TranslatorEngine
from system_handler import SystemHandler

class AppController(QObject):
    sig_do_translate = pyqtSignal(str)
    sig_change_engine = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.m_cfg = get_model_config()
        
        # 1. Models & Managers
        self.asr_manager = ASRManager()
        self.tr_engine = TranslatorEngine()
        self.audio_recorder = AudioRecorder()
        self.sys_handler = SystemHandler()
        
        # 2. Windows
        self.asr_window = ASRModeWindow()
        self.asr_jp_window = ASRJpModeWindow()
        self.tr_window = TranslatorWindow()
        self.all_windows = [self.asr_window, self.asr_jp_window, self.tr_window]
        
        self.app_mode = self.m_cfg.data.get("app_mode", "asr")
        self.window = self._get_active_window()
        
        self.tray = AppTrayIcon()
        self.tray.set_mode_checked(self.app_mode)
        
        # 3. Hotkey Manager
        self.hotkey_mgr = HotkeyManager(
            asr_key_str=self.m_cfg.hotkey_asr,
            toggle_ui_str=self.m_cfg.hotkey_toggle_ui
        )
        
        # 4. Async Worker
        self.tr_thread = QThread()
        self.tr_worker = TranslationWorker(self.tr_engine)
        self.tr_worker.moveToThread(self.tr_thread)
        self.sig_do_translate.connect(self.tr_worker.on_translate_requested)
        self.sig_change_engine.connect(self.tr_worker.on_engine_change_requested)
        self.tr_worker.result_ready.connect(self.on_translation_finished)
        self.tr_worker.status_changed.connect(self.on_worker_status_changed)
        self.tr_thread.start()
        
        # 初始触发翻译引擎加载
        QTimer.singleShot(0, lambda: self.sig_change_engine.emit(self.m_cfg.current_translator_engine))
        
        # 5. Connect UI Signals
        self.tray.signals.restartRequested.connect(self.restart_app)
        self.tray.signals.modeChanged.connect(self.handle_mode_change)
        self.tray.signals.quitRequested.connect(self.app.quit)
        
        for win in self.all_windows:
            win.requestSend.connect(self.handle_send_request)
            win.requestRecordStart.connect(self.on_record_pressed)
            win.requestRecordStop.connect(self.audio_recorder.stop_recording)
            
            if hasattr(win, "requestAppModeChange"): win.requestAppModeChange.connect(self.handle_mode_change)
            if hasattr(win, "requestASREngineChange"): win.requestASREngineChange.connect(self.handle_asr_engine_change)
            if hasattr(win, "requestTranslatorEngineChange"): win.requestTranslatorEngineChange.connect(self.handle_engine_change)
            if hasattr(win, "requestASROutputModeChange"): win.requestASROutputModeChange.connect(self.handle_asr_output_mode_change)
            if hasattr(win, "requestThemeChange"): win.requestThemeChange.connect(self.handle_theme_change)
            if hasattr(win, "requestScaleChange"): win.requestScaleChange.connect(self.handle_scale_change)
            if hasattr(win, "requestFontChange"): win.requestFontChange.connect(self.handle_font_change)
            if hasattr(win, "requestFontSizeChange"): win.requestFontSizeChange.connect(self.handle_font_size_change)
            if hasattr(win, "requestRestart"): win.requestRestart.connect(self.restart_app)
            if hasattr(win, "requestQuit"): win.requestQuit.connect(self.app.quit)
            if hasattr(win, "requestPersonalityChange"): win.requestPersonalityChange.connect(self.handle_personality_change)
            if hasattr(win, "requestHotkeyChange"): win.requestHotkeyChange.connect(self.handle_hotkey_change)

            
        if hasattr(self.tr_window, 'requestTranslation'):
            self.tr_window.requestTranslation.connect(self.handle_translation_request)
            
        self.sys_handler.set_my_window_handle(int(self.tr_window.winId()))
        self.sys_handler.start_focus_tracking()
        self.hotkey_mgr.start()
        
        # 6. Hotkey Watchdog - Check status every 30 seconds
        self.hotkey_watchdog = QTimer()
        self.hotkey_watchdog.timeout.connect(self.check_hotkey_status)
        self.hotkey_watchdog.start(30000)

        self.audio_recorder.started.connect(self.on_recording_state_changed)
        self.audio_recorder.stopped.connect(self.on_recording_state_changed)
        self.audio_recorder.audio_ready.connect(self.asr_manager.transcribe_async)
        self.audio_recorder.level_updated.connect(self.handle_audio_level)
        
        self.asr_manager.model_ready.connect(lambda: self.on_worker_status_changed("idle"))
        self.asr_manager.result_ready.connect(self.handle_asr_result)
        self.asr_manager.error.connect(lambda e: print(f"ASR Error: {e}"))
        
        self.hotkey_mgr.signals.asr_pressed.connect(self.on_asr_down)
        self.hotkey_mgr.signals.asr_released.connect(self.on_asr_up)
        self.hotkey_mgr.signals.toggle_ui.connect(self.toggle_main_ui)
        self.on_worker_status_changed("asr_loading")

        self._caps_was_on = False
        self.handle_mode_change(self.app_mode)

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
        self.save_config()

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
        if self.app_mode == "translation":
            self.tr_window.on_translation_ready(text)
        elif self.app_mode == "asr_jp":
            self.asr_jp_window.update_segment(text)
            self.handle_send_request(text)

    def handle_send_request(self, text):
        if not text: return
        self.sys_handler.paste_text(text)

    def handle_audio_level(self, level):
        if hasattr(self.window, "update_audio_level"):
            self.window.update_audio_level(level)

    def on_worker_status_changed(self, status):
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
            win.current_font_name = font_name
            if hasattr(win, 'apply_scaling'): win.apply_scaling(win.window_scale, win.font_size_factor, font_name == "思源宋体")
        self.save_config()

    def handle_font_size_change(self, factor):
        for win in self.all_windows:
            win.font_size_factor = factor
            if hasattr(win, 'apply_scaling'): win.apply_scaling(win.window_scale, factor, win.current_font_name == "思源宋体")
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

    def save_config(self):
        m_cfg = self.m_cfg
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            cfg = {
                "app_mode": self.app_mode,
                "window_scale": self.tr_window.window_scale,
                "font_size_factor": self.tr_window.font_size_factor,
                "theme_mode": self.tr_window.theme_mode,
                "font_name": self.tr_window.current_font_name,
                "asr_engine": m_cfg.current_asr_engine,
                "asr_output_mode": m_cfg.asr_output_mode,
                "translator_engine": m_cfg.current_translator_engine,
                "personality_scheme": m_cfg.personality.data.get("current_scheme"),
                "hotkey_asr": m_cfg.hotkey_asr,
                "hotkey_toggle_ui": m_cfg.hotkey_toggle_ui
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Save config error: {e}")

    def restart_app(self):
        os.execl(sys.executable, sys.executable, *sys.argv)

    def on_recording_state_changed(self):
        pass

    def on_record_pressed(self):
        if self.audio_recorder.is_recording:
            self.audio_recorder.stop_recording()
        else:
            self.audio_recorder.start_recording()

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # 强制切换工作目录到脚本所在目录，防止 pyw 运行路径偏移
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    controller = AppController()
    controller.run()
