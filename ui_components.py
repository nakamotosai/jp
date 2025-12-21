"""
通用 UI 组件
供设置窗口和首次启动向导复用
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QKeyEvent, QKeySequence, QFont

from model_downloader import get_downloader, DownloadStatus
from model_config import TranslatorEngineType, get_model_config
from ui_manager import FontManager

class HotkeyButton(QPushButton):
    """自定义快捷键按钮"""
    hotkeyChanged = pyqtSignal(str)
    
    def __init__(self, key_fullname, parent=None):
        super().__init__(parent)
        self.key_fullname = key_fullname
        self.is_recording = False
        self.setText(self._format_key(key_fullname))
        self.setCheckable(True)
        self.clicked.connect(self._start_recording)
        self._update_style()
        
    def _format_key(self, key_str):
        if not key_str: return "None"
        return key_str.replace("meta", "Win").replace("ctrl", "Ctrl").replace("alt", "Alt").replace("shift", "Shift").upper()
        
    def _start_recording(self):
        self.is_recording = True
        self.setText("请按键...")
        self.setChecked(True)
        self._update_style()
        self.setFocus()
        
    def _end_recording(self):
        self.is_recording = False
        self.setChecked(False)
        self._update_style()
        self.clearFocus()
        
    def _update_style(self):
        is_light = getattr(self, "is_light", False)
        
        if self.is_recording:
            bg = "#6366f1" # Indigo
            fg = "white"
            bd = "#6366f1"
            weight = "bold"
        else:
            if is_light:
                bg = "#ffffff"
                fg = "#4b5563"
                bd = "#e5e7eb"
                hover_bg = "#f9fafb"
                hover_bd = "#d1d5db"
            else:
                bg = "#252526"
                fg = "#cccccc"
                bd = "#3d3d3d"
                hover_bg = "#3d3d3d"
                hover_bd = "#555555"
            weight = "normal"

        style = f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {bd};
                padding: 6px 15px;
                border-radius: 6px;
                font-size: 13px;
                font-family: '{FontManager.get_correct_family(get_model_config().font_name)}', Consolas, 'Courier New', monospace;
                font-weight: {weight};
            }}
        """
        if not self.is_recording:
            style += f"""
                QPushButton:hover {{
                    background-color: {hover_bg};
                    border-color: {hover_bd};
                }}
            """
        self.setStyleSheet(style)

    def update_theme(self, is_light):
        self.is_light = is_light
        self._update_style()

    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_recording:
            super().keyPressEvent(event)
            return
            
        key = event.key()
        modifiers = event.modifiers()
        
        is_modifier_key = key in [Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta]
        
        has_ctrl = (modifiers & Qt.KeyboardModifier.ControlModifier) or key == Qt.Key.Key_Control
        has_alt = (modifiers & Qt.KeyboardModifier.AltModifier) or key == Qt.Key.Key_Alt
        has_shift = (modifiers & Qt.KeyboardModifier.ShiftModifier) or key == Qt.Key.Key_Shift
        has_win = (modifiers & Qt.KeyboardModifier.MetaModifier) or key == Qt.Key.Key_Meta
        
        mod_count = sum([has_ctrl, has_alt, has_shift, has_win])
        
        if is_modifier_key and mod_count <= 1:
            return
        
        if key == Qt.Key.Key_Escape:
            self.setText(self._format_key(self.key_fullname))
            self._end_recording()
            return
            
        parts = []
        if has_ctrl: parts.append("ctrl")
        if has_alt: parts.append("alt")
        if has_shift: parts.append("shift")
        if has_win: parts.append("windows")
        
        if not is_modifier_key:
            if key >= Qt.Key.Key_F1 and key <= Qt.Key.Key_F35:
                key_text = f"f{key - Qt.Key.Key_F1 + 1}"
            elif key == Qt.Key.Key_Space:
                key_text = "space"
            else:
                key_text = QKeySequence(key).toString().lower()
                
            if key_text:
                parts.append(key_text)

        new_key = "+".join(parts)
        
        self.key_fullname = new_key
        self.setText(self._format_key(new_key))
        self.hotkeyChanged.emit(new_key)
        self._end_recording()
        
    def focusOutEvent(self, event):
        if self.is_recording:
            self.setText(self._format_key(self.key_fullname))
            self._end_recording()
        super().focusOutEvent(event)


