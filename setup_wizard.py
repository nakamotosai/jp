"""
首次启动向导
引导用户下载必要模型并进行基本设置
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QStackedWidget, QFrame, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap

from model_config import get_model_config, ASREngineType
from model_downloader import get_downloader
from ui_components import ModelOptionWidget

class SetupWizard(QDialog):
    """首次启动向导窗口"""
    
    def __init__(self):
        super().__init__()
        self.m_cfg = get_model_config()
        self.downloader = get_downloader()
        self._setup_ui()
        
    def _setup_ui(self):
        self.setWindowTitle("AI 日语输入法 - 初始化向导")
        self.setFixedSize(600, 500)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.CustomizeWindowHint)
        
        # 样式 (深色主题)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #cccccc; }
            QLabel { color: #cccccc; font-size: 14px; }
            h1 { font-size: 24px; font-weight: bold; color: white; margin-bottom: 10px; }
            p { color: #aaaaaa; line-height: 1.4; }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 14px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled { background-color: #3d3d3d; color: #666666; }
            QPushButton#secondary { background-color: #3d3d3d; border: 1px solid #555555; }
            QPushButton#secondary:hover { background-color: #4d4d4d; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 顶部图片或Banner (可选)
        
        # 内容区域 (堆叠窗口)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        
        # 底部导航栏
        nav_bar = QFrame()
        nav_bar.setStyleSheet("background-color: #252526; border-top: 1px solid #3d3d3d;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(20, 15, 20, 15)
        
        self.btn_back = QPushButton("上一步")
        self.btn_back.setObjectName("secondary")
        self.btn_back.clicked.connect(self._prev_page)
        
        self.page_indicator = QLabel("1/3")
        self.page_indicator.setStyleSheet("color: #666666;")
        
        self.btn_next = QPushButton("下一步")
        self.btn_next.clicked.connect(self._next_page)
        
        nav_layout.addWidget(self.btn_back)
        nav_layout.addStretch()
        nav_layout.addWidget(self.page_indicator)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_next)
        
        layout.addWidget(nav_bar)
        
        # 添加页面
        self._init_page_welcome()
        self._init_page_models()
        self._init_page_finish()
        
        self._update_nav_state()

    def _init_page_welcome(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        title = QLabel("欢迎使用 AI 日语输入法")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white; margin-bottom: 20px;")
        
        desc = QLabel(
            "这是一款基于 AI 的日语语音输入与实时翻译工具。\n\n"
            "在开始之前，我们需要下载一些必要的 AI 模型组件。\n"
            "这些模型将运行在您的本地电脑上，确保隐私安全和低延迟。\n\n"
            "请点击“下一步”继续。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 15px; color: #cccccc; line-height: 1.6;")
        
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        page.setLayout(layout)
        self.pages.addWidget(page)

    def _init_page_models(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)
        
        title = QLabel("下载核心组件")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        layout.addWidget(title)
        
        desc = QLabel("以下模型是程序运行所必须的，请确保下载安装完成。")
        layout.addWidget(desc)
        
        layout.addSpacing(20)
        
        # SenseVoice 模型
        self.asr_model = ModelOptionWidget(
            ASREngineType.SENSEVOICE_ONNX.value, 
            "SenseVoice 语音识别模型 (必需)", 
            "高性能多语言识别模型 (约156MB)"
        )
        # 禁用取消选中，因为是必需的
        self.asr_model.btn.setCheckable(False)
        self.asr_model.update_theme(False) # Dark mode
        # 监听状态变化以启用/禁用下一步按钮
        self.asr_model.selected.connect(self._check_model_ready)
        
        layout.addWidget(self.asr_model)
        
        layout.addStretch()
        
        # 提示
        hint = QLabel("提示: 如果下载速度较慢，请检查网络连接。支持断点续传。")
        hint.setStyleSheet("color: #666666; font-style: italic; font-size: 12px;")
        layout.addWidget(hint)
        
        page.setLayout(layout)
        self.pages.addWidget(page)

    def _init_page_finish(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        title = QLabel("准备就绪")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: white; margin-bottom: 20px;")
        
        desc = QLabel(
            "初始设置已完成！\n\n"
            "您可以通过托盘图标右键菜单进入「详细设置」调整更多选项，\n"
            "如更换翻译模型、修改快捷键或界面主题。\n\n"
            "默认快捷键：\n"
            "• 语音输入: Ctrl + Win (按住说话)\n"
            "• 显示/隐藏: Alt + Win"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 15px; color: #cccccc; line-height: 1.6;")
        
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        page.setLayout(layout)
        self.pages.addWidget(page)

    def _update_nav_state(self):
        idx = self.pages.currentIndex()
        count = self.pages.count()
        
        self.page_indicator.setText(f"{idx + 1}/{count}")
        
        self.btn_back.setEnabled(idx > 0)
        self.btn_back.setVisible(idx > 0)
        
        if idx == count - 1:
            self.btn_next.setText("开始使用")
        else:
            self.btn_next.setText("下一步")
            
        # 特定页面的逻辑
        if idx == 1: # Model page
            self._check_model_ready()
        else:
            self.btn_next.setEnabled(True)

    def _check_model_ready(self):
        # 检查必需模型是否已安装
        is_ready = self.downloader.is_model_installed("sensevoice_onnx")
        self.btn_next.setEnabled(is_ready)
        
        # 如果未安装，自动触发显示下载状态（不需要自动开始下载，让用户点击更好，或者自动检测）
        # ModelOptionWidget 内部会处理显示

    def _next_page(self):
        idx = self.pages.currentIndex()
        if idx < self.pages.count() - 1:
            self.pages.setCurrentIndex(idx + 1)
            self._update_nav_state()
        else:
            self.accept() # 完成

    def _prev_page(self):
        idx = self.pages.currentIndex()
        if idx > 0:
            self.pages.setCurrentIndex(idx - 1)
            self._update_nav_state()
