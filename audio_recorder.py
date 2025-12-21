import sounddevice as sd
import numpy as np
import io
import threading
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

class AudioRecorder(QObject):
    started = pyqtSignal()
    stopped = pyqtSignal()
    audio_ready = pyqtSignal(np.ndarray)
    level_updated = pyqtSignal(float)

    def __init__(self, rate=16000, chunk=1024):
        super().__init__()
        self.rate = rate
        self.chunk = chunk
        self.is_recording = False
        self.frames = []
        self._lock = threading.Lock()
        
        # Level monitoring timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._check_level)
        self.last_chunk = np.zeros(chunk, dtype=np.int16)

    def start_recording(self):
        if self.is_recording: return
        
        with self._lock:
            self.frames = []
            self.is_recording = True
            
        try:
            # Use sounddevice's rec() which is high-level and handles device opening/closing well
            # However, for hold-to-talk, an InputStream is better
            self.stream = sd.InputStream(
                samplerate=self.rate,
                channels=1,
                dtype='int16',
                blocksize=self.chunk,
                callback=self._callback
            )
            self.stream.start()
            self.started.emit()
            self.timer.start(100)
            print("[AudioRecorder] sd.InputStream started.")
        except Exception as e:
            self.is_recording = False
            print(f"[AudioRecorder] Failed to start: {e}")

    def stop_recording(self):
        if not self.is_recording: return
        
        with self._lock:
            self.is_recording = False
        
        self.timer.stop()
        
        if hasattr(self, 'stream') and self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            except: pass
        
        # Explicitly release any sounddevice resources
        # This helps in Windows to drop the HFP handle immediately
        import gc
        gc.collect()
            
        self.stopped.emit()
        print("[AudioRecorder] sd.InputStream stopped and released.")
        
        if self.frames:
            audio_data = np.concatenate(self.frames, axis=0)
            # Normalization to float32 for FunASR/SenseVoice
            audio_float = audio_data.flatten().astype(np.float32) / 32768.0
            self.audio_ready.emit(audio_float)

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"[AudioRecorder] Stream status: {status}")
        with self._lock:
            if self.is_recording:
                self.frames.append(indata.copy())
                self.last_chunk = indata.flatten()

    def _check_level(self):
        # Calculate RMS level for UI
        rms = np.sqrt(np.mean(self.last_chunk.astype(np.float64)**2))
        self.level_updated.emit(float(rms))

    def cleanup(self):
        pass # sounddevice handles itself well
