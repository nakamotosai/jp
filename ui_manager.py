import os, json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QGraphicsDropShadowEffect, 
    QApplication, QLabel, QPushButton, QSlider, QFrame, QGridLayout, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent, QPoint, QTimer, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QPainter, QLinearGradient, QBrush, QFontDatabase, QFontMetrics, QPalette, QPainterPath, QIcon
from model_config import ASROutputMode

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Global Font Loading
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
SERIF_FONT_PATH = os.path.join(FONT_DIR, "NotoSerifSC-Regular.otf")
SANS_FONT_PATH = os.path.join(FONT_DIR, "NotoSansSC-Regular.otf")
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

class FontManager:
    _serif_family = "Microsoft YaHei"
    _sans_family = "Microsoft YaHei"
    
    @classmethod
    def load_fonts(cls):
        if os.path.exists(SERIF_FONT_PATH):
            id = QFontDatabase.addApplicationFont(SERIF_FONT_PATH)
            if id != -1:
                cls._serif_family = QFontDatabase.applicationFontFamilies(id)[0]
        if os.path.exists(SANS_FONT_PATH):
            id = QFontDatabase.addApplicationFont(SANS_FONT_PATH)
            if id != -1:
                cls._sans_family = QFontDatabase.applicationFontFamilies(id)[0]

    @classmethod
    def get_font(cls, serif=True):
        return cls._serif_family if serif else cls._sans_family

class ScaledTextEdit(QTextEdit):
    sizeHintChanged = pyqtSignal(int, int) # suggested width, height
    submitPressed = pyqtSignal()
    newlineInserted = pyqtSignal()

    def __init__(self, parent=None, placeholder="", color="black"):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QTextEdit.Shape.NoFrame)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        self.document().contentsChanged.connect(self._on_content_changed)
        
        self.base_min_height = 50 
        self.base_max_height = 100 
        self.base_font_size = 12 
        self.current_scale = 1.0
        self.current_family = FontManager.get_font(True)
        self.color = color
        self.font_factor = 1.0
        self.setCursorWidth(4) 
        self.apply_scale(1.0)

    def apply_scale(self, scale, family=None, font_factor=None):
        self.current_scale = scale
        if family: self.current_family = family
        if font_factor: self.font_factor = font_factor
        self.update_style(self.color)
        self._on_content_changed()

    def update_style(self, color):
        self.color = color
        self.document().setDocumentMargin(4) 
        placeholder_color = "rgba(0, 0, 0, 0.4)" if color != "white" else "rgba(255, 255, 255, 0.4)"
        self.setStyleSheet(f"""
            QTextEdit {{
                color: {color};
                background: transparent;
                font-weight: bold;
                font-size: {int(self.base_font_size * self.current_scale * self.font_factor)}px;
                font-family: "{self.current_family}";
                padding: 0px;
                margin: 0px;
                border: none;
            }}
            QTextEdit:empty {{ color: {placeholder_color}; }}
        """)

    def _on_content_changed(self):
        metrics = QFontMetrics(self.font())
        lines = self.toPlainText().split('\n')
        max_line_w = 0
        for line in lines:
            max_line_w = max(max_line_w, metrics.horizontalAdvance(line if line else " "))
        
        suggested_width = max_line_w + 10
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        doc_height = int(self.document().size().height())
        self.sizeHintChanged.emit(suggested_width, doc_height)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier or event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                self.insertPlainText("\n")
                self.newlineInserted.emit()
            else:
                self.submitPressed.emit()
        else:
            super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())

class FadingOverlay(QWidget):
    def __init__(self, round_top=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(15)
        self.color = QColor(255, 255, 255)
        self.round_top = round_top
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_color(self, c):
        if isinstance(c, str):
            if c.startswith("rgba"):
                p = c.replace("rgba(", "").replace(")", "").split(",")
                self.color = QColor(int(p[0]), int(p[1]), int(p[2]), int(float(p[3]) * 255))
            else:
                self.color = QColor(c)
        else:
            self.color = c
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, self.color)
        grad.setColorAt(1, QColor(self.color.red(), self.color.green(), self.color.blue(), 0))
        if self.round_top:
            path = QPainterPath()
            r = 12 
            path.moveTo(0, self.height())
            path.lineTo(0, r)
            path.quadTo(0, 0, r, 0)
            path.lineTo(self.width() - r, 0)
            path.quadTo(self.width(), 0, self.width(), r)
            path.lineTo(self.width(), self.height())
            path.closeSubpath()
            painter.fillPath(path, grad)
        else:
            painter.fillRect(self.rect(), grad)

class ClearButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setVisible(False)
        self.update_style()

    def update_style(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.1);
                color: #999;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.2);
                color: #333;
            }
        """)

class VoicePulseButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_recording = False
        self._pulse_radius = 0
        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius")
        self.pulse_anim.setDuration(1200)
        self.pulse_anim.setLoopCount(-1)
        self.pulse_anim.setStartValue(0)
        self.pulse_anim.setEndValue(15)
        self.pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.bg_color = QColor(0, 0, 0, 15)
        self.icon_color = QColor(100, 100, 100)
        self.pulse_color = QColor(255, 60, 60, 100)

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
        if self._is_recording:
            painter.setPen(Qt.PenStyle.NoPen)
            alpha = int(100 * (1.0 - self._pulse_radius / 15.0))
            c = QColor(self.pulse_color.red(), self.pulse_color.green(), self.pulse_color.blue(), alpha)
            painter.setBrush(QBrush(c))
            r = int(self._pulse_radius + 5)
            painter.drawEllipse(center, r, r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.pulse_color if self._is_recording else self.bg_color))
        painter.drawEllipse(center, 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        icon_c = QColor("white") if self._is_recording else self.icon_color
        painter.setBrush(QBrush(icon_c))
        painter.drawRoundedRect(center.x()-3, center.y()-7, 6, 10, 3, 3)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(icon_c.red(), icon_c.green(), icon_c.blue(), 200))
        painter.drawArc(center.x()-5, center.y()-3, 10, 8, 180*16, 180*16)
        painter.drawLine(center.x(), center.y()+5, center.x(), center.y()+7)
        painter.drawLine(center.x()-3, center.y()+7, center.x()+3, center.y()+7)

class Badge(QPushButton):
    def __init__(self, text, bg_color, text_color):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.base_width, self.base_height, self.base_font_size = 35, 23, 11 
        self.bg_color, self.text_color = bg_color, text_color
        self.current_scale = 1.0
        self.current_family = FontManager.get_font(True)
        self.apply_scale(1.0)
    def apply_scale(self, scale, family=None):
        self.current_scale = scale
        if family: self.current_family = family
        self.setFixedSize(int(self.base_width * scale), int(self.base_height * scale))
        self.update_style(self.bg_color, self.text_color)
    def update_style(self, bg_color, text_color):
        self.bg_color, self.text_color = bg_color, text_color
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) 
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {text_color};
                border-radius: 0px;
                font-size: {int(self.base_font_size * self.current_scale)}px;
                font-weight: bold;
                font-family: "{self.current_family}";
                border: none;
                padding: 0px;
            }}
        """)

class RainbowDivider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.offset = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_animation)
        self.timer.start(50) 
    def _update_animation(self):
        self.offset = (self.offset + 0.005) % 1.0 
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        gradient = QLinearGradient(self.offset * w, 0, (self.offset + 1.0) * w, 0)
        gradient.setSpread(QLinearGradient.Spread.RepeatSpread)
        colors = [(0.0, QColor(255,0,0)), (0.14, QColor(255,127,0)), (0.28, QColor(255,255,0)), (0.42, QColor(0,255,0)), (0.56, QColor(0,0,255)), (0.70, QColor(75,0,130)), (0.84, QColor(148,0,211)), (1.0, QColor(255,0,0))]
        for pos, color in colors:
            gradient.setColorAt(pos, color)
        painter.fillRect(self.rect(), QBrush(gradient))

