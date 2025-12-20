import os
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon

class TraySignals(QObject):
    restartRequested = pyqtSignal()
    modeChanged = pyqtSignal(str)
    quitRequested = pyqtSignal()

class AppTrayIcon(QSystemTrayIcon):
    def __init__(self, parent=None):
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        super().__init__(QIcon(logo_path), parent)
        self.signals = TraySignals()
        self.setToolTip("AI 实时翻译助手")
        self._init_menu()

    def _init_menu(self):
        menu = QMenu()
        
        mode_menu = menu.addMenu("应用模式")
        self.mode_actions = {}
        for m_id, m_name in [("asr", "语音输入"), ("asr_jp", "日语语音"), ("translation", "文字翻译")]:
            action = mode_menu.addAction(m_name)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, mid=m_id: self.signals.modeChanged.emit(mid))
            self.mode_actions[m_id] = action

        menu.addSeparator()
        menu.addAction("重启应用").triggered.connect(self.signals.restartRequested.emit)
        menu.addAction("退出程序").triggered.connect(self.signals.quitRequested.emit)
        
        self.setContextMenu(menu)

    def set_mode_checked(self, mode_id):
        for mid, action in self.mode_actions.items():
            action.setChecked(mid == mode_id)
        self.show()
