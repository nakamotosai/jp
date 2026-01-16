"""
通用 UI 组件
供设置窗口和首次启动向导复用
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, QObject, pyqtSlot
from PyQt6.QtGui import QKeyEvent, QKeySequence, QFont, QPainter, QColor, QBrush, QPen

from model_downloader import get_downloader, DownloadStatus
from model_config import TranslatorEngineType, get_model_config
from font_manager import FontManager

class DownloadWorker(QObject):
    """
    独立下载工作线程
    替代之前的 threading.Thread + callback 模式，解决UI刷新卡死问题
    """
    progressChanged = pyqtSignal(int, int, str)    # downloaded, total, speed
    statusChanged = pyqtSignal(object, str)        # status_enum, msg (object to handle Enum)
    finished = pyqtSignal(bool)

    def __init__(self, model_id):
        super().__init__()
        self.model_id = model_id
        self.downloader = get_downloader()

    def run(self):
        # 定义回调函数桥接到信号
        def on_progress(downloaded, total, speed):
            self.progressChanged.emit(downloaded, total, speed)
        
        def on_status(status, msg):
            self.statusChanged.emit(status, msg)

        try:
            success = self.downloader.download_model(
                self.model_id, 
                progress_callback=on_progress, 
                status_callback=on_status
            )
            self.finished.emit(success)
        except Exception as e:
            self.statusChanged.emit(DownloadStatus.FAILED, str(e))
            self.finished.emit(False)


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
        
        # 线程相关
        self.thread = None
        self.worker = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.btn = QPushButton()
        self.btn.setCheckable(True)
        self.btn.setFixedHeight(70) # Increased height to accommodate progress bar
        self.btn.clicked.connect(self._on_btn_clicked)
        
        btn_layout = QVBoxLayout(self.btn)
        btn_layout.setContentsMargins(15, 8, 15, 8)
        btn_layout.setSpacing(2)
        
        top_row = QHBoxLayout()
        text_layout = QVBoxLayout()
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; background: transparent;")
        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setStyleSheet("font-size: 11px; color: #888888; background: transparent;")
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.desc_lbl)
        top_row.addLayout(text_layout, 1)
        
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 12px; color: white; background: transparent;")
        top_row.addWidget(self.status_lbl)
        btn_layout.addLayout(top_row)
        
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.hide()
        btn_layout.addWidget(self.progress)
        
        layout.addWidget(self.btn)
        self._update_style()
        self._check_status()

    def _on_btn_clicked(self):
        dl_key = self._get_dl_key()
        if not self.downloader.is_model_installed(dl_key):
            self.btn.setChecked(False) # 还没安装，不能选中
            self.start_download()
        else:
            self.selected.emit(self.model_id)

    def _get_dl_key(self):
        dl_key = self.model_id.lower()
        if "sensevoice" in dl_key: return "sensevoice_onnx"
        if "600m" in dl_key: return "nllb_600m"
        return dl_key

    def _check_status(self):
        dl_key = self._get_dl_key()
        if self.downloader.is_model_installed(dl_key):
            self.status_lbl.setText("已安装")
            self.status_lbl.setStyleSheet("font-size: 12px; color: #4ade80; background: transparent;")
            self.progress.hide()
        else:
            self.status_lbl.setText("待安装 (点击开始)")
            self.status_lbl.setStyleSheet("font-size: 12px; color: #f87171; background: transparent;")

    def start_download(self):
        dl_key = self._get_dl_key()
        self.btn.setEnabled(False)
        self.status_lbl.setText("准备下载...")
        self.progress.setValue(0)
        self.progress.show()
        
        # 创建线程
        self.thread = QThread()
        self.worker = DownloadWorker(dl_key)
        self.worker.moveToThread(self.thread)
        
        # 链接信号
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.worker.progressChanged.connect(self._on_dl_progress)
        self.worker.statusChanged.connect(self._on_dl_status)
        
        # 启动
        self.thread.start()
        
    def _on_dl_progress(self, downloaded, total, speed):
        if total > 0:
            percent = int((downloaded / total) * 100)
            self.progress.setValue(percent)
            self.status_lbl.setText(f"{percent}% {speed}")
            
    def _on_dl_status(self, status, msg):
        if status == DownloadStatus.COMPLETED:
            self.progress.hide()
            self.btn.setEnabled(True)
            self._check_status()
            self.selected.emit(self.model_id)
            self.btn.setChecked(True)
        elif status == DownloadStatus.FAILED:
            self.status_lbl.setText("下载失败")
            self.btn.setEnabled(True)
            self.progress.hide()
        elif status == DownloadStatus.EXTRACTING:
            self.status_lbl.setText("正在解压...")
        else:
            if "%" not in msg:
                self.status_lbl.setText(msg)

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
        elif "加载中" in status_text or "Loading" in status_text or "切换" in status_text:
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
        elif "切换" in status_text:
            self.status_val.setText(status_text)
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
        self.pending_engine_id = None  # 记录正在切换中的引擎，防止 UI 跳变
        self._setup_ui()
        
        # 线程
        self.thread = None
        self.worker = None
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # [MODIFIED] 注释掉显示面板区域
        # self.monitor = TranslatorMonitorWidget()
        # layout.addWidget(self.monitor)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_google = QPushButton("Google 在线翻译")
        self.btn_google.setCheckable(True)
        self.btn_google.clicked.connect(lambda: self._on_engine_clicked("online"))
        
        self.btn_nllb = QPushButton("本地 AI 翻译引擎 (已暂停)")
        self.btn_nllb.setCheckable(True)
        self.btn_nllb.setEnabled(False) # [MODIFIED] Disable button
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
        # [MODIFIED] 注释掉对 monitor 的引用
        # self.monitor.update_theme(is_light)
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
        """同步 UI 状态显示，确保标题显示正确的目标引擎"""
        target_id = self.m_cfg.current_translator_engine
        backend_id = self.tr_engine.current_engine_id
        
        # 检查后端引擎是否已经切换到了目标引擎且已就绪
        is_ready = (backend_id == target_id) and (self.tr_engine.local_is_ready if target_id != "online" else True)
        
        # 只有当后端已经匹配目标时，才拉取后端的就绪状态显示
        # 否则（正在切换中）维持 Monitor 现状，避免被后端旧状态的 ID 覆盖
        if is_ready:
            self.pending_engine_id = None
            # self.monitor.set_status(target_id, "就绪", True)
        elif not self.pending_engine_id:
            # 仅在非点击切换的静态状态下（如刚打开设置面板）同步基础信息
            status_desc = "正在初始化..." if target_id != "online" else "运行中"
            # self.monitor.set_status(target_id, status_desc, is_ready)

        # 始终同步按钮高亮，以意图为主
        is_online = (target_id == "online")
        self.btn_google.setChecked(is_online)
        self.btn_nllb.setChecked(not is_online)
        
        if not self.downloader.is_model_installed("nllb_600m"):
            # self.monitor.info_lbl.setText("提示: NLLB 600M 本地模型暂未下载")
            pass
        else:
            # 如果已安装，确保清除旧的“未下载”提示
            # if "暂未下载" in self.monitor.info_lbl.text():
            #     self.monitor.info_lbl.setText("")
            pass

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
        # [MODIFIED] Guard against disabled NLLB
        if engine_id == TranslatorEngineType.NLLB_600M_CT2.value:
            return

        # Old logic commented out
        # if engine_id == TranslatorEngineType.NLLB_600M_CT2.value:
        #     if not self.downloader.is_model_installed("nllb_600m"):
        #         self._start_download("nllb_600m")
        #         return
        
        # [MODIFIED] 注释掉对 monitor 的引用
        # self.monitor.set_status(engine_id, "正在切换模式，请稍等...", False)
        self.pending_engine_id = engine_id
        self.m_cfg.current_translator_engine = engine_id
        self.m_cfg.save_config()
        self.engineChangeRequested.emit(engine_id)
        # 移除此处的 sync_status()，因为它会根据尚未改变的真个引擎状态把 UI 改回去
        self._update_button_styles() # 仅更新按钮样式

    def _start_download(self, dl_key: str):
        self.btn_nllb.setEnabled(False)
        # self.monitor.set_status(TranslatorEngineType.NLLB_600M_CT2.value, "准备下载...", False)
        self.progress.show()
        
        # 停止旧线程如果存在
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
            
        self.thread = QThread()
        self.worker = DownloadWorker(dl_key)
        self.worker.moveToThread(self.thread)
        
        # 连接信号
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.worker.progressChanged.connect(self._on_dl_progress)
        self.worker.statusChanged.connect(self._on_dl_status)
        
        self.thread.start()
            
    def _on_dl_progress(self, downloaded, total, speed):
        if total > 0:
            percent = int((downloaded / total) * 100)
            self.progress.setValue(percent)
            # self.monitor.set_status(
            #     TranslatorEngineType.NLLB_600M_CT2.value, 
            #     f"正在下载: {percent}% ({speed})", 
            #     False
            # )
            
    def _on_dl_status(self, status, msg):
        if status == DownloadStatus.COMPLETED:
            self.progress.hide()
            self.btn_nllb.setEnabled(True)
            # self.monitor.info_lbl.setText("安装成功！正在切换引擎...")
            self._on_engine_clicked(TranslatorEngineType.NLLB_600M_CT2.value)
        elif status == DownloadStatus.FAILED:
            # self.monitor.set_status(TranslatorEngineType.NLLB_600M_CT2.value, f"失败: {msg}", False)
            self.btn_nllb.setEnabled(True)
            self.progress.hide()
        else:
            if "%" not in msg:
                 # self.monitor.set_status(TranslatorEngineType.NLLB_600M_CT2.value, msg, False)
                 pass

    def update_engine_status(self, status: str):
        """引擎加载完成或状态改变的回调"""
        current_id = self.m_cfg.current_translator_engine
        is_ready = any(x in status for x in ["完成", "就绪", "成功", "ready", "idle"])
        
        if is_ready:
            self.pending_engine_id = None # 清除挂起状态
            
        # self.monitor.set_status(current_id, status, is_ready)
        # 刷新按钮状态和高亮
        self.sync_status()


class TeachingTip(QFrame):
    """新手教学气泡提示"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # Fix for black corners
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        # 提示内容
        self.label = QLabel(
            "<b>快捷指令</b><br><br>"
            "• <b>Win + Ctrl</b><br>"
            "&nbsp;&nbsp;&nbsp;按住说话<br><br>"
            "• <b>Win + Alt</b><br>"
            "&nbsp;&nbsp;&nbsp;显隐窗口<br><br>"
            "• <b>界面右键</b><br>"
            "&nbsp;&nbsp;&nbsp;唤出菜单"
        )
        self.label.setWordWrap(True)
        self.label.setFixedWidth(200) 
        self.label.setStyleSheet("color: #e0e0e0; font-size: 13px; line-height: 1.4;")
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) # [Fix] Allow dragging from text area
        layout.addWidget(self.label)
        
        # 关闭按钮
        close_btn = QPushButton("OK")
        close_btn.setFixedWidth(60)
        close_btn.setFixedHeight(24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("""
            TeachingTip {
                background: transparent; 
                border: none;
            }
            QLabel {
                padding: 5px;
                background: transparent;
            }
            QPushButton {
                background-color: #333333; 
                color: #cccccc;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
                color: white;
            }
        """)

    def paintEvent(self, event):
        """手动绘制以支持圆角透明背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 填充背景
        painter.setBrush(QBrush(QColor("#1f1f1f")))
        painter.setPen(QPen(QColor("#3d3d3d"), 1)) # 边框
        
        # [Fix] 使用 QRectF 避免整数坐标导致的截断问题
        from PyQt6.QtCore import QRectF
        rect = QRectF(self.rect())
        rect.adjust(0.5, 0.5, -0.5, -0.5) # 半像素微调，保证边框清晰且不被切
        painter.drawRoundedRect(rect, 12, 12)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def show_beside(self, widget):
        """在指定组件右侧显示"""
        if not widget: return
        # 获取目标窗口的全局几何信息
        target_geo = widget.frameGeometry()
        
        # 计算显示位置
        # 由于我们加上了 20px 的透明边距用于显示阴影，这里需要做一些偏移补偿
        # 目标：内容的左侧边缘 距离 目标窗口右侧 10px
        # 窗口左上角 x = 目标右边 + 10px - 左边距(20px)
        
        spacing = 10
        margin_left = 20 # 对应 ContentsMargins
        margin_top = 20
        
        x = target_geo.x() + target_geo.width() + spacing - margin_left
        y = target_geo.y() - margin_top # 顶部对齐（考虑到阴影上边距）
        
        self.move(x, y)
        self.show()
