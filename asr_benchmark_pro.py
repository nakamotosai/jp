import sys
import time
import threading
import numpy as np
import pyaudio
import os
import gc
import psutil
import keyboard
import torch
import re
from funasr import AutoModel

# --- Configuration ---
MODEL_PATHS = {
    "SenseVoice": r"C:\Users\sai\jp\models\SenseVoiceSmall",
    "Nano": r"C:\Users\sai\jp\models\Fun-ASR-Nano",
    "Paraformer": r"C:\Users\sai\jp\models\speech_paraformer"
}

OFFICIAL_MODEL_IDS = {
    "SenseVoice": "iic/SenseVoiceSmall",
    "Nano": "FunAudioLLM/Fun-ASR-Nano-2512",
    "Paraformer": "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"
}

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QFrame, QGraphicsDropShadowEffect, QProgressBar, QPushButton,
    QCheckBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, pyqtSlot, QTimer, pyqtProperty, QPropertyAnimation, QEasingCurve, QMetaObject, Q_ARG
from PyQt6.QtGui import QColor, QFont, QPainter, QLinearGradient, QBrush, QPen

# --- Style Constants ---
COLOR_ACCENT = "#7C4DFF"
COLOR_SENSE = "#00E5FF"
COLOR_NANO = "#00E676"
COLOR_PARA = "#FFD600"
COLOR_BG_DARK = "rgba(18, 18, 18, 0.95)"
COLOR_CARD = "rgba(45, 45, 45, 0.7)"

# --- Backend Workers ---

class ASRWorker(QObject):
    unified_signal = pyqtSignal(tuple) 

    def __init__(self, model_id, path):
        super().__init__()
        self.model_id = model_id
        self.path = path
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_ready = False

    def log_status(self, msg):
        self.unified_signal.emit((self.model_id, "status", msg))

    @pyqtSlot()
    def load(self):
        try:
            self.log_status("Initializing...")
            target_path = self.path
            if not os.path.exists(target_path):
                target_path = OFFICIAL_MODEL_IDS[self.model_id]
            
            print(f"[Worker-{self.model_id}] Loading from: {target_path}")
            
            # FIX: Manually import model.py via sys.path to force registration
            if self.model_id == "Nano":
                print(f"[Worker-{self.model_id}] Checking for local model.py to register class...")
                model_py_path = os.path.join(target_path, "model.py")
                if os.path.exists(model_py_path):
                    try:
                        import sys
                        if target_path not in sys.path:
                            sys.path.insert(0, target_path)
                        
                        # Force import or reload
                        if "model" in sys.modules:
                            import importlib
                            importlib.reload(sys.modules["model"])
                        else:
                            import model
                            
                        print(f"[Worker-{self.model_id}] 'model' module imported successfully. Class registered.")
                    except Exception as e:
                        print(f"[Worker-{self.model_id}] Manual import via sys.path failed: {e}")
                    finally:
                         if target_path in sys.path:
                             sys.path.remove(target_path)
                
                # Now load with AutoModel. We don't need remote_code argument if class is registered.
                # But we keep trust_remote_code=True just in case.
                # Optimization: Enable fp16 to speed up the Qwen-0.6B LLM backend
                self.model = AutoModel(
                    model=target_path, 
                    device=self.device, 
                    disable_update=True,
                    trust_remote_code=True,
                    fp16=True 
                )
            else:
                self.model = AutoModel(model=target_path, device=self.device, disable_update=True)
                
            self.is_ready = True
            self.log_status("Ready")
            print(f"[Worker-{self.model_id}] Load Success!")
        except Exception as e:
            print(f"[Worker-{self.model_id}] Load Error: {str(e)}")
            self.log_status(f"Error: {str(e)}")

    @pyqtSlot()
    def unload(self):
        self.model = None
        self.is_ready = False
        self.log_status("Unloaded")
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    @pyqtSlot(object)
    def process_full(self, audio_data):
        if not self.is_ready: return
        start_t = time.time()
        try:
            # Common params
            kwargs = {"use_itn": True}
            if self.model_id == "SenseVoice":
                kwargs["language"] = "zh" # SenseVoice requires language or auto
            
            # FIX: Nano's model.py strictly expects a list of Tensors or Paths
            # It blindly iterates input and checks isinstance(x, torch.Tensor)
            input_val = audio_data
            if self.model_id == "Nano":
                # Convert numpy -> tensor and wrap in list
                if isinstance(audio_data, np.ndarray):
                    tensor = torch.from_numpy(audio_data).to(self.device)
                    # If fp16 is enabled, the model weights are Half, so input must be Half
                    if hasattr(self.model.model, "llm_dtype") and self.model.model.llm_dtype in ["fp16", "half"]:
                        tensor = tensor.half()
                    elif str(next(self.model.model.parameters()).dtype).endswith('half'):
                         tensor = tensor.half()
                    input_val = [tensor]
                elif isinstance(audio_data, list):
                    pass # Assume correct
                else:
                    # Fallback if somehow just a tensor
                    input_val = [audio_data.to(self.device)]
            
            res = self.model.generate(input=input_val, **kwargs)
            latency = (time.time() - start_t) * 1000
            text = res[0].get('text', '')
            
            if self.model_id == "SenseVoice":
                tags = re.findall(r'<\|(.*?)\|>', text)
                emotion = "NEUTRAL"
                for t in tags:
                    if t.upper() in ["HAPPY", "SAD", "ANGRY", "NEUTRAL", "FEAR", "SURPRISED"]:
                        emotion = t.upper()
                self.unified_signal.emit((self.model_id, "emotion", emotion))
            
            clean_text = re.sub(r'<\|.*?\|>', '', text).strip()
            self.unified_signal.emit((self.model_id, "result", clean_text, latency))
            gc.collect()
        except Exception as e:
            self.log_status(f"Inference Error: {e}")

