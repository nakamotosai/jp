import sys
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from ui_components import TeachingTip

def main():
    app = QApplication(sys.argv)

    # Serialize fonts/config by init main components if needed, 
    # but TeachingTip is self contained enough generally.
    
    # Create a dummy window to anchor the tip
    # Using dark background to match the 'dark minimalist' vibe request
    w = QWidget()
    w.setWindowTitle("Visual Preview - Teaching Tip")
    w.setStyleSheet("background-color: #333333;") 
    w.resize(400, 200)
    w.move(500, 400) # Center-ish

    layout = QVBoxLayout(w)
    btn = QPushButton("Main App Window (Anchor)")
    btn.setStyleSheet("color: white; border: 1px solid #666; padding: 20px; background: #222;")
    layout.addWidget(btn)

    w.show()

    # Show the tip
    tip = TeachingTip()
    
    # Delayed show to ensure window geometry is ready
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(500, lambda: tip.show_beside(w))

    print("Preview running...")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
