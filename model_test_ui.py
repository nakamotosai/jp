"""
模型测试UI - 用于测试和选择ASR/翻译模型组合
支持:
- 2个ASR引擎选择
- 3个翻译引擎选择
- ASR输出模式切换 (Raw/Cleaned)
- 实时显示结果
"""

import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QButtonGroup, QPushButton, QTextEdit, QLabel,
    QFrame, QSizePolicy, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette

from model_config import (
    get_model_config,
    ASREngineType,
    ASROutputMode,
    TranslatorEngineType
)
from asr_manager import ASRManager
from translator_engine import TranslatorEngine
from audio_recorder import AudioRecorder


class ModelTestUI(QWidget):
    """模型测试界面"""
    
    def __init__(self):
        super().__init__()
        self.config = get_model_config()
        
        # 初始化引擎
        self.asr_manager = ASRManager()
        self.translator = TranslatorEngine()
        self.translator.set_mode("local")
        
        # 音频录制
        self.recorder = AudioRecorder()
        self.is_recording = False
        
        self._init_ui()
        self._connect_signals()
        
        # 打印当前状态
        self.config.print_status()
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("模型测试工具")
        self.setMinimumSize(500, 600)
        self.setStyleSheet("""
            QWidget {
                font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ccc;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                background-color: #4a90d9;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2a5f8f;
            }
            QPushButton:disabled {
                background-color: #aaa;
            }
            QPushButton#recordBtn {
                background-color: #e74c3c;
            }
            QPushButton#recordBtn:hover {
                background-color: #c0392b;
            }
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 8px;
                background-color: #ffffff;
                color: #000000;
                font-size: 14px;
                min-height: 60px;
            }
            QRadioButton {
                spacing: 8px;
                padding: 4px;
            }
            QLabel#statusLabel {
                color: #666;
                font-style: italic;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # === ASR引擎选择 ===
        asr_group = QGroupBox("🎤 ASR引擎选择")
        asr_layout = QVBoxLayout(asr_group)
        
        self.asr_button_group = QButtonGroup(self)
        
        for engine_type in ASREngineType:
            model_info = self.config.ASR_MODELS.get(engine_type.value)
            if model_info:
                radio = QRadioButton(model_info.name)
                radio.setProperty("engine_type", engine_type.value)
                radio.setEnabled(model_info.available)
                if not model_info.available:
                    radio.setText(f"{model_info.name} (不可用)")
                if engine_type.value == self.config.current_asr_engine:
                    radio.setChecked(True)
                self.asr_button_group.addButton(radio)
                asr_layout.addWidget(radio)
        
        layout.addWidget(asr_group)
        
        # === ASR输出模式 ===
        mode_group = QGroupBox("📝 ASR输出模式")
        mode_layout = QHBoxLayout(mode_group)
        
        self.mode_button_group = QButtonGroup(self)
        
        self.raw_radio = QRadioButton("Raw (原始输出)")
        self.raw_radio.setProperty("mode", ASROutputMode.RAW.value)
        self.cleaned_radio = QRadioButton("Cleaned (清理后)")
        self.cleaned_radio.setProperty("mode", ASROutputMode.CLEANED.value)
        
        if self.config.asr_output_mode == ASROutputMode.RAW.value:
            self.raw_radio.setChecked(True)
        else:
            self.cleaned_radio.setChecked(True)
        
        self.mode_button_group.addButton(self.raw_radio)
        self.mode_button_group.addButton(self.cleaned_radio)
        mode_layout.addWidget(self.raw_radio)
        mode_layout.addWidget(self.cleaned_radio)
        
        layout.addWidget(mode_group)
        
        # === 翻译引擎选择 ===
        trans_group = QGroupBox("🌐 翻译引擎选择")
        trans_layout = QVBoxLayout(trans_group)
        
        self.trans_button_group = QButtonGroup(self)
        
        for engine_type in TranslatorEngineType:
            model_info = self.config.TRANSLATOR_MODELS.get(engine_type.value)
            if model_info:
                radio = QRadioButton(model_info.name)
                radio.setProperty("engine_type", engine_type.value)
                radio.setEnabled(model_info.available)
                if not model_info.available:
                    radio.setText(f"{model_info.name} (不可用)")
                if engine_type.value == self.config.current_translator_engine:
                    radio.setChecked(True)
                self.trans_button_group.addButton(radio)
                trans_layout.addWidget(radio)
        
        layout.addWidget(trans_group)
        
        # === 控制按钮 ===
        btn_layout = QHBoxLayout()
        
        self.record_btn = QPushButton("🎙️ 开始录音")
        self.record_btn.setObjectName("recordBtn")
        self.record_btn.setMinimumHeight(40)
        
        self.apply_btn = QPushButton("🔄 应用模型设置")
        self.apply_btn.setMinimumHeight(40)
        
        btn_layout.addWidget(self.record_btn)
        btn_layout.addWidget(self.apply_btn)
        
        layout.addLayout(btn_layout)
        
        # === 结果显示 ===
        result_group = QGroupBox("📊 结果")
        result_layout = QVBoxLayout(result_group)
        
        # ASR结果
        asr_label = QLabel("ASR识别结果：")
        self.asr_result = QTextEdit()
        self.asr_result.setReadOnly(True)
        self.asr_result.setMaximumHeight(150)
        self.asr_result.setPlaceholderText("按住录音按钮说话...")
        
        result_layout.addWidget(asr_label)
        result_layout.addWidget(self.asr_result)
        
        # 翻译结果
        trans_label = QLabel("翻译结果：")
        self.trans_result = QTextEdit()
        self.trans_result.setReadOnly(True)
        self.trans_result.setMaximumHeight(150)
        self.trans_result.setPlaceholderText("等待ASR结果...")
        
        result_layout.addWidget(trans_label)
        result_layout.addWidget(self.trans_result)
        
        layout.addWidget(result_group)
        
        # === 状态栏 ===
        self.status_label = QLabel("状态：就绪")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        
        # === 弹簧 ===
        layout.addStretch()
    
    def _connect_signals(self):
        """连接信号"""
        # ASR引擎切换
        self.asr_button_group.buttonClicked.connect(self._on_asr_engine_changed)
        
        # ASR模式切换
        self.mode_button_group.buttonClicked.connect(self._on_asr_mode_changed)
        
        # 翻译引擎切换
        self.trans_button_group.buttonClicked.connect(self._on_trans_engine_changed)
        
        # 录音按钮
        self.record_btn.pressed.connect(self._start_recording)
        self.record_btn.released.connect(self._stop_recording)
        
        # 应用设置
        self.apply_btn.clicked.connect(self._apply_settings)
        
        # ASR管理器信号
        self.asr_manager.result_ready.connect(self._on_asr_result)
        self.asr_manager.status_changed.connect(self._on_status_changed)
        self.asr_manager.error.connect(self._on_error)
        self.asr_manager.model_ready.connect(lambda: self._on_status_changed("ASR模型就绪"))
        
        # 翻译引擎信号
        self.translator.status_changed.connect(self._on_status_changed)
        
        # 录音器信号
        self.recorder.audio_ready.connect(self._on_audio_ready)
    
    def _on_asr_engine_changed(self, button):
        """ASR引擎变更"""
        engine_type = button.property("engine_type")
        if engine_type:
            self._on_status_changed(f"ASR引擎将切换为: {engine_type}")
    
    def _on_asr_mode_changed(self, button):
        """ASR模式变更"""
        mode = button.property("mode")
        if mode:
            self.asr_manager.set_output_mode(mode)
            self._on_status_changed(f"ASR输出模式: {mode}")
    
    def _on_trans_engine_changed(self, button):
        """翻译引擎变更"""
        engine_type = button.property("engine_type")
        if engine_type:
            self._on_status_changed(f"翻译引擎将切换为: {engine_type}")
    
    def _apply_settings(self):
        """应用模型设置"""
        # 获取选中的ASR引擎
        asr_btn = self.asr_button_group.checkedButton()
        if asr_btn:
            engine_type = asr_btn.property("engine_type")
            if engine_type and engine_type != self.config.current_asr_engine:
                self.asr_manager.switch_engine(engine_type)
        
        # 获取选中的翻译引擎
        trans_btn = self.trans_button_group.checkedButton()
        if trans_btn:
            engine_type = trans_btn.property("engine_type")
            if engine_type and engine_type != self.config.current_translator_engine:
                self.translator.switch_engine(engine_type)
        
        self._on_status_changed("设置已应用")
    
    def _start_recording(self):
        """开始录音"""
        self.is_recording = True
        self.record_btn.setText("🔴 录音中...")
        self.recorder.start_recording()
        self._on_status_changed("正在录音...")
    
    def _stop_recording(self):
        """停止录音"""
        self.is_recording = False
        self.record_btn.setText("🎙️ 开始录音")
        self.recorder.stop_recording()
        self._on_status_changed("正在处理...")
    
    def _on_audio_ready(self, audio_data):
        """音频就绪，开始ASR"""
        try:
            print(f"[ModelTestUI] 音频数据就绪，长度: {len(audio_data)}")
            self.asr_manager.transcribe_async(audio_data)
        except Exception as e:
            import traceback
            print(f"[ModelTestUI] _on_audio_ready 错误: {e}")
            traceback.print_exc()
            self._on_error(str(e))
    
    def _on_asr_result(self, text: str):
        """ASR结果返回"""
        try:
            print(f"[ModelTestUI] ASR结果: {text[:50] if len(text) > 50 else text}")
            self.asr_result.setPlainText(text)
            self.asr_result.repaint()
            QApplication.processEvents()
            self._on_status_changed("ASR完成，正在翻译...")
            
            # 自动翻译
            if text:
                print("[ModelTestUI] 开始翻译...")
                translated = self.translator.translate(text)
                print(f"[ModelTestUI] 翻译结果: {translated[:50] if len(translated) > 50 else translated}")
                self.trans_result.setPlainText(translated)
                self.trans_result.repaint()
                QApplication.processEvents()
                self._on_status_changed("翻译完成")
        except Exception as e:
            import traceback
            print(f"[ModelTestUI] _on_asr_result 错误: {e}")
            traceback.print_exc()
            self._on_error(str(e))
    
    def _on_status_changed(self, status: str):
        """状态变更"""
        print(f"[ModelTestUI] 状态: {status}")
        self.status_label.setText(f"状态：{status}")
    
    def _on_error(self, error: str):
        """错误处理"""
        print(f"[ModelTestUI] 错误: {error}")
        self.status_label.setText(f"错误：{error}")
        self.status_label.setStyleSheet("color: red;")
    
    def closeEvent(self, event):
        """关闭事件"""
        try:
            print("[ModelTestUI] 正在清理资源...")
            self.asr_manager.cleanup()
            self.translator.cleanup()
            print("[ModelTestUI] 资源清理完成")
        except Exception as e:
            print(f"[ModelTestUI] 清理时错误: {e}")
        event.accept()


def main():
    """主函数"""
    import multiprocessing
    multiprocessing.freeze_support()
    
    # 添加全局异常处理
    import sys
    def exception_hook(exctype, value, tb):
        import traceback
        print("=" * 50)
        print("[FATAL] 未捕获的异常:")
        traceback.print_exception(exctype, value, tb)
        print("=" * 50)
        sys.__excepthook__(exctype, value, tb)
    
    sys.excepthook = exception_hook
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = ModelTestUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

