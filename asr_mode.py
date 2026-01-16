from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect, 
    QApplication, QLabel, QPushButton, QFrame, QMenu, QSizePolicy, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QIcon, QFontMetrics, QPen, QBrush, QFont

from font_manager import FontManager
from ui_manager import LOGO_PATH, HotkeyDialog, VoiceWaveform, ScaledTextEdit, ClearButton, SlotMachineLabel
from model_config import get_model_config, ASREngineType, TranslatorEngineType, ASROutputMode
from startup_manager import StartupManager
from asr_manager import ASRManager

# Default fallbacks if needed
DEFAULT_PLACEHOLDER = "按住大写键说话"
DEFAULT_LISTENING = "正在聆听..."

class ASRIconButton(QPushButton):
    def __init__(self, parent=None, icon_type="mic"):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_type = icon_type
        self._is_recording = False
        self._pulse_radius = 0
        self._pulse_max = 20
        self.scale = 1.0
        self.bg_color = QColor(255, 255, 255, 25)
        self.icon_color = QColor(200, 200, 200)
        self.pulse_color = QColor(255, 60, 60, 100)
        
        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius")
        self.pulse_anim.setDuration(1200)
        self.pulse_anim.setLoopCount(-1)
        self.pulse_anim.setStartValue(0)
        self.pulse_anim.setEndValue(20) 
        self.pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def apply_scale(self, scale):
        self.scale = scale
        size = int(50 * scale)
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
            alpha = int(100 * (1.0 - self._pulse_radius / self._pulse_max if self._pulse_max > 0 else 0))
            c = QColor(self.pulse_color.red(), self.pulse_color.green(), self.pulse_color.blue(), alpha)
            painter.setBrush(QBrush(c))
            r = int(self._pulse_radius + 5 * self.scale)
            painter.drawEllipse(center, r, r)
            
        painter.setPen(Qt.PenStyle.NoPen)
        if self._is_recording and self.icon_type == "mic":
            painter.setBrush(QBrush(self.pulse_color))
        else:
            painter.setBrush(QBrush(self.bg_color))
        r_inner = int(12 * self.scale)
        painter.drawEllipse(center, r_inner, r_inner)
        
        icon_c = QColor("white") if (self._is_recording and self.icon_type == "mic") else self.icon_color
        
        if self.icon_type == "clear":
            pen = QPen(icon_c, max(1, int(2 * self.scale)))
            painter.setPen(pen)
            off = int(4 * self.scale)
            painter.drawLine(center.x()-off, center.y()-off, center.x()+off, center.y()+off)
            painter.drawLine(center.x()+off, center.y()-off, center.x()-off, center.y()+off)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(icon_c))
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
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(25, 25, 25, 25)
        self.main_layout.setSpacing(0)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # [Fix] 确保内容始终顶部对齐

        self.container = QFrame()
        self.container.setObjectName("asr_container")
        
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(15, 0, 15, 1) # [Task] 底部留白 1px 配合高度增加，使下边缘下移
        self.container_layout.setSpacing(0)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.container.setGraphicsEffect(shadow)
        
        self.main_layout.addWidget(self.container)

        from model_config import get_model_config
        self.m_cfg = get_model_config()
        
        # Display - using ScaledTextEdit for coordinate tracking
        self.display = ScaledTextEdit(self, self.m_cfg.get_prompt("idle_zh"), "white", hide_cursor=True)
        self.display.setReadOnly(True)
        self.display.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        # self.display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding) # [Fix] Removed override to allow auto-centering with Fixed height
        
        # Waveform
        self.waveform = VoiceWaveform(self)
        self.waveform.setVisible(False)
        

        

        
        # Slot machine label for initial animation - 默认使用灰色
        self.slot_label = SlotMachineLabel(self, self.m_cfg.get_prompt("idle_zh"), "rgba(255,255,255,0.5)")
        self.slot_label.set_character_set("zh")

        self.slot_label.setVisible(False)
        self.slot_label.animationFinished.connect(self._on_animation_finished)
        
        # Add to layout
        self.container_layout.addWidget(self.display, 1)
        self.container_layout.addWidget(self.slot_label, 1)
        self.container_layout.addWidget(self.waveform, 1)


        self.container.installEventFilter(self)
        self.display.installEventFilter(self)

        self.theme_mode = "Dark"
        self.window_scale = 1.0
        self.font_size_factor = 1.0
        self.current_font_name = self.m_cfg.font_name
        self._placeholder_color = "rgba(255,255,255,0.5)"
        self._text_color = "white"
        
        self.height_anim = QPropertyAnimation(self, b"anim_height")
        self.height_anim.setDuration(400) # 400ms 兼顾丝滑与响应速度
        self.height_anim.setEasingCurve(QEasingCurve.Type.OutQuart) 
        
        self.base_height = 50
        self.expanded_height = 100
        self.is_expanded = False
        
        # [Task] 文字淡入淡出特效
        self.content_opacity = QGraphicsOpacityEffect(self.container)
        self.container.setGraphicsEffect(self.content_opacity)
        self.fade_anim = QPropertyAnimation(self.content_opacity, b"opacity")
        self.fade_anim.setDuration(400) # [Task] 400ms 淡出 + 400ms 淡入，接近一秒
        
        self._dragging = False
        self._drag_pos = None

        self.auto_clear_timer = QTimer(self)
        self.auto_clear_timer.setSingleShot(True)
        self.auto_clear_timer.setInterval(5000)
        self.auto_clear_timer.timeout.connect(self.clear_input)

        # 5秒自动循环播放动画定时器
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.setInterval(5000)
        self.idle_timer.timeout.connect(self._trigger_idle_anim)
        
        # 闲置文案循环
        self._idle_texts = [self.m_cfg.get_prompt("idle_zh"), "快捷键 Win+Ctrl", "欢迎使用中日说"]
        self._idle_text_index = 0

        self.apply_theme()
        self._update_size()

    def apply_theme(self, theme="Dark"):
        self.theme_mode = theme
        self.m_cfg.theme_mode = theme # [Fix] Sync config state immediately
        # [Fix] 保证至少 0.01 的不透明度以防止鼠标穿透
        opacity = max(0.01, getattr(self.m_cfg, 'window_opacity', 0.95))
        
        if theme == "Light":
            # 使用配置的透明度，底色为白
            bg = f"rgba(255, 255, 255, {opacity})"
            self._text_color = "#333333"
            self._placeholder_color = "rgba(0,0,0,0.4)"
        else:
            # 使用配置的透明度，底色为黑灰色
            bg = f"rgba(45, 45, 45, {opacity})"
            self._text_color = "rgba(255,255,255,0.5)"
            self._placeholder_color = "rgba(255,255,255,0.5)"
        
        r = int(12 * self.window_scale)
        self.container.setStyleSheet(f"""
            QFrame#asr_container {{
                background-color: {bg};
                border-radius: {r}px;
                border: none;
            }}
        """)
        
        
        btn_bg = QColor(0,0,0,40) if theme=="Light" else QColor(255,255,255,25)
        btn_icon = QColor(100,100,100) if theme=="Light" else QColor(200,200,200)
        

        
        self.waveform.bar_color = QColor(100, 100, 100) if theme == "Light" else QColor(200, 200, 200)
        
        self._update_display_style()

    def apply_scaling(self, scale, font_factor, is_serif=False):
        self.window_scale = scale
        self.m_cfg.window_scale = scale # [Fix] Sync config state
        self.font_size_factor = font_factor

        self.slot_label.apply_scale(scale, font_factor=font_factor)
        self._update_display_style()
        self._update_size()
        self.apply_theme(self.theme_mode) # Update border radius

    def change_theme(self, theme): self.apply_theme(theme)
    def set_font_name(self, name): 
        self.current_font_name = name
        self._update_display_style()
    def set_scale_factor(self, scale):
        self.apply_scaling(scale, self.font_size_factor)

    def _update_display_style(self):
        family = FontManager.get_correct_family(self.current_font_name)
        font_size = int(14 * self.font_size_factor)
        current_text = self.display.toPlainText()
        # Determine color based on content
        if not current_text:
            color = self._placeholder_color
            self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif current_text in self._idle_texts or current_text == self.m_cfg.get_prompt("listening"):
            color = self._placeholder_color
            self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            color = self._text_color
            self.display.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.display.set_text_color(color)
        self.display.apply_scale(self.window_scale, family, self.font_size_factor)
        
        # 老虎机强制使用占位符颜色
        self.slot_label.set_text_color(self._placeholder_color)
        self.slot_label.apply_scale(self.window_scale, family, self.font_size_factor)



    def _update_size(self):
        s = self.window_scale
        base_w = int(200 * s)
        if base_w < 100: base_w = 100 # 最小宽度保护
        base_h = int(53 * s) # [Task] 从 52 改为 53，使下边缘下移 1px
        
        # 1. 强制设定显示区域宽度，确保折行计算正确
        # Window width = base_w + 50 (margins 25*2)
        # Container width = Window width - 50 = base_w
        # Display width = Container width - 30 (margins 15*2)
        display_w = base_w - int(30 * s)
        self.display.setFixedWidth(display_w)
        
        # 2. 获取文档真实高度
        doc_h = self.display.document().size().height()
        
        # 3. 计算目标容器高度 (doc_h + 上下padding)
        # 上下留白给一点，避免贴边
        padding_v = int(25 * s) # [Task] 从 24 改为 25
        target_h = max(base_h, int(doc_h + padding_v))
        
        # 4. 限制最大高度
        target_h = min(target_h, int(800 * s))
        
        # 5. 设置窗口宽度
        window_w = base_w + int(50 * s)
        self.setFixedWidth(window_w)
        
        # 6. 高度动画 (改为 geometry 动画以锁定 Y 轴)
        current_h = self.container.height()
        target_win_h = target_h + 50 # Window height including shadow margins
        
        if abs(target_h - current_h) > 2:
            # [Fix] 如果窗口还没显示（初始化阶段），绝对不要启动动画
            # 否则动画会记录错误的 StartValue(0,0)，导致窗口出现后瞬间跳到左上角
            if not self.isVisible():
                self.resize(self.width(), target_win_h)
                self.container.setMinimumHeight(target_h)
                self.container.setMaximumHeight(target_h)
                # 同时也需要更新一下 geometry 的高度，虽然 resize 应该够了，但为了保险
                geo = self.geometry()
                geo.setHeight(target_win_h)
                self.setGeometry(geo)
                return

            # 动画前清理
            try: self.height_anim.finished.disconnect()
            except: pass
            self.height_anim.stop()
            
            # [Synchronization Fix] 动画前解锁所有高度约束
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.container.setMinimumHeight(0)
            self.container.setMaximumHeight(16777215)
            
            # 属性动画，Setter 会同步调整 window 和 container
            self.height_anim.setStartValue(current_h + 50)
            self.height_anim.setEndValue(target_win_h)
            
            def on_anim_finished():
                self.setMinimumHeight(target_win_h)
                self.setMaximumHeight(target_win_h)
                self.container.setMinimumHeight(target_h)
                self.container.setMaximumHeight(target_h)
                self.update() # 强制最后一次重绘，确保阴影归位
                
            self.height_anim.finished.connect(on_anim_finished)
            self.height_anim.start()
        else:
            # 直接应用
            target_geo = self.geometry()
            target_geo.setHeight(target_win_h)
            self.setGeometry(target_geo)
            
            self.setMinimumHeight(target_win_h)
            self.setMaximumHeight(target_win_h)
            self.container.setMinimumHeight(target_h)
            self.container.setMaximumHeight(target_h)

    def update_segment(self, text, animate=True):
        # 如果正在进行淡入淡出，且来了新文字，立即停止并恢复不透明度
        self.fade_anim.stop()
        self.content_opacity.setOpacity(1.0)

        # 如果正在进行动画，且现在有真正文本输入，强制停止动画
        if self.slot_label.isVisible():
            self.slot_label.setVisible(False)
            self.display.setVisible(True)
            
        self.display.setPlainText(text)
        self._update_display_style()
        self._update_size()
        
        if not text:
            # Empty text

            is_real_text = False
        else:
            # Check if text is one of the idle placeholders or listening prompt
            is_placeholder = text in self._idle_texts or text == self.m_cfg.get_prompt("listening")

            is_real_text = not is_placeholder
        
        if is_real_text:
            self.auto_clear_timer.start()
            self.idle_timer.stop()
        else:
            self.auto_clear_timer.stop()
            # 只有当内容是任意一个 idle_texts 时才启动循环
            if text in self._idle_texts:
                self.idle_timer.start()
            else:
                self.idle_timer.stop()


    def update_status(self, status):
        # [FIX] 如果正在录音，绝对不要更新文字状态/显示占位符
        if self.waveform.isVisible():
            return

        current = self.display.toPlainText()
        if status == "idle" or "加载完成" in status or "就绪" in status:
            if self.slot_label.isVisible():
                # 加载完毕，开始逐字归位
                self.slot_label.settle_one_by_one(start_delay=300)
            elif self.m_cfg.is_placeholder_text(current) and current not in self._idle_texts:
                # 只有当当前显示的是旧的占位符时，才重置
                self.update_segment(self.m_cfg.get_prompt("idle_zh"))
        elif "加载" in status or status == "loading" or status == "asr_loading":
            # [FIX] 如果当前已经有识别出的文本（非占位符），不要切换回 Loading 动画
            # 这防止了某些情况下 status 更新滞后导致的输入框消失
            is_real_text = current not in self._idle_texts and not self.m_cfg.is_placeholder_text(current)
            if is_real_text:
                return

            # 开启老虎机动画
            self.display.setVisible(False)
            self.slot_label.setVisible(True)
            self.slot_label.start_animation()
            self._update_display_style()
            
            if ASRManager().worker.engine.is_loaded:
                QTimer.singleShot(1000, self.slot_label.settle_one_by_one)

    def clear_input(self):
        # 用户希望有淡入淡出过渡 (约一秒)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        
        def on_fade_out():
            self.fade_anim.finished.disconnect()
            self.update_segment(self.m_cfg.get_prompt("idle_zh"), animate=False)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.start()
            
        self.fade_anim.finished.connect(on_fade_out)
        self.fade_anim.start()

    def focus_input(self):
        self.display.setFocus()

    def update_recording_status(self, is_recording):
        self.waveform.setVisible(is_recording)
        
        if is_recording:
            self.display.setVisible(False)
            self.slot_label.setVisible(False) # 确保占位符也被隐藏
            self.auto_clear_timer.stop()
            self.idle_timer.stop() # [Fix] 录音时强制停止轮播
            # 不需要设置 display 的文本，因为已经隐藏了
        else:
            # 录音结束，恢复显示
            # 逻辑：如果有识别文本，显示 display；如果没有，update_segment 会处理回退到占位符
            self.display.setVisible(True)
            current = self.display.toPlainText()
            if current == self.m_cfg.get_prompt("listening"): 
                self.update_segment("")
            elif current not in [self.m_cfg.get_prompt("idle_zh"), ""]: 
                self.auto_clear_timer.start()
            
            # 如果当前是空的，update_segment 会自动调用 update_status 把 slot_label 显示出来
            # 所以这里主要负责把 display 设为可见 (如果它包含真实文本)
            if not current or current in self._idle_texts:
                self.display.setVisible(False)
                self.slot_label.setVisible(True)

    def update_audio_level(self, level):
        if self.waveform.isVisible(): self.waveform.set_level(level)

    def _start_drag(self, global_pos):
        self._dragging = True
        self._drag_pos = global_pos - self.pos()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: 
            self._start_drag(e.globalPosition().toPoint())
    def mouseMoveEvent(self, e):
        # [Fix] 防粘连：如果移动时左键没按，强制停止拖动
        if not (e.buttons() & Qt.MouseButton.LeftButton):
            self._dragging = False
            
        if self._dragging and self._drag_pos: 
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e): 
        if self._dragging:
            self._dragging = False

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._start_drag(event.globalPosition().toPoint())
                if obj == self.display: return True
        elif event.type() == QEvent.Type.MouseMove:
            # [Fix] 防粘连保险丝
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._dragging = False
                return False
                
            if self._dragging:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton: 
                if self._dragging:
                    self._dragging = False
        return super().eventFilter(obj, event)

    def setVisible(self, visible):
        # 只有当从隐藏变为显示时，才标记需要重置位置
        if visible and not self.isVisible():
            self._should_reset_pos = True
        super().setVisible(visible)

    def showEvent(self, event):
        super().showEvent(event)
        self._dragging = False 
        
        # [Task] 只有在真正"打开"窗口时才重置位置
        # 这样可以避免在使用过程中因 resize 等原因导致的意外重置
        if getattr(self, '_should_reset_pos', False):
            self._should_reset_pos = False # 消费掉标记
            
            screen = QApplication.primaryScreen().geometry()
            
            # 计算居中位置
            # Y轴固定在屏幕上方 15% 处，或者固定 150px
            target_y = int(screen.height() * 0.15) 
            if target_y < 100: target_y = 100 # 最小高度
            
            # X轴居中
            win_w = self.width() if self.width() > 10 else 600
            if hasattr(self, 'frameGeometry'):
                win_w = self.frameGeometry().width()
                
            target_x = (screen.width() - win_w) // 2
            
            self.move(target_x, target_y)
        self.activateWindow()
        self.raise_()
        
        # 只要是占位符就执行动画
        # 只要是占位符就执行动画
        if self.m_cfg.is_placeholder_text(self.display.toPlainText()) or self.display.toPlainText() in self._idle_texts:
            self.update_status("asr_loading")

    def contextMenuEvent(self, event):
        self.show_context_menu(event.globalPos())

    def show_context_menu(self, global_pos):
        # 使用统一的新菜单
        from ui_manager import create_context_menu
        self.activateWindow()
        self.raise_()
        # 传入 self 作为 signals_proxy
        menu = create_context_menu(self, self.m_cfg, self)
        menu.exec(global_pos)

    def update_background_opacity(self, opacity):
        """更新背景透明度"""
        self.m_cfg.window_opacity = opacity
        self.apply_theme(self.theme_mode)

    def _on_animation_finished(self):
        self.slot_label.setVisible(False)
        self.display.setVisible(True)
        # 确保显示的文本是刚刚动画结束的那个文案
        if 0 <= self._idle_text_index < len(self._idle_texts):
            current_idle_text = self._idle_texts[self._idle_text_index]
            self.update_segment(current_idle_text)
        else:
            self.update_segment(self.m_cfg.get_prompt("idle_zh"))

    # [Synchronized Animation Property]
    def _get_anim_height(self): return self.height()
    def _set_anim_height(self, h):
        # h 是 Window 总高度
        self.resize(self.width(), h)
        # 强制同步 Container 高度 (Window - Shadow 25*2)
        # 使用 setFixedHeight 绕过布局系统的滞后，确保圆角背景始终撑满
        self.container.setFixedHeight(max(1, h - 50))
    anim_height = pyqtProperty(int, fget=_get_anim_height, fset=_set_anim_height)

    def _show_hotkey_dialog(self):
        asr = self.m_cfg.hotkey_asr
        toggle = self.m_cfg.hotkey_toggle_ui
        dlg = HotkeyDialog(self, asr, toggle)
        if dlg.exec():
            new_asr, new_toggle = dlg.get_values()
            if new_asr or new_toggle:
                self.requestHotkeyChange.emit(new_asr, new_toggle)

    def _trigger_idle_anim(self):
        """触发一次加载动画，用于循环效果"""
        # 只有当前还在显示 display 且内容是占位符时才触发
        current_text = self.display.toPlainText()
        if self.display.isVisible() and current_text in self._idle_texts:
            # 切换到下一句文案
            self._idle_text_index = (self._idle_text_index + 1) % len(self._idle_texts)
            next_text = self._idle_texts[self._idle_text_index]
            
            # 设置新文案并触发动画
            self.slot_label.set_target_text(next_text)
            self.update_status("asr_loading")
            
    def _on_animation_finished(self):
        # [Fix] 如果正在录音，动画结束后绝对不要显示 display
        if self.waveform.isVisible():
            return
            
        # 动画结束后，显示 display，并确保 display 的内容也是最新的那句文案
        # 这样下面的 update_segment 逻辑（检测是否为占位符）就能正确启动定时器
        current_idle_text = self._idle_texts[self._idle_text_index]
        self.display.setVisible(True)
        self.slot_label.setVisible(False)
        self.update_segment(current_idle_text)

    # [New] 新手引导相关方法
    def toggle_teaching_tip(self):
        """切换新手引导显示"""
        from ui_components import TeachingTip
        if hasattr(self, 'teaching_tip') and self.teaching_tip and self.teaching_tip.isVisible():
            self.teaching_tip.close()
            self.teaching_tip = None
        else:
            self.show_teaching_tip()

    def show_teaching_tip(self):
        """显示新手引导"""
        from ui_components import TeachingTip
        # 如果已存在，先关闭旧的
        if hasattr(self, 'teaching_tip') and self.teaching_tip:
            try: self.teaching_tip.close()
            except: pass
            
        self.teaching_tip = TeachingTip(None) # Parent None to be independent top-level
        self.teaching_tip.show_beside(self)
        
        # 窗口关闭时清理引用
        self.teaching_tip.destroyed.connect(lambda: setattr(self, 'teaching_tip', None))
