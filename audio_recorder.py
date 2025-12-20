import pyaudio
import numpy as np
import wave
import io
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

class AudioRecorder(QObject):
    started = pyqtSignal()
    stopped = pyqtSignal()
    audio_ready = pyqtSignal(np.ndarray)
    level_updated = pyqtSignal(float) # For UI feedback

    def __init__(self, rate=16000, chunk=1024):
        super().__init__()
        self.rate = rate
        self.chunk = chunk
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.frames = []
        self.is_recording = False
        
        # Level monitoring timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._check_level)

    def start_recording(self):
        if self.is_recording: return
        
        self.frames = []
        try:
            self.stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk,
                stream_callback=self._callback
            )
            self.is_recording = True
            self.started.emit()
            self.timer.start(100)
            print("[AudioRecorder] Recording started.")
        except Exception as e:
            print(f"[AudioRecorder] Failed to start recording: {e}")

    def stop_recording(self):
        if not self.is_recording: return
        
        self.is_recording = False
        self.timer.stop()
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        self.stopped.emit()
        print("[AudioRecorder] Recording stopped.")
        
        if self.frames:
            # Convert to numpy array for FunASR
            audio_data = np.frombuffer(b''.join(self.frames), dtype=np.int16)
            # Float32 normalization if needed by some models, but FunASR AutoModel often handles int16
            # SenseVoiceSmall via FunASR usually likes float32 or int16. 
            # Let's provide float32 for better compatibility.
            audio_float = audio_data.astype(np.float32) / 32768.0
            self.audio_ready.emit(audio_float)

    def _callback(self, in_data, frame_count, time_info, status):
        if self.is_recording:
            self.frames.append(in_data)
        return (in_data, pyaudio.paContinue)

    def _check_level(self):
        if not self.frames: return
        # Calculate RMS level of the last chunk for UI feedback
        last_chunk = np.frombuffer(self.frames[-1], dtype=np.int16)
        rms = np.sqrt(np.mean(last_chunk.astype(np.float64)**2))
        self.level_updated.emit(float(rms))

    def cleanup(self):
        self.p.terminate()