class TranslatorWindow(QWidget):
    requestTranslation = pyqtSignal(str)
    requestSend = pyqtSignal(str)
    requestAppModeChange = pyqtSignal(str)
    requestASREngineChange = pyqtSignal(str)
    requestTranslatorEngineChange = pyqtSignal(str)
    requestASROutputModeChange = pyqtSignal(str)
    requestThemeChange = pyqtSignal(str)
    requestScaleChange = pyqtSignal(float)
    requestFontChange = pyqtSignal(str)
    requestFontSizeChange = pyqtSignal(float)
    requestRecordStart = pyqtSignal()
    requestRecordStop = pyqtSignal()
    requestPersonalityChange = pyqtSignal(str)
    requestRestart = pyqtSignal()
    requestQuit = pyqtSignal()

    def __init__(self):
        super().__init__()
        FontManager.load_fonts()
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))
        from model_config import get_model_config
        self.m_cfg = get_model_config()
        self.theme_mode, self.window_scale, self.current_font_name, self.font_size_factor = "Dark", 1.0, "思源宋体", 1.0
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.container = QWidget()
        self.container.setObjectName("container")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0) 
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30); shadow.setXOffset(0); shadow.setYOffset(2); shadow.setColor(QColor(0, 0, 0, 100))
        self.container.setGraphicsEffect(shadow)
        self.main_layout.addWidget(self.container)

        self.top_section = QWidget(); self.top_section.setObjectName("top_section")
        self.top_layout = QHBoxLayout(self.top_section)
        self.top_layout.setSpacing(10)
        self.top_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.jp_badge = Badge("日>", "rgba(0,0,0,0.1)", "white")
        self.jp_display = ScaledTextEdit(self, self.m_cfg.get_prompt("idle_tr_res") or "入力をください", "white")
        self.jp_display.setReadOnly(False) 
        self.jp_display.viewport().setCursor(Qt.CursorShape.ArrowCursor) 
        self.jp_display.sizeHintChanged.connect(self._handle_resizing)
        self.jp_display.submitPressed.connect(self._on_submit)
        
        text_shadow = QGraphicsDropShadowEffect(self)
        text_shadow.setBlurRadius(4); text_shadow.setXOffset(1); text_shadow.setYOffset(1); text_shadow.setColor(QColor(0, 0, 0, 40))
        self.jp_display.setGraphicsEffect(text_shadow)
        self.top_layout.addWidget(self.jp_badge); self.top_layout.addWidget(self.jp_display)
        self.container_layout.addWidget(self.top_section)
        self.top_fade = FadingOverlay(True, self.top_section)

        self.divider = RainbowDivider()
        self.container_layout.addWidget(self.divider)

        self.bottom_section = QWidget(); self.bottom_section.setObjectName("bottom_section")
        self.bottom_layout = QHBoxLayout(self.bottom_section)
        self.bottom_layout.setSpacing(10)
        self.bottom_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.zh_badge = Badge("中>", "rgba(0,0,0,0.05)", "#333333")
        self.zh_input = ScaledTextEdit(self, self.m_cfg.get_prompt("idle_tr") or "请输入中文", "#333333")
        self.zh_input.sizeHintChanged.connect(self._handle_resizing)
        self.zh_input.textChanged.connect(self._on_text_changed)
        self.zh_input.submitPressed.connect(self._on_submit)
        self.bottom_layout.addWidget(self.zh_badge); self.bottom_layout.addWidget(self.zh_input)
        
        self.clear_btn = ClearButton(self)
        self.clear_btn.clicked.connect(self.clear_input_forced)
        self.bottom_layout.addWidget(self.clear_btn)
        self.voice_btn = VoicePulseButton(self)
        self.voice_btn.pressed.connect(self._handle_record_start)
        self.voice_btn.released.connect(self._handle_record_stop)
        self.bottom_layout.addWidget(self.voice_btn)
        self.container_layout.addWidget(self.bottom_section)
        self.bottom_fade = FadingOverlay(False, self.bottom_section)

        self.anim = QPropertyAnimation(self, b"minimumHeight")
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.is_expanded = False

        self._load_config()
        self._apply_scaling()
        self.debounce_timer = QTimer(); self.debounce_timer.setSingleShot(True); self.debounce_timer.timeout.connect(self._do_translation)
        
        # Auto-clear timer (5 seconds)
        self.auto_clear_timer = QTimer(self)
        self.auto_clear_timer.setSingleShot(True)
        self.auto_clear_timer.setInterval(5000)
        self.auto_clear_timer.timeout.connect(self.clear_input)

    def clear_input_forced(self):
        self.zh_input.clear()
        self.jp_display.clear()
        self.is_expanded = False
        self._handle_resizing()
        self.zh_input.setFocus()

    def _handle_resizing(self):
        s = self.window_scale
        visible_w = 180 * s
        self.setFixedWidth(int(visible_w + 40))
        text = self.zh_input.toPlainText()
        fm = QFontMetrics(self.zh_input.font())
        doc_margin = int(self.zh_input.document().documentMargin())
        single_line_height = fm.height() + (doc_margin * 2)
        if not self.is_expanded:
            if self.zh_input.document().size().height() > (single_line_height + 5) or "\n" in text:
                self.is_expanded = True
        elif not text:
            self.is_expanded = False
        target_visible_h = 203 if self.is_expanded else 103
        target_h = int((target_visible_h + 40) * s)
        if self.minimumHeight() != target_h:
            self.anim.stop()
            self.anim.setStartValue(self.height())
            self.anim.setEndValue(target_h)
            try: self.anim.valueChanged.disconnect()
            except: pass
            self.anim.valueChanged.connect(lambda v: self.setMaximumHeight(v))
            self.anim.start()
            self.setMaximumHeight(target_h)
        sect_h = 100 if self.is_expanded else 50
        self.top_section.setFixedHeight(int(sect_h * s))
        self.bottom_section.setFixedHeight(int(sect_h * s))
        if self.is_expanded:
            self.zh_input.setFixedHeight(int(sect_h * s))
            self.jp_display.setFixedHeight(int(sect_h * s))
        else:
            self.zh_input.setFixedHeight(single_line_height)
            self.jp_display.setFixedHeight(single_line_height)
        self.clear_btn.setVisible(self.is_expanded or bool(text))
        m_x = int(12 * s)
        self.top_layout.setContentsMargins(m_x, 0, m_x, 0)
        self.bottom_layout.setContentsMargins(m_x, 0, m_x, 0)
        self.top_fade.setFixedWidth(int(visible_w))
        self.top_fade.move(0, 0)
        self.bottom_fade.setFixedWidth(int(visible_w))
        self.bottom_fade.move(0, 0)

    def _apply_scaling(self):
        s = self.window_scale
        f = self.font_size_factor
        family = FontManager.get_font(self.current_font_name == "思源宋体")
        self.jp_badge.apply_scale(s, family); self.zh_badge.apply_scale(s, family)
        self.jp_display.apply_scale(s, family, f); self.zh_input.apply_scale(s, family, f)
        self._handle_resizing(); self._apply_theme()

    def _apply_theme(self):
        if self.theme_mode == "Light":
            top_bg, top_text, top_badge_bg = "rgba(185, 185, 185, 0.9)", "white", "rgba(0,0,0,0.1)"
            bottom_bg, bottom_text, bottom_badge_bg = "rgba(245, 245, 245, 0.98)", "#333333", "rgba(0,0,0,0.05)"
        else:
            top_bg, top_text, top_badge_bg = "rgba(245, 245, 245, 0.98)", "#333333", "rgba(0,0,0,0.05)"
            bottom_bg, bottom_text, bottom_badge_bg = "rgba(45, 45, 45, 0.98)", "white", "rgba(255,255,255,0.1)"
        r = 12 
        self.setStyleSheet(f"""
            QWidget#top_section {{ background-color: {top_bg}; border-top-left-radius: {r}px; border-top-right-radius: {r}px; border-bottom: none; }}
            QWidget#bottom_section {{ background-color: {bottom_bg}; border-bottom-left-radius: {r}px; border-bottom-right-radius: {r}px; border-top: none; }}
            QWidget#container {{ background: transparent; border: none; }}
        """)
        self.jp_badge.update_style(top_badge_bg, top_text); self.jp_display.update_style(top_text)
        self.zh_badge.update_style(bottom_badge_bg, bottom_text); self.zh_input.update_style(bottom_text)
        self.top_fade.set_color(top_bg)
        self.bottom_fade.set_color(bottom_bg)
        voice_bg = QColor(0, 0, 0, 15) if self.theme_mode == "Light" else QColor(255, 255, 255, 15)
        voice_icon = QColor(100, 100, 100) if self.theme_mode == "Light" else QColor(200, 200, 200)
        self.voice_btn.bg_color = voice_bg
        self.voice_btn.icon_color = voice_icon
        self.voice_btn.update()
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {"rgba(255,255,255,0.1)" if self.theme_mode == "Dark" else "rgba(0,0,0,0.1)"};
                color: {bottom_text};
                border-radius: 10px;
                font-size: 10px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {"rgba(255,255,255,0.2)" if self.theme_mode == "Dark" else "rgba(0,0,0,0.2)"};
            }}
        """)

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

    def change_theme(self, t): self.theme_mode = t; self._apply_theme()
    def change_scale(self, s): self.window_scale = s; self._apply_scaling()
    def change_font(self, f): self.current_font_name = f; self._apply_scaling()
    def change_font_size(self, f): self.font_size_factor = f; self._apply_scaling()
    def _on_submit(self): self.requestSend.emit(self.jp_display.toPlainText())
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self._dragging, self._drag_pos = True, e.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, e):
        if hasattr(self, '_dragging') and self._dragging: self.move(e.globalPosition().toPoint() - self._drag_pos)
    def mouseReleaseEvent(self, e): self._dragging = False
    def _on_text_changed(self): 
        self.debounce_timer.start(300)
        if self.zh_input.toPlainText().strip():
            self.auto_clear_timer.start()
        else:
            self.auto_clear_timer.stop()
    def _do_translation(self):
        text = self.zh_input.toPlainText()
        if text.strip(): self.requestTranslation.emit(text)
        else: 
            if not text: self.jp_display.clear()
            self.jp_display._on_content_changed()
    def set_zh_text(self, text): self.zh_input.setPlainText(text); self.zh_input._on_content_changed(); self._do_translation()
    def _handle_record_start(self): 
        self.auto_clear_timer.stop()
        self.update_recording_status(True); self.requestRecordStart.emit()
    def _handle_record_stop(self): 
        self.update_recording_status(False); self.requestRecordStop.emit()
        if self.zh_input.toPlainText().strip():
            self.auto_clear_timer.start()
    def update_recording_status(self, is_recording):
        self.voice_btn.set_recording(is_recording)
        if is_recording:
            self.auto_clear_timer.stop()
            if not self.zh_input.toPlainText(): self.zh_input.setPlaceholderText(self.m_cfg.get_prompt("listening"))
        else: 
            self.zh_input.setPlaceholderText(self.m_cfg.get_prompt("idle_tr"))
            if self.zh_input.toPlainText().strip():
                self.auto_clear_timer.start()
    def update_translation(self, t): 
        self.jp_display.setPlaceholderText(self.m_cfg.get_prompt("idle_tr_res") or "入력을ください"); 
        self.jp_display.setPlainText(t); 
        self.jp_display._on_content_changed()
        if t.strip() or self.zh_input.toPlainText().strip():
            self.auto_clear_timer.start()
    def update_status(self, status):
        if status == "loading": 
            self.jp_display.setPlainText(""); self.jp_display.setPlaceholderText(self.m_cfg.get_prompt("loading"))
        elif status == "asr_loading" or "正在加载ASR模型" in status: 
            self.zh_input.setPlaceholderText(self.m_cfg.get_prompt("init"))
        elif status == "translating":
            if not self.jp_display.toPlainText(): self.jp_display.setPlaceholderText(self.m_cfg.get_prompt("translating"))
        elif status == "idle" or "加载完成" in status: 
            self.jp_display.setPlaceholderText(self.m_cfg.get_prompt("idle_tr_res") or "入力をください")
            self.zh_input.setPlaceholderText(self.m_cfg.get_prompt("idle_tr"))
            
            # Immediate refresh if current text is a placeholder from any scheme
            if self.m_cfg.is_placeholder_text(self.zh_input.toPlainText()):
                self.zh_input.clear()
            if self.m_cfg.is_placeholder_text(self.jp_display.toPlainText()):
                self.jp_display.clear()
    def focus_input(self):
        self.zh_input.setFocus(); c = self.zh_input.textCursor(); c.movePosition(c.MoveOperation.End); self.zh_input.setTextCursor(c)
    def clear_input(self): self.zh_input.clear(); self.jp_display.clear(); self.jp_display._on_content_changed(); self.zh_input._on_content_changed()
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.window_scale = data.get("scale", 1.0)
                    self.font_size_factor = data.get("font_scale", 1.0)
            except: pass