class ParaformerWorker(QObject):
    unified_signal = pyqtSignal(tuple)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.model = None
        self.cache = {}
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_ready = False

    def log_status(self, msg):
        self.unified_signal.emit(("status", msg))

    @pyqtSlot()
    def load(self):
        try:
            self.log_status("Initializing Online...")
            target_path = self.path
            if not os.path.exists(target_path):
                target_path = OFFICIAL_MODEL_IDS["Paraformer"]
            
            # Paraformer Online initialization
            self.model = AutoModel(
                model=target_path, 
                device=self.device, 
                disable_update=True,
                online=True 
            )
            # Force Paraformer to Float32 to avoid BF16/FP32 mismatch during streaming
            if hasattr(self.model, "model") and hasattr(self.model.model, "to"):
                self.model.model.to(torch.float32)
            self.is_ready = True
            self.log_status("Ready (Online)")
            print(f"[Paraformer] Online model loaded from {target_path}")
        except Exception as e:
            self.log_status(f"Error: {e}")

    @pyqtSlot()
    def unload(self):
        self.model = None
        self.is_ready = False
        self.cache = {}
        self.log_status("Unloaded")
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    @pyqtSlot(object)
    def process_chunk(self, chunk):
        if not self.is_ready: return
        try:
            # Explicitly convert to Float32 Tensor to avoid dtype mismatch
            input_tensor = torch.from_numpy(chunk).to(self.device).float()
            
            res = self.model.generate(
                input=input_tensor, 
                cache=self.cache, 
                is_final=False, 
                chunk_size=[0, 10, 5],
                encoder_chunk_look_back=4,
                decoder_chunk_look_back=1
            )
            if res:
                text = res[0].get('text', '')
                if text:
                    self.unified_signal.emit(("result", text))
        except Exception as e:
            print(f"[Paraformer] Chunk Error: {e}")

    @pyqtSlot()
    def finalize(self):
        if not self.is_ready: return
        try:
            # Passing input=None to finalize the decode
            # If this produces a TypeError in some funasr versions, we catch it.
            # Some versions prefer a small silent chunk instead of None.
            res = self.model.generate(
                input=None, 
                cache=self.cache, 
                is_final=True, 
                chunk_size=[0, 10, 5],
                encoder_chunk_look_back=4,
                decoder_chunk_look_back=1
            )
            if res:
                text = res[0].get('text', '')
                if text:
                    self.unified_signal.emit(("result", text))
            self.cache = {} 
        except Exception as e:
            print(f"[Paraformer] Finalize with None failed ({e}), trying silent chunk...")
            try:
                # Fallback: send a 10ms silent chunk as Float32 Tensor
                silent_chunk = torch.zeros(160, device=self.device).float()
                res = self.model.generate(
                    input=silent_chunk, 
                    cache=self.cache, 
                    is_final=True, 
                    chunk_size=[0, 10, 5],
                    encoder_chunk_look_back=4,
                    decoder_chunk_look_back=1
                )
                if res:
                    text = res[0].get('text', '')
                    if text: self.unified_signal.emit(("result", text))
            except Exception as e2:
                print(f"[Paraformer] Finalize Error: {e2}")
            self.cache = {} 

    @pyqtSlot()
    def reset_cache(self):
        self.cache = {}

