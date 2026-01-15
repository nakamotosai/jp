from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QGraphicsDropShadowEffect, 
    QApplication, QLabel, QPushButton, QSlider, QFrame, QGridLayout, QMenu, QDialog, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent, QPoint, QTimer, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QPainter, QLinearGradient, QBrush, QFontDatabase, QFontMetrics, QPalette, QPainterPath, QIcon, QKeyEvent, QKeySequence, QScreen, QPen, QTextCursor
import os, json, sys, time, random

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

from font_manager import FontManager
from asr_manager import ASRManager


class ScaledTextEdit(QTextEdit):
    sizeHintChanged = pyqtSignal(int, int) # suggested width, height
    submitPressed = pyqtSignal()
    newlineInserted = pyqtSignal()

    def __init__(self, parent=None, placeholder="", color="black", hide_cursor=False):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QTextEdit.Shape.NoFrame)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        self.document().contentsChanged.connect(self._on_content_changed)
        
        self.base_min_height = 50 
        self.base_max_height = 100 
        self.base_font_size = 15 
        self.current_scale = 1.0
        self.current_family = FontManager.get_font(True)
        self.color = color
        self.font_factor = 1.0
        self.setCursorWidth(0 if hide_cursor else 4) 
        self.apply_scale(1.0)
        self.document().contentsChanged.connect(self._center_vertically)

    def contextMenuEvent(self, event):
        """Disable default menu and show app menu"""
        win = self.window()
        if hasattr(win, "show_context_menu"):
            win.show_context_menu(event.globalPos())

    def mousePressEvent(self, e):
        """Pass drag start to window if left button"""
        if e.button() == Qt.MouseButton.LeftButton:
            self.window()._start_drag(e.globalPosition().toPoint())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        """Pass drag to window if dragging"""
        win = self.window()
        if hasattr(win, '_dragging') and win._dragging:
            win.move(e.globalPosition().toPoint() - win._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        win = self.window()
        if hasattr(win, '_dragging'):
            win._dragging = False
        super().mouseReleaseEvent(e)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_vertically()

    def _center_vertically(self):
        # Calculate dynamic margin to center text vertically
        doc_height = self.document().size().height()
        widget_height = self.height()
        if widget_height > doc_height:
            # Move text slightly up (visual center) by reducing top margin
            margin = (widget_height - doc_height) / 2 - 2
            self.setViewportMargins(0, max(0, int(margin)), 0, 0)
        else:
            self.setViewportMargins(0, 0, 0, 0)

    def apply_scale(self, scale, family=None, font_factor=None):
        self.current_scale = scale
        if family: self.current_family = family
        if font_factor: self.font_factor = font_factor
        self.update_style(self.color)
        self._on_content_changed()

    def set_text_color(self, color):
        """Standard method for external callers like asr_mode"""
        self.update_style(color)

    def update_style(self, color):
        self.color = color
        self.document().setDocumentMargin(0) 
        placeholder_color = "rgba(0, 0, 0, 0.4)" if color != "white" else "rgba(255, 255, 255, 0.4)"
        self.setStyleSheet(f"""
            QTextEdit {{
                color: {color};
                background: transparent;
                font-weight: bold;
                font-size: {int(self.base_font_size * self.current_scale * self.font_factor)}px;
                font-family: "{self.current_family}";
                padding: 0px 2px 0px 2px; /* Align with SlotMachineLabel */
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
            max_line_w = max_line_w if max_line_w > metrics.horizontalAdvance(line if line else " ") else metrics.horizontalAdvance(line if line else " ")
        
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

class SlotMachineLabel(QLabel):
    """
    老虎机式滚动文字组件
    文字会像老虎机一样急速变化，然后逐一归位
    """
    animationFinished = pyqtSignal()

    def __init__(self, parent=None, text="按住快捷键说话", color="white"):
        super().__init__(parent)
        self._target_text = text
        self._display_text = [""] * len(text)
        self._settled_count = 0
        self._color = color
        self._is_animating = False
        self._scale = 1.0
        self._font_factor = 1.0
        self._family = FontManager.get_font(True)
        
        # 字符库定义
        self._charsets = {
            "default": "あいうえおアイウエオ0123456789!?$&%#@*",
            "zh": "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年样能下过子说产种面而方后多定行学法所民得意经十三之进着等部度",
            "jp": "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんアイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
        }
        self._random_chars = self._charsets["default"]
        
        self._timer = QTimer(self)
        self._timer.setInterval(40) # 约 25fps 的急速变换
        self._timer.timeout.connect(self._update_animation)
        
        self._timer.timeout.connect(self._update_animation)
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apply_scale(1.0)

    def set_character_set(self, charset_name):
        """设置使用的随机字符库: 'zh', 'jp', 'default'"""
        if charset_name in self._charsets:
            self._random_chars = self._charsets[charset_name]

    def apply_scale(self, scale, family=None, font_factor=None):
        self._scale = scale
        if family: self._family = family
        if font_factor: self._font_factor = font_factor
        
        size = int(15 * self._scale * self._font_factor)
        self.setStyleSheet(f"""
            QLabel {{
                color: {self._color};
                background: transparent;
                font-weight: bold;
                font-size: {size}px;
                font-family: "{self._family}";
                border: none;
                margin: 0px;
                padding: 0px 0px 4px 0px; /* Top Right Bottom Left */
                qproperty-indent: 0;
            }}
        """)
        self.update()

    def set_text_color(self, color):
        self._color = color
        self.apply_scale(self._scale)

    def set_target_text(self, text):
        """设置目标文本，用于动态更改"""
        self._target_text = text
        self._display_text = [""] * len(text)
        self._settled_count = 0

    def start_animation(self):
        """开始急速变换"""
        if self._is_animating: return
        self._is_animating = True
        self._settled_count = 0
        
        # 强制起始长度至少为 12 (撑满效果)
        anim_len = max(len(self._target_text), 12)
        self._initial_step_count = anim_len
        self._display_text = [random.choice(self._random_chars) for _ in range(anim_len)]
        self._timer.start()

    def settle_one_by_one(self, start_delay=0):
        """开始逐个归位，支持延迟开始"""
        if not self._is_animating:
            self.start_animation()
            
        if start_delay > 0:
            QTimer.singleShot(start_delay, self._settle_step)
        else:
            self._settle_step()

    def _settle_step(self):
        # 动态计算归位间隔，使总时长约为 2000ms
        total_duration = 2000
        # 使用初始长度来计算步长，保证节奏一直
        step_delay = int(total_duration / max(1, getattr(self, '_initial_step_count', len(self._target_text))))
        # 限制单字间隔范围
        step_delay = max(50, min(step_delay, 400))
        
        if self._settled_count < len(self._target_text):
            # 阶段 A: 定格有效字符
            self._display_text[self._settled_count] = self._target_text[self._settled_count]
            self._settled_count += 1
            QTimer.singleShot(step_delay, self._settle_step)
            
        elif len(self._display_text) > len(self._target_text):
            # 阶段 B: 消除多余字符 (从紧挨着正文的位置开始消除，造成收缩效果)
            # 例如: "ABCxxxx" -> "ABCxxx" -> "ABCxx"
            self._display_text.pop(len(self._target_text))
            QTimer.singleShot(step_delay, self._settle_step)
            
        else:
            # 全部完成
            self._is_animating = False
            self._timer.stop()
            self.setText(self._target_text)
            self.animationFinished.emit()

    def _update_animation(self):
        # 对未归位的字符进行随机变换
        # 注意：_display_text 长度可能会变化，必须动态获取
        for i in range(self._settled_count, len(self._display_text)):
            self._display_text[i] = random.choice(self._random_chars)
        
        self.setText("".join(self._display_text))

class FadingOverlay(QWidget):
    def __init__(self, round_top=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(15)
        self.color = QColor(255, 255, 255)
        self.round_top = round_top
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

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
        self.base_size = 16  # Reduced from 20
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setVisible(False)
        self.theme_mode = "Dark"
        self.scale = 1.0
        self.update_style()

    def apply_scale(self, scale):
        self.scale = scale
        self.update_style()

    def update_style(self, theme=None):
        if theme: self.theme_mode = theme
        size = int(self.base_size * self.scale)
        self.setFixedSize(size, size)
        bg_hover = "rgba(255,255,255,0.2)" if self.theme_mode == "Dark" else "rgba(0,0,0,0.2)"
        bg = "rgba(255,255,255,0.1)" if self.theme_mode == "Dark" else "rgba(0,0,0,0.1)"
        color = "white" if self.theme_mode == "Dark" else "#333"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border-radius: {size // 2}px;
                font-size: {int(10 * self.scale)}px;
                font-weight: bold;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
        """)

class VoicePulseButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)  # Reduced from 50 to fit smaller card
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 避免点击按钮时导致文本框失去焦点
        self._is_recording = False
        self._pulse_radius = 0
        self._pulse_max = 20
        self.scale = 1.0
        
        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius")
        self.pulse_anim.setDuration(1200)
        self.pulse_anim.setLoopCount(-1)
        self.pulse_anim.setStartValue(0)
        self.pulse_anim.setEndValue(20) 
        self.pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.bg_color = QColor(0, 0, 0, 15)
        self.icon_color = QColor(100, 100, 100)
        self.pulse_color = QColor(255, 60, 60, 100)

    def apply_scale(self, scale):
        self.scale = scale
        size = int(40 * scale)
        self.setFixedSize(size, size)
        self._pulse_max = 20 * scale
        self.pulse_anim.stop()
        self.pulse_anim.setEndValue(self._pulse_max)
        if self._is_recording:
            self.pulse_anim.start()
        self.update()

    def set_recording(self, recording):
        self._is_recording = recording
        if recording:
            if self.pulse_anim.state() != QPropertyAnimation.State.Running:
                self.pulse_anim.start()
        else:
            self.pulse_anim.stop()
            self._pulse_radius = 0
        self.update()
        self.repaint() # 强制立即重绘，确保红色光圈立即出现

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
            alpha = int(100 * (1.0 - self._pulse_radius / self._pulse_max if self._pulse_max > 0 else 0))
            c = QColor(self.pulse_color.red(), self.pulse_color.green(), self.pulse_color.blue(), alpha)
            painter.setBrush(QBrush(c))
            r = int(self._pulse_radius + 5 * self.scale)
            painter.drawEllipse(center, r, r)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.pulse_color if self._is_recording else self.bg_color))
        r_inner = int(12 * self.scale)
        painter.drawEllipse(center, r_inner, r_inner)
        
        painter.setPen(Qt.PenStyle.NoPen)
        icon_c = QColor("white") if self._is_recording else self.icon_color
        painter.setBrush(QBrush(icon_c))
        # Scaled icon parts
        iw = int(6 * self.scale)
        ih = int(10 * self.scale)
        painter.drawRoundedRect(center.x()-iw//2, center.y()-int(7*self.scale), iw, ih, int(3*self.scale), int(3*self.scale))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(icon_c.red(), icon_c.green(), icon_c.blue(), 200), max(1, int(1.5*self.scale))))
        aw = int(10 * self.scale)
        ah = int(8 * self.scale)
        painter.drawArc(center.x()-aw//2, center.y()-int(3*self.scale), aw, ah, 180*16, 180*16)
        painter.drawLine(center.x(), center.y()+int(5*self.scale), center.x(), center.y()+int(7*self.scale))
        painter.drawLine(center.x()-int(3*self.scale), center.y()+int(7*self.scale), center.x()+int(3*self.scale), center.y()+int(7*self.scale))

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

class VoiceWaveform(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setMinimumWidth(100)
        self._levels = [0.1] * 6
        self._target_levels = [0.1] * 6
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(30)
        self.bar_color = QColor(100, 100, 100) # 深灰色

    def set_level(self, rms):
        # Normalize RMS (roughly 0 to 1000+) to 0.1 - 1.0
        normalized = max(0.1, min(1.0, rms / 800.0))
        for i in range(len(self._target_levels)):
            variation = random.uniform(0.7, 1.3)
            self._target_levels[i] = normalized * variation

    def _animate(self):
        changed = False
        for i in range(len(self._levels)):
            if abs(self._levels[i] - self._target_levels[i]) > 0.01:
                # Smooth transition
                self._levels[i] += (self._target_levels[i] - self._levels[i]) * 0.3
                changed = True
            else:
                # Slight decay if no input
                self._target_levels[i] *= 0.95
        if changed:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        n = len(self._levels)
        bar_w = 4
        spacing = 8
        total_w = n * bar_w + (n-1) * spacing
        start_x = (w - total_w) / 2

        for i in range(n):
            bar_h = h * self._levels[i] * 0.8
            bar_h = max(4, bar_h)
            x = start_x + i * (bar_w + spacing)
            y = (h - bar_h) / 2
            
            # Draw rounded bar
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.bar_color))
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 2, 2)

