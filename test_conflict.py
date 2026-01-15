
import sys
import time
import threading
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

print("Importing modules...")
try:
    import audio_recorder
    import tts_worker
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

def run_test():
    print("Initializing AudioRecorder...")
    rec = audio_recorder.AudioRecorder()
    
    print("Starting Recording (1s)...")
    rec.start_recording()
    time.sleep(1.0)
    
    print("Stopping Recording...")
    rec.stop_recording()
    
    # Simulate processing time
    time.sleep(0.5)
    
    print("Starting TTS Thread...")
    def tts_task():
        print("TTS Thread started.")
        try:
            tts_worker.say("テスト、一、二、三。")
        except Exception as e:
            print(f"TTS Thread Exception: {e}")
            import traceback
            traceback.print_exc()
        print("TTS Thread finished.")

    t = threading.Thread(target=tts_task)
    t.start()
    t.join()
    print("Test Complete.")

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv) # AudioRecorder uses QObject/QTimer
    
    # Run test in a timer to let event loop start
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1000, run_test)
    
    # Quit after some time
    QTimer.singleShot(8000, app.quit)
    
    app.exec()
