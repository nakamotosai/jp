import os, json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect, 
    QApplication, QLabel, QPushButton, QFrame, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QIcon, QFontMetrics, QPen, QBrush, QFont

from ui_manager import FontManager, LOGO_PATH
from model_config import ASROutputMode

# Default fallbacks if needed
DEFAULT_PLACEHOLDER = "按住大写键说话 → 日语"
DEFAULT_LISTENING = "正在聆听..."
DEFAULT_TRANSLATING = "翻译中..."

class ASRIconButton(QPushButton):
    def __init__(self, parent=None, icon_type="mic"):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_type = icon_type
        self._is_recording = False
        self._pulse_radius = 0
        self.bg_color = QColor(255, 255, 255, 25)
        self.icon_color = QColor(200, 200, 200)
        self.pulse_color = QColor(255, 60, 60, 100)
        
        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius")
        self.pulse_anim.setDuration(1200)
        self.pulse_anim.setLoopCount(-1)
        self.pulse_anim.setStartValue(0)
        self.pulse_anim.setEndValue(15)
        self.pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_recording(self, recording):
        self._is_recording = recording
        if recording:
            self.pulse_anim.start()
        else:
            self.pulse_anim.stop()
            self._pulse_radius = 0
        self.update()

    def get_pulse_radius(self): return self._pulse_radius
    def set_pulse_radius(self, r): 
        self._pulse_radius = r
        self.update()
    pulse_radius = pyqtProperty(float, fget=get_pulse_radius, fset=set_pulse_radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        
        if self._is_recording and self.icon_type == "mic":
            painter.setPen(Qt.PenStyle.NoPen)
            alpha = int(100 * (1.0 - self._pulse_radius / 15.0))
            c = QColor(self.pulse_color.red(), self.pulse_color.green(), self.pulse_color.blue(), alpha)
            painter.setBrush(QBrush(c))
            r = int(self._pulse_radius + 5)
            painter.drawEllipse(center, r, r)
            
        painter.setPen(Qt.PenStyle.NoPen)
        if self._is_recording and self.icon_type == "mic":
            painter.setBrush(QBrush(self.pulse_color))
        else:
            painter.setBrush(QBrush(self.bg_color))
        painter.drawEllipse(center, 10, 10)
        
        icon_c = QColor("white") if (self._is_recording and self.icon_type == "mic") else self.icon_color
        
        if self.icon_type == "clear":
            pen = QPen(icon_c, 2)
            painter.setPen(pen)
            painter.drawLine(center.x()-4, center.y()-4, center.x()+4, center.y()+4)
            painter.drawLine(center.x()+4, center.y()-4, center.x()-4, center.y()+4)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(icon_c))
            painter.drawRoundedRect(center.x()-3, center.y()-7, 6, 10, 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(icon_c.red(), icon_c.green(), icon_c.blue(), 200))
            painter.drawArc(center.x()-5, center.y()-3, 10, 8, 180*16, 180*16)
            painter.drawLine(center.x(), center.y()+5, center.x(), center.y()+7)
            painter.drawLine(center.x()-3, center.y()+7, center.x()+3, center.y()+7)