class HotkeyDialog(QDialog):
    def __init__(self, parent=None, current_asr="", current_toggle=""):
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setFixedSize(320, 260)
        self.setStyleSheet("""
            QDialog { background-color: #f5f5f7; border-radius: 12px; }
            QLabel { color: #333333; font-weight: bold; font-family: "思源黑体"; font-size: 13px; }
            QLabel#instruction { color: #666666; font-weight: normal; font-size: 11px; }
            QPushButton { 
                background-color: #007aff; color: white; border-radius: 6px; padding: 10px; 
                font-weight: bold; border: none; font-size: 13px;
            }
            QPushButton:hover { background-color: #0063cc; }
            QLineEdit { 
                border: 2px solid #ddd; border-radius: 6px; padding: 8px; background: white; 
                font-weight: bold; color: #333333; font-size: 14px;
            }
            QLineEdit:focus { border-color: #007aff; background-color: #f0f7ff; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(10)
        
        instr = QLabel("点击输入框后按下键盘按键即可设置:")
        instr.setObjectName("instruction")
        layout.addWidget(instr)
        layout.addSpacing(5)
        
        layout.addWidget(QLabel("按住说话热键:"))
        self.asr_input = QLineEdit(current_asr)
        self.asr_input.setReadOnly(True)
        self.asr_input.setPlaceholderText("点击以录制...")
        self.asr_input.installEventFilter(self)
        layout.addWidget(self.asr_input)
        
        layout.addSpacing(5)
        layout.addWidget(QLabel("显示/隐藏界面:"))
        self.toggle_input = QLineEdit(current_toggle)
        self.toggle_input.setReadOnly(True)
        self.toggle_input.setPlaceholderText("点击以录制...")
        self.toggle_input.installEventFilter(self)
        layout.addWidget(self.toggle_input)
        
        layout.addStretch()
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存设置")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("background-color: #e5e5ea; color: #333333;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if not isinstance(event, QKeyEvent): return False
            key = event.key()
            mod = event.modifiers()
            
            # Handle Escape to cancel recording/lose focus
            if key == Qt.Key.Key_Escape:
                obj.clearFocus()
                return True

            parts = []
            # Modifier detection
            if mod & Qt.KeyboardModifier.ControlModifier: parts.append("ctrl")
            if mod & Qt.KeyboardModifier.AltModifier: parts.append("alt")
            if mod & Qt.KeyboardModifier.ShiftModifier: parts.append("shift")
            if mod & Qt.KeyboardModifier.MetaModifier or key == Qt.Key.Key_Meta:
                if "meta" not in parts: parts.append("meta")
            
            # Non-modifier key detection
            if key not in [Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta]:
                # Special mapping
                if key == Qt.Key.Key_CapsLock:
                    kn = "caps_lock"
                elif key == Qt.Key.Key_Space:
                    kn = "space"
                else:
                    kn = QKeySequence(key).toString().lower()
                
                if kn and kn not in parts:
                    parts.append(kn)
            
            if parts:
                obj.setText("+".join(parts))
            return True
        return super().eventFilter(obj, event)

    def get_values(self):
        return self.asr_input.text(), self.toggle_input.text()

class CopyBubble(QLabel):
    """复制成功后的气泡提示 (永久固定在屏幕正下方)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("已复制到剪贴板")
        self.setFixedSize(140, 32)
        
        # 建立淡出动画
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(400) # 约 60 帧的感官时长
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_anim.finished.connect(self.hide)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.start_fade_out)

    def show_at(self, pos=None, theme="Dark"):
        """忽略 pos，始终显示在屏幕正下方"""
        if theme == "Light":
            bg, fg, border = "#ffffff", "#333333", "#dddddd"
        else:
            bg, fg, border = "#1e1e1e", "white", "#4d4d4d"
            
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                padding: 4px;
            }}
        """)
        
        # 计算屏幕正下方位置
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 60 
        
        self.setWindowOpacity(1.0)
        self.move(x, y)
        self.show()
        self.raise_()
        self.hide_timer.start(1000) # 1秒后开始淡出

    def start_fade_out(self):
        self.fade_anim.start()

class FloatingVoiceIndicator(QWidget):
    """悬浮录音指示器，在 ASR 模式隐藏界面录音时显示"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(120, 120) 
        
        self.level = 0.1
        self.smooth_level = 0.1
        self.pulse_radius = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(8)
        
        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius")
        self.pulse_anim.setDuration(1000)
        self.pulse_anim.setLoopCount(-1)
        self.pulse_anim.setStartValue(0)
        self.pulse_anim.setEndValue(35) 
        self.pulse_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    def set_level(self, rms):
        target = max(0.1, min(1.0, rms / 800.0))
        self.level = target

    def get_pulse_radius(self): return self._pulse_radius
    def set_pulse_radius(self, r): 
        self._pulse_radius = r
        self.update()
    pulse_radius = pyqtProperty(float, fget=get_pulse_radius, fset=set_pulse_radius)

    def _animate(self):
        self.smooth_level += (self.level - self.smooth_level) * 0.2
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.pulse_anim.start()
        self._reposition()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.pulse_anim.stop()

    def _reposition(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 80 
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        
        if self.smooth_level > 0.12:
            alpha = int(180 * (1.0 - self.pulse_radius / 35.0) * self.smooth_level)
            painter.setPen(Qt.PenStyle.NoPen)
            pulse_color = QColor(255, 60, 60, alpha)
            painter.setBrush(QBrush(pulse_color))
            r_pulse = int(22 + self.pulse_radius * self.smooth_level)
            painter.drawEllipse(center, r_pulse, r_pulse)
        
        bg_radius = 22
        painter.setBrush(QBrush(QColor(20, 20, 20, 230)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, bg_radius, bg_radius)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("white")))
        painter.drawRoundedRect(center.x()-4, center.y()-8, 8, 13, 4, 4)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        p = painter.pen()
        p.setColor(QColor(255, 255, 255, 200))
        p.setWidth(2)
        painter.setPen(p)
        painter.drawArc(center.x()-8, center.y()-3, 16, 12, 180*16, 180*16)
        painter.drawLine(center.x(), center.y()+9, center.x(), center.y()+12)
        painter.drawLine(center.x()-4, center.y()+12, center.x()+4, center.y()+12)

