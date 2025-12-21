import os
from PyQt6.QtWidgets import QSystemTrayIcon
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon

class TraySignals(QObject):
    restartRequested = pyqtSignal()
    openSettingsRequested = pyqtSignal()
    modeChanged = pyqtSignal(str)
    quitRequested = pyqtSignal()

class AppTrayIcon(QSystemTrayIcon):
    def __init__(self, parent=None):
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        super().__init__(QIcon(logo_path), parent)
        self.signals = TraySignals() # Keep for compatibility if needed, though mostly unused now
        self.setToolTip("AI 实时翻译助手")
        self.show()

    def set_mode_checked(self, mode_id):
        # This method is now a no-op as the checkmarks are handled in the window context menus
        # but we keep it to avoid crashing main.py
        pass
