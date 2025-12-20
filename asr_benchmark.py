import sys
import time
import os
import threading
import numpy as np
import pyaudio
import torch
import psutil
from funasr import AutoModel
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QCheckBox, QTextEdit, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QObject, pyqtProperty

# Model Configs
MODELS_TO_TEST = {
    "SenseVoiceSmall": "iic/SenseVoiceSmall",
    "Paraformer-Short": "damo/speech_paraformer-short-utf8-zh-cn-fp32",
    "FunASR-Nano": "FunAudioLLM/Fun-ASR-Nano"
}

class ModelWorker(QObject):
    finished = pyqtSignal(str, str, float, float) # model_name, text, time_ms, mem_mb
    status = pyqtSignal(str, str) # model_name, status_text

    def __init__(self, model_key, model_path):
        super().__init__()
        self.model_key = model_key
        self.model_path = model_path
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    @pyqtSlot()
    def load(self):
        try:
            self.status.emit(self.model_key, "Loading...")
            start_mem = psutil.Process().memory_info().rss / (1024 * 1024)
            self.model = AutoModel(model=self.model_path, device=self.device, disable_update=True)
            end_mem = psutil.Process().memory_info().rss / (1024 * 1024)
            self.status.emit(self.model_key, f"Ready (Used ~{end_mem - start_mem:.1f}MB)")
        except Exception as e:
            self.status.emit(self.model_key, f"Error: {e}")

    @pyqtSlot(object)
    def run_inference(self, audio_data):
        if self.model is None:
            return
        
        try:
            self.status.emit(self.model_key, "Inference...")
            start_time = time.time()
            start_mem = psutil.Process().memory_info().rss / (1024 * 1024)
            
            res = self.model.generate(input=audio_data, language="zh", use_itn=True)
            
            end_time = time.time()
            end_mem = psutil.Process().memory_info().rss / (1024 * 1024)
            
            text = res[0].get('text', '') if res else "No Result"
            import re
            text = re.sub(r'<\|.*?\|>', '', text).strip()
            
            time_ms = (end_time - start_time) * 1000
            mem_inc = end_mem - start_mem
            
            self.finished.emit(self.model_key, text, time_ms, mem_inc)
            self.status.emit(self.model_key, "Idle")
        except Exception as e:
            self.finished.emit(self.model_key, f"Error: {e}", 0, 0)
            self.status.emit(self.model_key, "Idle")

class BenchmarkApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASR Model Benchmark Tool")
        self.resize(900, 600)
        self.init_ui()
        
        self.workers = {}
        self.threads = {}
        self.audio_recorder = pyaudio.PyAudio()
        self.recording_frames = []
        self.is_recording = False
        self.last_audio_data = None

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Model Selection
        selection_layout = QHBoxLayout()
        self.checks = {}
        for name in MODELS_TO_TEST:
            cb = QCheckBox(name)
            cb.setChecked(name == "SenseVoiceSmall")
            selection_layout.addWidget(cb)
            self.checks[name] = cb
        
        load_btn = QPushButton("Load Selected Models")
        load_btn.clicked.connect(self.load_models)
        selection_layout.addWidget(load_btn)
        layout.addLayout(selection_layout)

        # 2. Controls
        ctrl_layout = QHBoxLayout()
        self.record_btn = QPushButton("Start Recording (Hold)")
        self.record_btn.pressed.connect(self.start_recording)
        self.record_btn.released.connect(self.stop_recording)
        ctrl_layout.addWidget(self.record_btn)

        self.run_btn = QPushButton("Run Benchmark on Last Audio")
        self.run_btn.clicked.connect(self.run_benchmark)
        ctrl_layout.addWidget(self.run_btn)
        layout.addLayout(ctrl_layout)

        # 3. Status Labels
        self.status_labels = {}
        status_box = QHBoxLayout()
        for name in MODELS_TO_TEST:
            lbl = QLabel(f"{name}: Not Loaded")
            lbl.setStyleSheet("color: gray;")
            status_box.addWidget(lbl)
            self.status_labels[name] = lbl
        layout.addLayout(status_box)

        # 4. Results Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Model", "Result Text", "Time (ms)", "Mem Inc (MB)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        layout.addWidget(self.log)

    def load_models(self):
        for name, cb in self.checks.items():
            if cb.isChecked() and name not in self.workers:
                worker = ModelWorker(name, MODELS_TO_TEST[name])
                thread = QThread()
                worker.moveToThread(thread)
                
                worker.status.connect(self.update_status)
                worker.finished.connect(self.add_result)
                
                self.workers[name] = worker
                self.threads[name] = thread
                thread.start()
                
                from PyQt6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(worker, "load", Qt.ConnectionType.QueuedConnection)

    def update_status(self, name, text):
        self.status_labels[name].setText(f"{name}: {text}")
        if "Error" in text:
            self.status_labels[name].setStyleSheet("color: red;")
        elif "Ready" in text:
            self.status_labels[name].setStyleSheet("color: green;")
        else:
            self.status_labels[name].setStyleSheet("color: blue;")

    def start_recording(self):
        self.is_recording = True
        self.recording_frames = []
        self.record_btn.setText("Recording...")
        self.record_btn.setStyleSheet("background: red; color: white;")
        threading.Thread(target=self._record_thread, daemon=True).start()

    def _record_thread(self):
        stream = self.audio_recorder.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
        while self.is_recording:
            self.recording_frames.append(stream.read(1024))
        stream.stop_stream()
        stream.close()

    def stop_recording(self):
        self.is_recording = False
        self.record_btn.setText("Start Recording (Hold)")
        self.record_btn.setStyleSheet("")
        if self.recording_frames:
            audio_data = np.frombuffer(b''.join(self.recording_frames), dtype=np.int16).astype(np.float32) / 32768.0
            self.last_audio_data = audio_data
            self.log.append(f"Recorded {len(audio_data)/16000:.2f}s audio.")
            self.run_benchmark()

    def run_benchmark(self):
        if self.last_audio_data is None:
            self.log.append("Error: No audio data.")
            return
        
        self.table.setRowCount(0)
        loaded_any = False
        for name, worker in self.workers.items():
            if self.checks[name].isChecked():
                loaded_any = True
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(worker, "run_inference", Qt.ConnectionType.QueuedConnection, Q_ARG(object, self.last_audio_data))
        
        if not loaded_any:
            self.log.append("Error: No models loaded.")

    def add_result(self, name, text, time_ms, mem_mb):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(text))
        self.table.setItem(row, 2, QTableWidgetItem(f"{time_ms:.1f}"))
        self.table.setItem(row, 3, QTableWidgetItem(f"{mem_mb:.1f}"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = BenchmarkApp()
    ex.show()
    sys.exit(app.exec())