# --- UI Components ---
class StatusCard(QFrame):
    def __init__(self, name, accent_color, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.title_label = QLabel(name); self.title_label.setStyleSheet(f"color: {accent_color}; font-size: 18px; font-weight: bold;")
        self.layout.addWidget(self.title_label)
        self.status_label = QLabel("Idle"); self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        self.layout.addWidget(self.status_label)
        self.text_area = QLabel("Waiting..."); self.text_area.setWordWrap(True); self.text_area.setStyleSheet("color: white; font-size: 14px; min-height: 100px;")
        self.text_area.setAlignment(Qt.AlignmentFlag.AlignTop); self.layout.addWidget(self.text_area)
        self.meta_label = QLabel(""); self.meta_label.setStyleSheet("color: #999; font-size: 11px;"); self.layout.addWidget(self.meta_label)
        self.setStyleSheet(f"QFrame#card {{ background: {COLOR_CARD}; border-radius: 20px; border: 1px solid rgba(255,255,255,0.05); }}")
    def set_status(self, text): self.status_label.setText(text)
    def set_text(self, text): self.text_area.setText(text)
    def set_meta(self, text): self.meta_label.setText(text)

class ASRBenchmarkPro(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(900, 680)
        self.init_layout(); self.init_workers(); self.init_audio(); self.init_hotkey()
        self.para_text = ""

    def init_layout(self):
        self.main_layout = QVBoxLayout(self)
        self.container = QFrame(); self.container.setObjectName("container")
        self.container.setStyleSheet(f"QFrame#container {{ background: {COLOR_BG_DARK}; border-radius: 30px; }}")
        self.layout = QVBoxLayout(self.container); self.main_layout.addWidget(self.container)
        
        header = QHBoxLayout()
        title = QLabel("ASR 三雄对比工具 V5 (Official Doc Sync)")
        title.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        close = QPushButton("✕"); close.clicked.connect(self.close); close.setStyleSheet("background: transparent; color: white; border: none; font-size: 20px;")
        header.addWidget(close)
        self.layout.addLayout(header)
        
        self.ctrls = {}
        for key in ["SenseVoice", "Nano", "Paraformer"]:
            row = QHBoxLayout()
            cb = QCheckBox(f"Enable {key}"); cb.setStyleSheet("color: white;"); cb.stateChanged.connect(lambda state, k=key: self.on_check_changed(state, k))
            row.addWidget(cb)
            btn_path = QPushButton("📁"); btn_path.setFixedSize(30,30); btn_path.clicked.connect(lambda _, k=key: self.pick_path(k)); row.addWidget(btn_path)
            btn_init = QPushButton("Initialize"); btn_init.setFixedSize(100, 30); btn_init.clicked.connect(lambda _, k=key: self.manual_init(k)); row.addWidget(btn_init)
            row.addStretch()
            self.layout.addLayout(row)
            self.ctrls[key] = {"cb": cb, "init": btn_init}
            
        self.card_layout = QHBoxLayout()
        self.card_sense = StatusCard("SenseVoice", COLOR_SENSE); self.card_nano = StatusCard("Nano", COLOR_NANO); self.card_para = StatusCard("Paraformer Online", COLOR_PARA)
        self.card_layout.addWidget(self.card_sense); self.card_layout.addWidget(self.card_nano); self.card_layout.addWidget(self.card_para)
        self.layout.addLayout(self.card_layout)

    def init_workers(self):
        self.w_sense = ASRWorker("SenseVoice", MODEL_PATHS["SenseVoice"])
        self.t_sense = QThread(); self.w_sense.moveToThread(self.t_sense); self.w_sense.unified_signal.connect(self.on_worker_signal); self.t_sense.start()
        self.w_nano = ASRWorker("Nano", MODEL_PATHS["Nano"])
        self.t_nano = QThread(); self.w_nano.moveToThread(self.t_nano); self.w_nano.unified_signal.connect(self.on_worker_signal); self.t_nano.start()
        self.w_para = ParaformerWorker(MODEL_PATHS["Paraformer"])
        self.t_para = QThread(); self.w_para.moveToThread(self.t_para); self.w_para.unified_signal.connect(self.on_para_signal); self.t_para.start()

    def on_worker_signal(self, data):
        mid, info_type, val1, *rest = data
        card = self.card_sense if mid == "SenseVoice" else self.card_nano
        if info_type == "status":
            card.set_status(val1)
            if "Ready" in val1: self.ctrls[mid]["init"].setText("Loaded")
            elif "Unloaded" in val1: self.ctrls[mid]["init"].setText("Initialize"); self.ctrls[mid]["init"].setEnabled(True)
        elif info_type == "result":
            card.set_text(val1); card.set_meta(f"Latency: {int(rest[0])}ms")
        elif info_type == "emotion":
            card.set_meta(f"Emotion: {val1}")

    def on_para_signal(self, data):
        info_type, val = data
        if info_type == "status":
            self.card_para.set_status(val)
            if "Ready" in val: self.ctrls["Paraformer"]["init"].setText("Loaded")
            elif "Unloaded" in val: self.ctrls["Paraformer"]["init"].setText("Initialize"); self.ctrls["Paraformer"]["init"].setEnabled(True)
        elif info_type == "result":
            self.para_text += val
            self.card_para.set_text(self.para_text)

    def manual_init(self, key):
        self.ctrls[key]["init"].setEnabled(False); self.ctrls[key]["init"].setText("Loading...")
        worker = self.w_sense if key == "SenseVoice" else (self.w_nano if key == "Nano" else self.w_para)
        QMetaObject.invokeMethod(worker, "load", Qt.ConnectionType.QueuedConnection); self.ctrls[key]["cb"].setChecked(True)

    def on_check_changed(self, state, key):
        if state == 0:
            worker = self.w_sense if key == "SenseVoice" else (self.w_nano if key == "Nano" else self.w_para)
            QMetaObject.invokeMethod(worker, "unload", Qt.ConnectionType.QueuedConnection)

    def pick_path(self, key):
        p = QFileDialog.getExistingDirectory(self, f"Select {key} Folder")
        if p:
            MODEL_PATHS[key] = p; worker = self.w_sense if key == "SenseVoice" else (self.w_nano if key == "Nano" else self.w_para)
            worker.path = p

    def init_audio(self): self.pa = pyaudio.PyAudio(); self.stream = None; self.is_rec = False
    def init_hotkey(self): self.caps_lock = False; keyboard.hook(self._on_key)
    def _on_key(self, e):
        if e.name == 'caps lock':
            if e.event_type == 'down' and not self.caps_lock:
                self.caps_lock = True; self.start_rec()
            elif e.event_type == 'up' and self.caps_lock:
                self.caps_lock = False; self.stop_rec()
                import ctypes
                if ctypes.windll.user32.GetKeyState(0x14) & 1: keyboard.press_and_release('caps lock')

    def start_rec(self):
        self.audio_buffer = []; self.para_text = ""
        self.card_sense.set_text("..."); self.card_nano.set_text("..."); self.card_para.set_text("")
        QMetaObject.invokeMethod(self.w_para, "reset_cache", Qt.ConnectionType.QueuedConnection)
        self.is_rec = True
        # 600ms buffer for better streaming stability
        self.stream = self.pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                                   frames_per_buffer=9600, stream_callback=self._audio_cb)

    def _audio_cb(self, in_data, frame_count, time_info, status):
        if self.is_rec:
            self.audio_buffer.append(in_data)
            if self.ctrls["Paraformer"]["cb"].isChecked():
                # Convert to float32 [ -1.0, 1.0 ]
                chunk = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
                QMetaObject.invokeMethod(self.w_para, "process_chunk", Qt.ConnectionType.QueuedConnection, Q_ARG(object, chunk))
        return (in_data, pyaudio.paContinue)

    def stop_rec(self):
        self.is_rec = False
        if self.stream: self.stream.close(); self.stream = None
        if self.audio_buffer:
            full = np.frombuffer(b''.join(self.audio_buffer), dtype=np.int16).astype(np.float32) / 32768.0
            if self.ctrls["SenseVoice"]["cb"].isChecked(): QMetaObject.invokeMethod(self.w_sense, "process_full", Qt.ConnectionType.QueuedConnection, Q_ARG(object, full))
            if self.ctrls["Nano"]["cb"].isChecked(): QMetaObject.invokeMethod(self.w_nano, "process_full", Qt.ConnectionType.QueuedConnection, Q_ARG(object, full))
            if self.ctrls["Paraformer"]["cb"].isChecked(): QMetaObject.invokeMethod(self.w_para, "finalize", Qt.ConnectionType.QueuedConnection)

    def mousePressEvent(self, e): self.m_pos = e.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, e): self.move(e.globalPosition().toPoint() - self.m_pos)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ASRBenchmarkPro(); window.show(); sys.exit(app.exec())