class ASRJpModeWindow(QWidget):
    """Japanese ASR Mode - recognizes Chinese, translates to Japanese, displays Japanese."""
    requestSend = pyqtSignal()
    requestRecordStart = pyqtSignal()
    requestRecordStop = pyqtSignal()
    
    # Unified Menu Signals
    requestAppModeChange = pyqtSignal(str)
    requestASREngineChange = pyqtSignal(str)
    requestTranslatorEngineChange = pyqtSignal(str)
    requestASROutputModeChange = pyqtSignal(str)
    requestThemeChange = pyqtSignal(str)
    requestScaleChange = pyqtSignal(float)
    requestFontChange = pyqtSignal(str)
    requestFontSizeChange = pyqtSignal(float)
    requestQuit = pyqtSignal()
    requestPersonalityChange = pyqtSignal(str)
    requestRestart = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main Layout with margins for shadow
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(25, 25, 25, 25)
        self.main_layout.setSpacing(0)

        # Container - the visible rounded rectangle
        self.container = QFrame()
        self.container.setObjectName("asr_jp_container")
        
        # Container layout - horizontal with text and buttons, vertically centered
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(15, 0, 10, 0)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.container.setGraphicsEffect(shadow)
        
        self.main_layout.addWidget(self.container)

        from model_config import get_model_config
        self.m_cfg = get_model_config()
        
        # Display label
        self.display = QLabel(self.m_cfg.get_prompt("idle_jp"))
        self.display.setWordWrap(True)
        self.display.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Buttons
        self.clear_btn = ASRIconButton(self, "clear")
        self.clear_btn.clicked.connect(self.clear_input)
        self.clear_btn.setVisible(False)
        
        self.voice_btn = ASRIconButton(self, "mic")
        self.voice_btn.pressed.connect(self.requestRecordStart.emit)
        self.voice_btn.released.connect(self.requestRecordStop.emit)

        # Add to layout
        self.container_layout.addWidget(self.display, 1)
        self.container_layout.addWidget(self.clear_btn)
        self.container_layout.addWidget(self.voice_btn)

        # State
        self.theme_mode = "Dark"
        self.window_scale = 1.0
        self.font_size_factor = 1.0
        self.current_font_serif = True
        self._placeholder_color = "rgba(255,255,255,0.5)"
        self._text_color = "white"
        
        # Animation
        self.height_anim = QPropertyAnimation(self, b"minimumHeight")
        self.height_anim.setDuration(200)
        self.height_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.base_height = 50
        self.expanded_height = 100
        self.is_expanded = False

        # Auto-clear timer (5 seconds)
        self.auto_clear_timer = QTimer(self)
        self.auto_clear_timer.setSingleShot(True)
        self.auto_clear_timer.setInterval(5000)
        self.auto_clear_timer.timeout.connect(self.clear_input)

        self.apply_theme()
        self._update_size()

    def apply_theme(self, theme="Dark"):
        self.theme_mode = theme
        if theme == "Light":
            bg = "rgba(245, 245, 245, 0.98)"
            self._text_color = "#333333"
            self._placeholder_color = "rgba(0,0,0,0.4)"
        else:
            bg = "rgba(45, 45, 45, 0.98)"
            self._text_color = "white"
            self._placeholder_color = "rgba(255,255,255,0.5)"
        
        self.container.setStyleSheet(f"""
            QFrame#asr_jp_container {{
                background-color: {bg};
                border-radius: 12px;
                border: none;
            }}
        """)
        
        btn_bg = QColor(0,0,0,40) if theme=="Light" else QColor(255,255,255,25)
        btn_icon = QColor(100,100,100) if theme=="Light" else QColor(200,200,200)
        self.clear_btn.bg_color = btn_bg
        self.clear_btn.icon_color = btn_icon
        self.clear_btn.update()
        self.voice_btn.bg_color = btn_bg
        self.voice_btn.icon_color = btn_icon
        self.voice_btn.update()
        
        self._update_display_style()

    def apply_scaling(self, scale, font_factor, serif=True):
        self.window_scale = scale
        self.font_size_factor = font_factor
        self.current_font_serif = serif
        self._update_display_style()
        self._update_size()

    def _update_display_style(self):
        family = FontManager.get_font(self.current_font_serif)
        font_size = int(14 * self.font_size_factor)
        
        current_text = self.display.text()
        loading_msgs = [self.m_cfg.get_prompt("loading"), self.m_cfg.get_prompt("init")]
        placeholders = [self.m_cfg.get_prompt("idle_jp"), self.m_cfg.get_prompt("listening"), self.m_cfg.get_prompt("translating")] + loading_msgs
        is_placeholder = current_text in placeholders or current_text == ""
        color = self._placeholder_color if is_placeholder else self._text_color
        
        self.display.setStyleSheet(f"""
            QLabel {{
                color: {color}; 
                background: transparent; 
                font-size: {font_size}px; 
                font-family: '{family}';
            }}
        """)

    def _needs_expansion(self, text):
        loading_msgs = [self.m_cfg.get_prompt("loading"), self.m_cfg.get_prompt("init")]
        if text in [self.m_cfg.get_prompt("idle_jp"), self.m_cfg.get_prompt("listening"), self.m_cfg.get_prompt("translating"), ""] + loading_msgs:
            return False
        
        font = self.display.font()
        fm = QFontMetrics(font)
        available_width = int(300 * self.window_scale) - 100
        text_width = fm.horizontalAdvance(text)
        return text_width > available_width or "\n" in text

    def _update_size(self):
        s = self.window_scale
        base_w = 220 * s
        content_w = self.container_layout.sizeHint().width() + 40
        w = max(base_w, content_w)
        self.setFixedWidth(w + 50)
        
        self.base_height = int(48 * s)
        self.expanded_height = int(100 * s)
        
        text = self.display.text()
        needs_expand = self._needs_expansion(text)
        
        if needs_expand != self.is_expanded:
            self.is_expanded = needs_expand
            target_container_h = self.expanded_height if needs_expand else self.base_height
            target_window_h = target_container_h + 50
            
            self.height_anim.stop()
            self.height_anim.setStartValue(self.height())
            self.height_anim.setEndValue(target_window_h)
            self.height_anim.start()
            
            self.container.setMinimumHeight(target_container_h)
            self.container.setMaximumHeight(target_container_h)
        else:
            target_container_h = self.expanded_height if self.is_expanded else self.base_height
            target_window_h = target_container_h + 50
            self.setMinimumHeight(target_window_h)
            self.setMaximumHeight(target_window_h)
            self.container.setMinimumHeight(target_container_h)
            self.container.setMaximumHeight(target_container_h)

    def update_segment(self, text):
        self.display.setText(text)
        self._update_display_style()
        is_real_text = text not in [self.m_cfg.get_prompt("idle_jp"), self.m_cfg.get_prompt("listening"), self.m_cfg.get_prompt("translating"), ""]
        self.clear_btn.setVisible(is_real_text)
        self._update_size()
        
        if is_real_text:
            self.auto_clear_timer.start()
        else:
            self.auto_clear_timer.stop()

    def show_translating(self):
        self.display.setText(self.m_cfg.get_prompt("translating"))
        self._update_display_style()

    def update_status(self, status):
        current = self.display.text()
        if "加载" in status or status == "loading":
            self.display.setText(self.m_cfg.get_prompt("loading"))
            self._update_display_style()
        elif status == "idle" or "加载完成" in status:
            if self.m_cfg.is_placeholder_text(current):
                self.update_segment(self.m_cfg.get_prompt("idle_jp"))
        elif status == "asr_loading":
            self.display.setText(self.m_cfg.get_prompt("init"))
            self._update_display_style()

    def clear_input(self):
        self.update_segment(self.m_cfg.get_prompt("idle_jp"))

    def focus_input(self):
        self.display.setFocus()

    def update_recording_status(self, is_recording):
        self.voice_btn.set_recording(is_recording)
        current = self.display.text()
        if is_recording:
            self.auto_clear_timer.stop()
            if current == self.m_cfg.get_prompt("idle_jp") or current == "":
                self.update_segment(self.m_cfg.get_prompt("listening"))
        else:
            if current == self.m_cfg.get_prompt("listening"):
                self.update_segment(self.m_cfg.get_prompt("idle_jp"))
            elif current not in [self.m_cfg.get_prompt("idle_jp"), ""]:
                self.auto_clear_timer.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: 
            self._dragging, self._drag_pos = True, e.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, e):
        if hasattr(self, '_dragging') and self._dragging: 
            self.move(e.globalPosition().toPoint() - self._drag_pos)
    def mouseReleaseEvent(self, e): self._dragging = False

    def contextMenuEvent(self, event):
        from model_config import get_model_config, ASREngineType, TranslatorEngineType, ASROutputMode
        config = get_model_config()
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(45, 45, 45, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                color: #eeeeee;
                padding: 6px 20px;
                margin: 2px;
                border-radius: 4px;
                background: transparent;
                text-align: left;
            }
            QMenu::item:selected {
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
            }
            QMenu::item:checked {
                color: #00ffcc;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 10px;
            }
            QMenu::right-arrow {
                image: none;
                width: 0px;
                padding-right: 0px;
            }
        """)
        
        mode_menu = menu.addMenu("应用模式")
        modes = [("asr", "语音输入模式"), ("asr_jp", "日语语音模式"), ("translation", "文字翻译模式")]
        for m_id, m_name in modes:
            action = mode_menu.addAction(m_name)
            action.triggered.connect(lambda checked, mid=m_id: self.requestAppModeChange.emit(mid))
            
        menu.addSeparator()

        asr_menu = menu.addMenu("ASR 引擎")
        for engine_id, info in self.m_cfg.ASR_MODELS.items():
            if not info.available: continue
            action = asr_menu.addAction(info.name)
            action.setCheckable(True)
            action.setChecked(self.m_cfg.current_asr_engine == engine_id)
            action.triggered.connect(lambda checked, eid=engine_id: self.requestASREngineChange.emit(eid))
            
        trans_menu = menu.addMenu("翻译引擎")
        for engine_id, info in self.m_cfg.TRANSLATOR_MODELS.items():
            action = trans_menu.addAction(info.name)
            action.setCheckable(True)
            action.setChecked(self.m_cfg.current_translator_engine == engine_id)
            action.triggered.connect(lambda checked, eid=engine_id: self.requestTranslatorEngineChange.emit(eid))
            
        clean_menu = menu.addMenu("文本处理")
        raw_action = clean_menu.addAction("原始结果")
        raw_action.setCheckable(True)
        raw_action.setChecked(self.m_cfg.asr_output_mode == ASROutputMode.RAW.value)
        raw_action.triggered.connect(lambda: self.requestASROutputModeChange.emit(ASROutputMode.RAW.value))
        
        clean_action = clean_menu.addAction("智能清理")
        clean_action.setCheckable(True)
        clean_action.setChecked(self.m_cfg.asr_output_mode == ASROutputMode.CLEANED.value)
        clean_action.triggered.connect(lambda: self.requestASROutputModeChange.emit(ASROutputMode.CLEANED.value))

        menu.addSeparator()
        
        theme_menu = menu.addMenu("界面设置")
        theme_sub = theme_menu.addMenu("配色主题")
        theme_sub.addAction("深色模式").triggered.connect(lambda: self.requestThemeChange.emit("Dark"))
        theme_sub.addAction("浅色模式").triggered.connect(lambda: self.requestThemeChange.emit("Light"))
        
        scale_sub = theme_menu.addMenu("窗口缩放")
        for s in [0.8, 1.0, 1.2, 1.5]:
            scale_sub.addAction(f"{int(s*100)}%").triggered.connect(lambda checked, val=s: self.requestScaleChange.emit(val))
            
        font_sub = theme_menu.addMenu("全局字体")
        font_sub.addAction("思源宋体").triggered.connect(lambda: self.requestFontChange.emit("思源宋体"))
        font_sub.addAction("思源黑体").triggered.connect(lambda: self.requestFontChange.emit("思源黑体"))
        
        font_size_sub = theme_menu.addMenu("文字大小")
        for s in [0.8, 1.0, 1.2, 1.5]:
            font_size_sub.addAction(f"{int(s*100)}%").triggered.connect(lambda checked, val=s: self.requestFontSizeChange.emit(val))

        personality_menu = menu.addMenu("AI 个性风格")
        for p_id, p_name in self.m_cfg.get_personality_schemes():
            action = personality_menu.addAction(p_name)
            action.setCheckable(True)
            action.setChecked(self.m_cfg.personality.data.get("current_scheme") == p_id)
            action.triggered.connect(lambda checked, pid=p_id: self.requestPersonalityChange.emit(pid))

        menu.addSeparator()
        
        menu.addAction("重启应用").triggered.connect(self.requestRestart.emit)
        menu.addAction("退出程序").triggered.connect(self.requestQuit.emit)
        
        menu.exec(event.globalPos())