class ModelOptionWidget(QWidget):
    """通用单选模型选项组件 (用于 ASR 或简单模型选择)"""
    selected = pyqtSignal(str)
    
    def __init__(self, model_id, title, desc, parent=None):
        super().__init__(parent)
        self.model_id = model_id
        self.downloader = get_downloader()
        self.is_light = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        self.btn = QPushButton()
        self.btn.setCheckable(True)
        self.btn.setFixedHeight(60)
        self.btn.clicked.connect(lambda: self.selected.emit(self.model_id))
        
        btn_layout = QHBoxLayout(self.btn)
        btn_layout.setContentsMargins(15, 10, 15, 10)
        
        text_layout = QVBoxLayout()
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; background: transparent;")
        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setStyleSheet("font-size: 11px; color: #888888; background: transparent;")
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.desc_lbl)
        btn_layout.addLayout(text_layout, 1)
        
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 12px; color: white; background: transparent;")
        btn_layout.addWidget(self.status_lbl)
        
        layout.addWidget(self.btn)
        self._update_style()
        self._check_status()

    def _check_status(self):
        dl_key = self.model_id.lower()
        if "sensevoice" in dl_key: dl_key = "sensevoice_onnx"
        elif "600m" in dl_key: dl_key = "nllb_600m"
        
        if self.downloader.is_model_installed(dl_key):
            self.status_lbl.setText("已安装")
            self.status_lbl.setStyleSheet("font-size: 12px; color: white; background: transparent;")
        else:
            self.status_lbl.setText("待安装")
            self.status_lbl.setStyleSheet("font-size: 12px; color: #888888; background: transparent;")

    def _update_style(self):
        if self.is_light:
            bg = "#ffffff"
            fg = "#1f2937"
            bd = "#e5e7eb"
            hover_bg = "#f9fafb"
            hover_bd = "#0078d4"
            checked_bg = "#0078d4"
            checked_fg = "white"
            checked_bd = "#0078d4"
            title_color = "#111827"
            desc_color = "#6b7280"
        else:
            bg = "#252526"
            fg = "#cccccc"
            bd = "#3d3d3d"
            hover_bg = "#3d3d3d"
            hover_bd = "#555555"
            checked_bg = "#0e639c"
            checked_fg = "white"
            checked_bd = "#0e639c"
            title_color = "white"
            desc_color = "#888888"

        font_name = FontManager.get_correct_family(get_model_config().font_name)
        self.btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {bd};
                border-radius: 8px;
                text-align: left;
                font-family: '{font_name}', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: {hover_bd};
            }}
            QPushButton:checked {{
                background-color: {checked_bg};
                color: {checked_fg};
                border: 1px solid {checked_bd};
            }}
        """)
        font_name = FontManager.get_correct_family(get_model_config().font_name)
        self.title_lbl.setStyleSheet(f"font-family: '{font_name}'; font-weight: bold; font-size: 13px; color: {title_color if not self.btn.isChecked() else 'white'}; background: transparent;")
        self.desc_lbl.setStyleSheet(f"font-family: '{font_name}'; font-size: 11px; color: {desc_color if not self.btn.isChecked() else '#e0e7ff'}; background: transparent;")

    def setChecked(self, checked):
        self.btn.setChecked(checked)
        self._update_style()
        
    def update_theme(self, is_light):
        self.is_light = is_light
        self._update_style()
        self._check_status()

class TranslatorMonitorWidget(QFrame):
    """翻译引擎状态显示器 - 仿 OLED 屏幕风格"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Monitor")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.is_light = False
        self.setFixedHeight(110)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(8)
        
        # 引擎标题行
        engine_layout = QHBoxLayout()
        self.engine_label = QLabel("当前活动引擎:")
        self.engine_name = QLabel("未探测")
        self.engine_name.setWordWrap(True)
        engine_layout.addWidget(self.engine_label)
        engine_layout.addWidget(self.engine_name, 1)
        layout.addLayout(engine_layout)
        
        # 状态行
        status_layout = QHBoxLayout()
        self.status_label = QLabel("运行状态:")
        self.status_val = QLabel("离线")
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.status_val)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        self.info_lbl = QLabel("")
        layout.addWidget(self.info_lbl)
        
        self._update_style()

    def _update_style(self):
        if self.is_light:
            bg = "#f9fafb"
            bd = "#e5e7eb"
            label_color = "#6b7280"
            name_color = "#0078d4" # Blue
            info_color = "#9ca3af"
        else:
            bg = "#0c0c0c"
            bd = "#1a1a1a"
            label_color = "#666666"
            name_color = "#3b82f6" # Blue
            info_color = "#888888"

        self.setStyleSheet(f"""
            #Monitor {{
                background-color: {bg};
                border: 2px solid {bd};
                border-radius: 12px;
            }}
        """)
        
        font_name = FontManager.get_correct_family(get_model_config().font_name)
        self.engine_label.setStyleSheet(f"color: {label_color}; font-size: 11px; font-weight: bold; font-family: '{font_name}'; background: transparent;")
        self.engine_name.setStyleSheet(f"color: {name_color}; font-size: 14px; font-weight: bold; font-family: '{font_name}', 'Segoe UI', system-ui, sans-serif; background: transparent;")
        self.status_label.setStyleSheet(f"color: {label_color}; font-size: 11px; font-weight: bold; font-family: '{font_name}'; background: transparent;")
        self.info_lbl.setStyleSheet(f"color: {info_color}; font-size: 10px; font-family: '{font_name}'; background: transparent;")
        
        # Status value color depends on the status itself, handled in set_status
        self.update_status_style()

    def update_status_style(self):
        status_text = self.status_val.text()
        if self.is_light:
            ready_color = "#059669" # Green 600
            loading_color = "#d97706" # Amber 600
            error_color = "#dc2626" # Red 600
        else:
            ready_color = "#3b82f6" # Blue
            loading_color = "#f0b000"
            error_color = "#d16969"

        color = error_color
        if "运行中" in status_text or "Ready" in status_text:
            color = ready_color
        elif "加载中" in status_text or "Loading" in status_text:
            color = loading_color
            
        font_name = FontManager.get_correct_family(get_model_config().font_name)
        self.status_val.setStyleSheet(f"color: {color}; font-size: 13px; font-family: '{font_name}', 'Consolas', monospace; font-weight: bold; background: transparent;")

    def update_theme(self, is_light):
        self.is_light = is_light
        self._update_style()

    def set_status(self, engine_id: str, status_text: str, is_ready: bool):
        name_map = {
            "online": "Google 在线翻译",
            TranslatorEngineType.NLLB_600M_CT2.value: "NLLB 600M (智能本地引擎)",
            None: "未加载"
        }
        name = name_map.get(engine_id, "未知引擎")
        self.engine_name.setText(name)
        
        if "完成" in status_text or "就绪" in status_text or "成功" in status_text or status_text == "idle":
            self.status_val.setText("运行中 (Ready)")
        elif "加载" in status_text or "loading" in status_text:
            self.status_val.setText("加载中 (Loading...)")
        else:
            self.status_val.setText(status_text)
        
        self.update_status_style()