class TranslatorWindow(QWidget):
    requestTranslation = pyqtSignal(str)
    sigTranslationStarted = pyqtSignal()
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
    requestAutoTTSChange = pyqtSignal(bool)
    requestTTSDelayChange = pyqtSignal(int)
    requestPersonalityChange = pyqtSignal(str)
    requestHotkeyChange = pyqtSignal(str, str)
    requestRestart = pyqtSignal()
    requestOpenSettings = pyqtSignal()
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
        self.jp_display = ScaledTextEdit(self, "翻訳を待機中", "white", hide_cursor=True)
        self.jp_display.setReadOnly(True) 
        self.jp_display.viewport().setCursor(Qt.CursorShape.ArrowCursor) 
        self.jp_display.sizeHintChanged.connect(self._handle_resizing)
        self.jp_display.submitPressed.connect(self._on_submit)
        
        text_shadow = QGraphicsDropShadowEffect(self)
        text_shadow.setBlurRadius(4); text_shadow.setXOffset(1); text_shadow.setYOffset(1); text_shadow.setColor(QColor(0, 0, 0, 40))
        self.jp_display.setGraphicsEffect(text_shadow)
        
        self.jp_slot = SlotMachineLabel(self, "翻訳を待機中", "white")
        self.jp_slot.set_character_set("jp")
        self.jp_slot.setVisible(False)
        self.jp_slot.animationFinished.connect(lambda: self._on_prompt_anim_finished("jp"))

        self.top_layout.addWidget(self.jp_badge); self.top_layout.addWidget(self.jp_display); self.top_layout.addWidget(self.jp_slot, 1)
        self.top_layout.setStretch(2, 1) # Set stretch for display/slot
        self.container_layout.addWidget(self.top_section)
        self.top_fade = FadingOverlay(True, self.top_section)

        self.divider = RainbowDivider()
        self.container_layout.addWidget(self.divider)

        self.bottom_section = QWidget(); self.bottom_section.setObjectName("bottom_section")
        self.bottom_layout = QHBoxLayout(self.bottom_section)
        self.bottom_layout.setSpacing(10)
        self.bottom_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.zh_badge = Badge("中>", "rgba(0,0,0,0.05)", "#333333")
        self.zh_input = ScaledTextEdit(self, "说点中文...", "#333333")
        self.zh_input.sizeHintChanged.connect(self._handle_resizing)
        self.zh_input.textChanged.connect(self._on_text_changed)
        self.zh_input.submitPressed.connect(self._on_submit)
        
        self.zh_slot = SlotMachineLabel(self, "说点中文...", "#333333")
        self.zh_slot.set_character_set("zh")
        self.zh_slot.setVisible(False)
        self.zh_slot.animationFinished.connect(lambda: self._on_prompt_anim_finished("zh"))

        self.bottom_layout.addWidget(self.zh_badge); self.bottom_layout.addWidget(self.zh_input); self.bottom_layout.addWidget(self.zh_slot, 1)
        self.bottom_layout.setStretch(2, 1)
        
        self.top_section.installEventFilter(self)
        self.bottom_section.installEventFilter(self)

        # Clear button now parented to bottom_section for dynamic positioning
        self.clear_btn = ClearButton(self.bottom_section)
        self.clear_btn.clicked.connect(self.clear_input_forced)
        
        self.voice_btn = VoicePulseButton(self)
        self.voice_btn.pressed.connect(self._handle_record_start)
        self.voice_btn.released.connect(self._handle_record_stop)
        self.bottom_layout.addWidget(self.voice_btn)

        # 5s Auto-clear timer for zh_input only
        self.auto_clear_zh_timer = QTimer(self)
        self.auto_clear_zh_timer.setSingleShot(True)
        self.auto_clear_zh_timer.setInterval(5000)
        self.auto_clear_zh_timer.timeout.connect(self._auto_clear_zh)
        
        self.waveform = VoiceWaveform(self)
        self.waveform.setVisible(False)
        
        self.container_layout.addWidget(self.bottom_section)
        self.bottom_fade = FadingOverlay(False, self.bottom_section)

        self.container.installEventFilter(self)
        self.top_section.installEventFilter(self)
        self.bottom_section.installEventFilter(self)
        self.zh_input.installEventFilter(self)
        self.jp_display.installEventFilter(self)

        self.copy_bubble = None

        self.anim = QPropertyAnimation(self, b"minimumHeight")
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.is_expanded = False

        self._load_config()
        self._apply_scaling()
        self.debounce_timer = QTimer(); self.debounce_timer.setSingleShot(True); self.debounce_timer.timeout.connect(self._do_translation)
        
        self._dragging = False
        self._drag_pos = None

        self.auto_clear_timer = QTimer(self)
        self.auto_clear_timer.setSingleShot(True)
        self.auto_clear_timer.setInterval(5000)

    def update_result(self, zh_text, jp_text):
        if zh_text: 
            self.zh_input.setPlainText(zh_text)
            self._move_cursor_to_end()
        if jp_text: self.jp_display.setPlainText(jp_text)
        self._handle_resizing()
        # Reset auto-clear timer whenever new text arrives
        if zh_text: 
            self.auto_clear_zh_timer.start()

    def _move_cursor_to_end(self):
        """Internal helper to move blinking cursor to end of Chinese input"""
        cursor = self.zh_input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.zh_input.setTextCursor(cursor)
        self.zh_input.setFocus()

    def _on_text_changed(self):
        text = self.zh_input.toPlainText()
        # 忽略 "识别中..." 和空文本
        if text.strip() and text.strip() != "识别中...": 
            self.auto_clear_zh_timer.start()
            self.sigTranslationStarted.emit()
            self.debounce_timer.start(300)
        else: 
            self.auto_clear_zh_timer.stop()
        self._handle_resizing()

    def _handle_resizing(self):
        s = self.window_scale
        # Updated width to ~250px total (visible area 210 + 40 margins)
        visible_w = 210 * s
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
            h = int(sect_h * s)
            self.zh_input.setFixedHeight(h)
            self.jp_display.setFixedHeight(h)
            self.zh_slot.setFixedHeight(h)
            self.jp_slot.setFixedHeight(h)
        else:
            h = int(45 * s)
            self.zh_input.setFixedHeight(h)
            self.jp_display.setFixedHeight(h)
            self.zh_slot.setFixedHeight(h)
            self.jp_slot.setFixedHeight(h)
        
        self.clear_btn.setVisible(self.is_expanded or bool(text))
        self._update_clear_btn_pos()

        m_x = int(12 * s)
        self.top_layout.setContentsMargins(m_x, 0, m_x, 0)
        self.bottom_layout.setContentsMargins(m_x, 0, m_x, 0)
        self.top_fade.setFixedWidth(int(visible_w))
        self.top_fade.move(0, 0)
        self.bottom_fade.setFixedWidth(int(visible_w))
        self.bottom_fade.move(0, 0)
        
        if self.waveform.isVisible():
            self.waveform.setFixedWidth(self.zh_input.width())
            self.waveform.move(self.zh_input.pos())

    def _update_clear_btn_pos(self):
        """Update X button position to follow text instead of layout-fixed"""
        if not self.zh_input.toPlainText() or not self.clear_btn.isVisible():
            return
            
        cursor = self.zh_input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        rect = self.zh_input.cursorRect(cursor)
        
        # Center the rect vertically within the viewport
        viewport_pos = self.zh_input.viewport().mapTo(self.bottom_section, rect.topRight())
        
        s = self.window_scale
        x = viewport_pos.x() + int(4 * s) # Tightened from 10
        y = viewport_pos.y() + (rect.height() - self.clear_btn.height()) // 2
        
        # Guard against overlapping the voice button
        max_x = self.bottom_section.width() - int(60 * s)
        if x > max_x:
            x = max_x
            
        self.clear_btn.move(x, y)
        self.clear_btn.raise_()

    def _auto_clear_zh(self):
        """Only clear Chinese input, keep Japanese display"""
        self.zh_input.setPlainText("")
        self._handle_resizing()

    def clear_input_forced(self):
        """Forced clear of both sections (X button/manual)"""
        self.zh_input.setPlainText("")
        self.jp_display.setPlainText("")
        self._handle_resizing()

    def _apply_scaling(self):
        s = self.window_scale
        f = self.font_size_factor
        family = FontManager.get_correct_family(self.current_font_name)
        self.jp_badge.apply_scale(s, family); self.zh_badge.apply_scale(s, family)
        self.jp_display.apply_scale(s, family, f); self.zh_input.apply_scale(s, family, f)
        self.zh_slot.apply_scale(s, family, f); self.jp_slot.apply_scale(s, family, f)
        self.voice_btn.apply_scale(s)
        self.clear_btn.apply_scale(s)
        self._handle_resizing(); self._apply_theme()

    def _apply_theme(self):
        if self.theme_mode == "Light":
            top_bg, top_text, top_badge_bg = "rgba(185, 185, 185, 0.9)", "white", "rgba(0,0,0,0.1)"
            bottom_bg, bottom_text, bottom_badge_bg = "rgba(245, 245, 245, 0.98)", "#333333", "rgba(0,0,0,0.05)"
        else:
            top_bg, top_text, top_badge_bg = "rgba(245, 245, 245, 0.98)", "#333333", "rgba(0,0,0,0.05)"
            bottom_bg, bottom_text, bottom_badge_bg = "rgba(45, 45, 45, 0.98)", "white", "rgba(255,255,255,0.1)"
        r = int(12 * self.window_scale)
        self.setStyleSheet(f"""
            QWidget#top_section {{ background-color: {top_bg}; border-top-left-radius: {r}px; border-top-right-radius: {r}px; border-bottom: none; }}
            QWidget#bottom_section {{ background-color: {bottom_bg}; border-bottom-left-radius: {r}px; border-bottom-right-radius: {r}px; border-top: none; }}
            QWidget#container {{ background: transparent; border: none; }}
        """)
        self.jp_badge.update_style(top_badge_bg, top_text); self.jp_display.update_style(top_text)
        self.zh_badge.update_style(bottom_badge_bg, bottom_text); self.zh_input.update_style(bottom_text)
        # 老虎机动画统一使用半透明灰色，避免太亮
        zh_slot_color = "rgba(255,255,255,0.5)" if self.theme_mode == "Dark" else "rgba(0,0,0,0.4)"
        jp_slot_color = "rgba(0,0,0,0.4)" if self.theme_mode == "Dark" else "rgba(255,255,255,0.5)"
        self.zh_slot.set_text_color(zh_slot_color); self.jp_slot.set_text_color(jp_slot_color)
        self.top_fade.set_color(top_bg)
        self.bottom_fade.set_color(bottom_bg)
        self.waveform.bar_color = QColor(100, 100, 100) if self.theme_mode == "Light" else QColor(204, 204, 204)
        
        voice_bg = QColor(0, 0, 0, 15) if self.theme_mode == "Light" else QColor(255, 255, 255, 15)
        voice_icon = QColor(100, 100, 100) if self.theme_mode == "Light" else QColor(200, 200, 200)
        self.voice_btn.bg_color = voice_bg
        self.voice_btn.icon_color = voice_icon
        self.voice_btn.update()
        self.clear_btn.update_style(self.theme_mode)

    def contextMenuEvent(self, event):
        self.show_context_menu(event.globalPos())

    def show_context_menu(self, global_pos):
        self.activateWindow()
        self.raise_()
        menu = QMenu()
        modes = [("asr", "中文直出模式"), ("translation", "中日双显模式")]
        from model_config import get_model_config
        current_mode = get_model_config().app_mode
        for m_id, m_name in modes:
            display_name = f"{m_name}{'        ✔' if m_id == current_mode else ''}"
            action = menu.addAction(display_name)
            action.triggered.connect(lambda checked, mid=m_id: self.requestAppModeChange.emit(mid))
        menu.addSeparator()
        menu.addAction("详细设置").triggered.connect(self.requestOpenSettings.emit)
        from startup_manager import StartupManager
        is_on = StartupManager.is_enabled()
        autostart_text = f"开机自启{'        ✔' if is_on else ''}"
        menu.addAction(autostart_text).triggered.connect(lambda: StartupManager.set_enabled(not is_on))
        menu.addSeparator()
        menu.addAction("重启应用").triggered.connect(self.requestRestart.emit)
        menu.addAction("退出程序").triggered.connect(self.requestQuit.emit)
        self.activateWindow()
        menu.exec(global_pos)

    def _show_hotkey_dialog(self):
        asr = self.m_cfg.hotkey_asr
        toggle = self.m_cfg.hotkey_toggle_ui
        dlg = HotkeyDialog(self, asr, toggle)
        if dlg.exec():
            new_asr, new_toggle = dlg.get_values()
            if new_asr or new_toggle:
                self.requestHotkeyChange.emit(new_asr, new_toggle)

    def change_theme(self, t): self.theme_mode = t; self._apply_theme()
    def change_scale(self, s): self.window_scale = s; self._apply_scaling()
    def change_font(self, f): self.current_font_name = f; self._apply_scaling()
    def change_font_size(self, f): self.font_size_factor = f; self._apply_scaling()
    
    def set_font_name(self, name): self.change_font(name)
    def set_scale_factor(self, scale): self.change_scale(scale)
    def _on_submit(self): self.requestSend.emit(self.jp_display.toPlainText())

    def _start_drag(self, pos):
        self._dragging = True
        self._drag_pos = pos - self.pos()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                if isinstance(obj, (QPushButton, ClearButton, VoicePulseButton)) or obj in [self.clear_btn, self.voice_btn]:
                    return super().eventFilter(obj, event)
                self._start_drag(event.globalPosition().toPoint())
                if obj in [self.zh_input, self.jp_display]: 
                    return False 
                return True
        elif event.type() == QEvent.Type.MouseMove:
            if getattr(self, '_dragging', False):
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if getattr(self, '_dragging', False):
                    self._dragging = False
                    # 记录位置到配置中
                    self.m_cfg.set_window_pos(self.x(), self.y())
        elif event.type() == QEvent.Type.MouseButtonDblClick:
            if obj in [self.zh_input, self.jp_display]:
                QTimer.singleShot(50, lambda: self._handle_copy_on_dblclick(obj))
                return False
        return super().eventFilter(obj, event)

    def _handle_copy_on_dblclick(self, obj):
        cursor = obj.textCursor()
        text = cursor.selectedText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            if self.copy_bubble is None:
                self.copy_bubble = CopyBubble()
            # 始终在屏幕下方居中显示
            self.copy_bubble.show_at(None, self.theme_mode)

    def showEvent(self, event):
        super().showEvent(event)
        self._dragging = False
        
        # 处理窗口定位
        wx, wy = self.m_cfg.window_pos
        if wx == -1 or wy == -1:
            # 居中显示
            screen = QApplication.primaryScreen().geometry()
            size = self.frameGeometry().size()
            x = (screen.width() - size.width()) // 2
            y = (screen.height() - size.height()) // 2
            self.move(x, y)
        else:
            # 恢复之前位置
            self.move(wx, wy)

        self.activateWindow()
        self.raise_()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except: pass
            
        if not self.zh_input.toPlainText():
            self.zh_input.setVisible(False)
            self.zh_slot.setVisible(True)
            self.zh_slot.start_animation()
            
            # 如果 ASR 引擎已就绪，播个 1 秒动画自动归位；否则等待信号
            is_asr_ready = False
            try:
                is_asr_ready = ASRManager().worker.engine.is_loaded
            except: pass
            
            if is_asr_ready:
                QTimer.singleShot(1000, self.zh_slot.settle_one_by_one)
            
        current_jp = self.jp_display.toPlainText()
        if not current_jp or current_jp == "翻訳を待機中":
            self.jp_display.setVisible(False)
            self.jp_slot.setVisible(True)
            self.jp_slot.start_animation()
            # 日文翻译一般切过来就是就绪的（除非正在下模型），我们也给个 1 秒仪式感
            QTimer.singleShot(1000, self.jp_slot.settle_one_by_one)

    def _do_translation(self):
        text = self.zh_input.toPlainText()
        if text.strip(): 
            self.requestTranslation.emit(text)
    def set_zh_text(self, text): 
        """Update Chinese text without immediate forced translation; let debounce handle it"""
        self.zh_input.setPlainText(text)
        self.zh_input._on_content_changed()

    def _handle_record_start(self): 
        self.auto_clear_zh_timer.stop() # Prevent clearing while speaking
        self.requestRecordStart.emit()
        self.zh_input.clear()
        self.zh_input.setPlaceholderText("识别中...")
        
    def _handle_record_stop(self): 
        self.update_recording_status(False)
        self.requestRecordStop.emit()
        self._move_cursor_to_end() # Focus and move cursor after recording finishes
    def update_recording_status(self, is_recording):
        self.voice_btn.set_recording(is_recording)
        if is_recording:
            if not self.zh_input.toPlainText():
                self.zh_input.setPlaceholderText("识别中...")
        else: 
            self.zh_input.setPlaceholderText("说点中文...")
    def update_audio_level(self, level):
        if self.waveform.isVisible():
            self.waveform.set_level(level)

    def on_translation_ready(self, t): 
        # 强制关闭两个老虎机动画
        if self.jp_slot.isVisible():
            self.jp_slot.setVisible(False); self.jp_display.setVisible(True)
        if self.zh_slot.isVisible():
            self.zh_slot.setVisible(False); self.zh_input.setVisible(True)
            
        self.jp_display.setPlaceholderText("翻訳を待機中"); 
        self.jp_display.setPlainText(t); 
        self.jp_display._on_content_changed()

    def update_status(self, status):
        if status == "loading" or "正在切换模型" in status: 
            self.jp_display.setVisible(False)
            self.jp_slot.setVisible(True)
            self.jp_slot.start_animation()
        elif status == "asr_loading" or "正在加载ASR模型" in status: 
            self.zh_input.setVisible(False)
            self.zh_slot.setVisible(True)
            self.zh_slot.start_animation()
        elif status == "translating":
            if not self.jp_display.toPlainText(): 
                self.jp_display.setPlaceholderText(self.m_cfg.get_prompt("translating") or "正在翻译...")
        elif status == "idle" or "加载完成" in status or "准备就绪" in status: 
            # 停止正在进行的动画
            if self.zh_slot.isVisible():
                self.zh_slot.settle_one_by_one()
            if self.jp_slot.isVisible():
                self.jp_slot.settle_one_by_one()
                
            self.jp_display.setPlaceholderText("翻訳を待機中")
            self.zh_input.setPlaceholderText("说点中文...")
            if self.m_cfg.is_placeholder_text(self.zh_input.toPlainText()) or self.zh_input.toPlainText() == "说点中文...":
                self.zh_input.clear()
            if self.m_cfg.is_placeholder_text(self.jp_display.toPlainText()) or self.jp_display.toPlainText() == "翻訳を待机中":
                self.jp_display.clear()

    def update_segment(self, text):
        """Standard entry point for ASR results"""
        if text == "识别中...": return # 忽略此中间状态文本
        
        if self.zh_slot.isVisible():
            self.zh_slot.setVisible(False); self.zh_input.setVisible(True)
        if self.jp_slot.isVisible():
            self.jp_slot.setVisible(False); self.jp_display.setVisible(True)
        self.set_zh_text(text)
    def focus_input(self):
        self.zh_input.setFocus(); c = self.zh_input.textCursor(); c.movePosition(c.MoveOperation.End); self.zh_input.setTextCursor(c)
    def _on_prompt_anim_finished(self, lang):
        if lang == "zh":
            self.zh_slot.setVisible(False); self.zh_input.setVisible(True)
        else:
            self.jp_slot.setVisible(False); self.jp_display.setVisible(True)
    def clear_input(self): 
        self.zh_input.clear()
        self.zh_input._on_content_changed()
    def clear_all(self):
        self.zh_input.clear()
        self.jp_display.clear()
        self.jp_display._on_content_changed()
        self.zh_input._on_content_changed()
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.window_scale = data.get("scale", 1.0)
                    self.font_size_factor = data.get("font_scale", 1.0)
            except: pass