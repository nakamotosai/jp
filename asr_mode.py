import os, json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect, 
    QApplication, QLabel, QPushButton, QFrame, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QIcon, QFontMetrics, QPen, QBrush, QFont

from ui_manager import FontManager, LOGO_PATH, HotkeyDialog, VoiceWaveform
from model_config import get_model_config, ASREngineType, TranslatorEngineType, ASROutputMode
from startup_manager import StartupManager

# Default fallbacks if needed
DEFAULT_PLACEHOLDER = "按住大写键说话"
DEFAULT_LISTENING = "正在聆听..."

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


class ASRModeWindow(QWidget):
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
    requestAutoTTSChange = pyqtSignal(bool)
    requestTTSDelayChange = pyqtSignal(int)
    requestPersonalityChange = pyqtSignal(str)
    requestHotkeyChange = pyqtSignal(str, str)
    requestRestart = pyqtSignal()
    requestOpenSettings = pyqtSignal()

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
        self.container.setObjectName("asr_container")
        
        # Container layout - horizontal with text and buttons, vertically centered
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(15, 0, 10, 0)  # No vertical padding
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)  # Vertically center all items
        
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
        self.display = QLabel(self.m_cfg.get_prompt("idle_zh"))
        self.display.setWordWrap(True)
        self.display.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Waveform
        self.waveform = VoiceWaveform(self)
        self.waveform.setVisible(False)
        
        # Buttons
        self.clear_btn = ASRIconButton(self, "clear")
        self.clear_btn.clicked.connect(self.clear_input)
        self.clear_btn.setVisible(False)
        
        self.voice_btn = ASRIconButton(self, "mic")
        self.voice_btn.pressed.connect(self.requestRecordStart.emit)
        self.voice_btn.released.connect(self.requestRecordStop.emit)
        
        # Add to layout
        self.container_layout.addWidget(self.display, 1)
        self.container_layout.addWidget(self.waveform, 1)
        self.container_layout.addWidget(self.clear_btn)
        self.container_layout.addWidget(self.voice_btn)

        # State
        self.theme_mode = "Dark"
        self.window_scale = 1.0
        self.font_size_factor = 1.0
        self.current_font_name = "思源宋体"
        self._placeholder_color = "rgba(255,255,255,0.5)"
        self._text_color = "white"
        
        # Animation for smooth height changes
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
            QFrame#asr_container {{
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
        
        self.waveform.bar_color = QColor(100, 100, 100) if theme == "Light" else QColor(200, 200, 200)
        
        self._update_display_style()

    def apply_scaling(self, scale, font_factor):
        self.window_scale = scale
        self.font_size_factor = font_factor
        # removed overriding current_font_name logic
        self._update_display_style()
        self._update_size()

    # Compatibility methods
    def change_theme(self, theme): self.apply_theme(theme)
    def set_font_name(self, name): 
        self.current_font_name = name
        self._update_display_style()
    def set_scale_factor(self, scale):
        self.apply_scaling(scale, self.font_size_factor)

    def _update_display_style(self):
        family = FontManager.get_correct_family(self.current_font_name)
        font_size = int(14 * self.font_size_factor)
        
        current_text = self.display.text()
        loading_msgs = [self.m_cfg.get_prompt("loading"), self.m_cfg.get_prompt("init")]
        placeholders = [self.m_cfg.get_prompt("idle_zh"), self.m_cfg.get_prompt("listening")] + loading_msgs
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
        if text in [self.m_cfg.get_prompt("idle_zh"), self.m_cfg.get_prompt("listening"), ""] + loading_msgs:
            return False
        font = self.display.font()
        fm = QFontMetrics(font)
        available_width = int(300 * self.window_scale) - 100
        text_width = fm.horizontalAdvance(text)
        return text_width > available_width or "\n" in text

    def _update_size(self):
        s = self.window_scale
        # 固定宽度，不再随内容抖动
        fixed_w = int(320 * s)
        self.setFixedWidth(fixed_w + 50)
        
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
        is_real_text = text not in [self.m_cfg.get_prompt("idle_zh"), self.m_cfg.get_prompt("listening"), ""]
        self.clear_btn.setVisible(is_real_text)
        self._update_size()
        
        if is_real_text:
            self.auto_clear_timer.start()
        else:
            self.auto_clear_timer.stop()

    def update_status(self, status):
        current = self.display.text()
        if status == "idle" or "加载完成" in status or "就绪" in status:
            if self.m_cfg.is_placeholder_text(current):
                self.update_segment(self.m_cfg.get_prompt("idle_zh"))
        elif "加载" in status or status == "loading":
            self.display.setText(self.m_cfg.get_prompt("loading"))
            self._update_display_style()
        elif status == "asr_loading":
            self.display.setText(self.m_cfg.get_prompt("init"))
            self._update_display_style()

    def clear_input(self):
        self.update_segment(self.m_cfg.get_prompt("idle_zh"))

    def focus_input(self):
        self.display.setFocus()

    def update_recording_status(self, is_recording):
        self.voice_btn.set_recording(is_recording)
        self.waveform.setVisible(is_recording)
        self.display.setVisible(not is_recording)
        
        current = self.display.text()
        if is_recording:
            self.auto_clear_timer.stop()
            if current == self.m_cfg.get_prompt("idle_zh") or current == "":
                self.update_segment(self.m_cfg.get_prompt("listening"))
        else:
            if current == self.m_cfg.get_prompt("listening"):
                self.update_segment(self.m_cfg.get_prompt("idle_zh"))
            elif current not in [self.m_cfg.get_prompt("idle_zh"), ""]:
                self.auto_clear_timer.start()

    def update_audio_level(self, level):
        if self.waveform.isVisible():
            self.waveform.set_level(level)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: 
            self._dragging, self._drag_pos = True, e.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, e):
        if hasattr(self, '_dragging') and self._dragging: 
            self.move(e.globalPosition().toPoint() - self._drag_pos)
    def mouseReleaseEvent(self, e): self._dragging = False

    def contextMenuEvent(self, event):
        self.show_context_menu(event.globalPos())

    def show_context_menu(self, global_pos):
        menu = QMenu() # 不带 parent 以确保即便窗口隐藏时也能正常显示菜单
        # 1. 应用模式
        mode_menu = menu.addMenu("应用模式")
        modes = [("asr", "语音输入模式"), ("asr_jp", "日语语音模式"), ("translation", "文字翻译模式")]
        current_mode = self.m_cfg.app_mode
        for m_id, m_name in modes:
            display_name = f"{m_name}{'        ✔' if m_id == current_mode else ''}"
            action = mode_menu.addAction(display_name)
            action.triggered.connect(lambda checked, mid=m_id: self.requestAppModeChange.emit(mid))
        
        menu.addSeparator()
        menu.addAction("详细设置").triggered.connect(self.requestOpenSettings.emit)
        
        is_on = StartupManager.is_enabled()
        # 统一使用右侧文本标记勾选
        autostart_text = f"开机自启{'        ✔' if is_on else ''}"
        menu.addAction(autostart_text).triggered.connect(lambda: StartupManager.set_enabled(not is_on))
        
        menu.addSeparator()
        menu.addAction("重启应用").triggered.connect(self.requestRestart.emit)
        menu.addAction("退出程序").triggered.connect(self.requestQuit.emit)
        
        self.activateWindow() # 确保窗口激活，解决点击外部不消失的问题
        menu.exec(global_pos)

    def _show_hotkey_dialog(self):
        asr = self.m_cfg.hotkey_asr
        toggle = self.m_cfg.hotkey_toggle_ui
        dlg = HotkeyDialog(self, asr, toggle)
        if dlg.exec():
            new_asr, new_toggle = dlg.get_values()
            if new_asr or new_toggle:
                self.requestHotkeyChange.emit(new_asr, new_toggle)