class TranslatorSelectorWidget(QWidget):
    """翻译引擎选择控制面板"""
    engineChangeRequested = pyqtSignal(str)
    
    def __init__(self, tr_engine, parent=None):
        super().__init__(parent)
        self.tr_engine = tr_engine
        self.downloader = get_downloader()
        self.m_cfg = get_model_config()
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        self.monitor = TranslatorMonitorWidget()
        layout.addWidget(self.monitor)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_google = QPushButton("Google 在线翻译")
        self.btn_google.setCheckable(True)
        self.btn_google.clicked.connect(lambda: self._on_engine_clicked("online"))
        
        self.btn_nllb = QPushButton("本地 AI 翻译引擎")
        self.btn_nllb.setCheckable(True)
        self.btn_nllb.clicked.connect(lambda: self._on_engine_clicked(TranslatorEngineType.NLLB_600M_CT2.value))
        
        for btn in [self.btn_google, self.btn_nllb]:
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_layout.addWidget(btn, 1)
        
        layout.addLayout(btn_layout)
        
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        
        self.sync_status()

    def update_theme(self, is_light):
        self.is_light = is_light
        self.monitor.update_theme(is_light)
        self._update_button_styles()
        
        if is_light:
            prog_style = f"""
                QProgressBar {{ border: none; background: #e5e7eb; border-radius: 2px; }}
                QProgressBar::chunk {{ background-color: #0078d4; border-radius: 2px; }}
            """
        else:
            prog_style = """
                QProgressBar { border: none; background: #2d2d2d; border-radius: 2px; }
                QProgressBar::chunk { background-color: #0e639c; border-radius: 2px; }
            """
        self.progress.setStyleSheet(prog_style)

    def sync_status(self):
        current_id = self.tr_engine.current_engine_id
        is_ready = self.tr_engine.local_is_ready if current_id != "online" else True
        self.monitor.set_status(current_id, "就绪" if is_ready else "正在初始化", is_ready)
        
        config_id = self.m_cfg.current_translator_engine
        self.btn_google.setChecked(config_id == "online")
        self.btn_nllb.setChecked(config_id != "online")
        
        if not self.downloader.is_model_installed("nllb_600m"):
            self.monitor.info_lbl.setText("提示: NLLB 600M 本地模型暂未下载")

        self._update_button_styles()

    def _update_button_styles(self):
        is_light = getattr(self, "is_light", False)
        accent_color = "#0078d4" if is_light else "#0e639c"
        if is_light:
            bg = "#ffffff"
            fg = "#4b5563"
            bd = "#e5e7eb"
            hover_bg = "#f9fafb"
            hover_bd = accent_color
            checked_bg = accent_color
            checked_fg = "white"
            checked_bd = accent_color
        else:
            bg = "#252526"
            fg = "#cccccc"
            bd = "#3d3d3d"
            hover_bg = "#3d3d3d"
            hover_bd = "#555555"
            checked_bg = accent_color
            checked_fg = "white"
            checked_bd = accent_color

        font_name = FontManager.get_correct_family(get_model_config().font_name)
        style = f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {bd};
                border-radius: 8px;
                font-size: 13px;
                padding: 4px;
                font-family: '{font_name}', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{ 
                background-color: {hover_bg}; 
                border-color: {hover_bd}; 
            }}
            QPushButton:checked {{ 
                background-color: {checked_bg}; 
                color: {checked_fg}; 
                border: 1px solid {checked_bd}; 
                font-weight: bold; 
            }}
        """
        self.btn_google.setStyleSheet(style)
        self.btn_nllb.setStyleSheet(style)

    def _on_engine_clicked(self, engine_id: str):
        if engine_id == TranslatorEngineType.NLLB_600M_CT2.value:
            if not self.downloader.is_model_installed("nllb_600m"):
                self._start_download("nllb_600m")
                return
        
        self.monitor.set_status(engine_id, "正在加载...", False)
        self.m_cfg.current_translator_engine = engine_id
        self.m_cfg.save_config()
        self.engineChangeRequested.emit(engine_id)
        self.sync_status()

    def _start_download(self, dl_key: str):
        self.btn_nllb.setEnabled(False)
        self.monitor.set_status(TranslatorEngineType.NLLB_600M_CT2.value, "准备下载...", False)
        self.progress.show()
        
        def on_progress(downloaded, total, speed):
            if total > 0:
                percent = int((downloaded / total) * 100)
                QTimer.singleShot(0, lambda: self.progress.setValue(percent))

        def on_status(status, msg):
            def update_ui():
                if status == DownloadStatus.COMPLETED:
                    self.progress.hide()
                    self.btn_nllb.setEnabled(True)
                    self._on_engine_clicked(TranslatorEngineType.NLLB_600M_CT2.value)
                elif status == DownloadStatus.FAILED:
                    self.monitor.set_status(None, f"下载失败: {msg}", False)
                    self.btn_nllb.setEnabled(True)
                    self.progress.hide()
            QTimer.singleShot(0, update_ui)

        import threading
        threading.Thread(target=self.downloader.download_model, args=(dl_key, on_progress, on_status), daemon=True).start()

    def update_engine_status(self, status: str):
        current_id = self.m_cfg.current_translator_engine
        self.monitor.set_status(current_id, status, "就绪" in status or "完成" in status)
