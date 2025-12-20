"""
ASR管理模块 - 支持多引擎和输出模式
支持:
1. SenseVoiceSmall-ONNX (进程隔离模式) - 彻底解决崩溃问题
2. SenseVoiceSmall (funasr PyTorch) - 全量驱动
"""

import os
import re
import gc
import sys
import torch
import numpy as np
import multiprocessing
import traceback
from abc import ABC, abstractmethod
from typing import Optional, List
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot

from model_config import (
    get_model_config, 
    ASREngineType, 
    ASROutputMode,
    ModelInfo
)

# 设置环境变量，解决可能的OpenMP库冲突
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ===== 语气词清理配置 =====
FILLER_WORDS = [
    '嗯', '啊', '哦', '呃', '额', '哎',
    '那个', '就是', '然后', '这个', '所以', '其实',
    '对吧', '你知道', '就是说', '怎么说呢',
]

def restore_punctuation_heuristic(text: str) -> str:
    """
    基于启发式规则的简单标点恢复 (针对 SenseVoice ONNX)
    """
    if not text:
        return text
        
    # 1. 在常见语气助词或停顿词后加逗号
    # 吗, 呢经常是疑问句结尾，后面先不加逗号
    text = re.sub(r'([吧了啊哦呃嘛呀])', r'\1，', text)
    
    # 2. 处理由于 re.sub 产生的多重逗号
    text = re.sub(r'，+', '，', text)
    
    # 3. 删除末尾多余的逗号
    text = text.rstrip('，')
    
    # 4. 判定结尾标点 (句号或问号)
    if not text.endswith(('。', '？', '！', '.', '?', '!')):
        # 常见疑问词
        is_question = any(q in text for q in ['谁', '什么', '哪', '怎么', '为什么', '吗', '多少', '几时', '如何'])
        if is_question:
            text += '？'
        else:
            text += '。'
            
    # 5. 长句分割 (如果句子超过15字且中间没标点，强制在常用助词后加逗号)
    if len(text) > 15 and '，' not in text:
        # 在这些字后面尝试加逗号，优先度从前到后
        break_chars = ['的', '了', '是', '在', '和', '与', '就', '才', '让']
        for char in break_chars:
            idx = text.find(char)
            # 确保位置在中间区间 (比如第 4 到倒数第 4 个字之间)
            if 3 < idx < len(text) - 4:
                text = text[:idx+1] + '，' + text[idx+1:]
                break
                
    # 优化：删除连续重复标点
    text = re.sub(r'([，。？！])\1+', r'\1', text)
        
    return text

def clean_asr_output(text: str, remove_tags_only=False) -> str:
    """
    清理ASR输出文本
    remove_tags_only: 仅移除 <|xxx|> 标签
    """
    if not text:
        return text
        
    # 必须移除的标签 (即便在 RAW 模式下也要移除)
    text = re.sub(r'<\|.*?\|>', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    
    if remove_tags_only:
        return text.strip()
        
    # 强化清理模式
    for word in FILLER_WORDS:
        text = text.replace(word, '')
        
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ===== ONNX 推理独立进程核心函数 =====
def onnx_inference_worker(model_path, input_queue, output_queue):
    """独立的 ONNX 推理进程，避免与 GUI 库冲突"""
    try:
        import sys
        
        # 判断是否为 Sherpa-ONNX 模型
        use_sherpa = "sherpa" in model_path.lower()
        
        print(f"[ASR-Proc] 启动中, 模型: {os.path.basename(model_path)}")
        sys.stdout.flush()
        
        model = None
        recognizer = None
        
        if use_sherpa:
            import sherpa_onnx
            print(f"[ASR-Proc] 使用 Sherpa-ONNX 引擎 (支持标点)")
            
            model_file = os.path.join(model_path, "model.int8.onnx")
            if not os.path.exists(model_file):
                model_file = os.path.join(model_path, "model.onnx")
                
            tokens_file = os.path.join(model_path, "tokens.txt")
            
            if not os.path.exists(model_file) or not os.path.exists(tokens_file):
                raise FileNotFoundError(f"Sherpa模型文件缺失: {model_file} 或 {tokens_file}")
                
            recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model_file,
                tokens=tokens_file,
                use_itn=True,  # 启用逆文本标准化 (标点恢复)
                num_threads=4
            )
        else:
            from funasr_onnx import SenseVoiceSmall
            print(f"[ASR-Proc] 使用 FunASR-ONNX 引擎 (无内置标点)")
            # 初始化模型 (在独立进程中)
            model = SenseVoiceSmall(model_path, quantize=True)
            
        print(f"[ASR-Proc] 模型加载成功")
        sys.stdout.flush()
        
        # 通知主进程已就绪
        output_queue.put(("ready", True))
        
        while True:
            # 等待任务
            task = input_queue.get()
            if task is None: 
                break
            
            # 执行推理
            try:
                # 转化数据为 numpy 数组
                audio_data = np.array(task, dtype=np.float32)
                text = ""
                
                if use_sherpa:
                    # Sherpa 推理流程
                    stream = recognizer.create_stream()
                    stream.accept_waveform(16000, audio_data)
                    recognizer.decode_stream(stream)
                    text = stream.result.text
                else:
                    # FunASR 推理流程
                    result = model(audio_data, language="zh", use_itn=True)
                    if result and len(result) > 0:
                        res_obj = result[0]
                        text = res_obj.get('text', '') if isinstance(res_obj, dict) else str(res_obj)
                
                # 在子进程中就完成标签过滤
                text = clean_asr_output(text, remove_tags_only=True)
                
                # 如果使用 FunASR 且没有标点，应用启发式规则
                # Sherpa 开启 use_itn 后自带标点，不需要启发式
                if not use_sherpa:
                    if not any(p in text for p in ['，', '。', '？', '！']):
                        text = restore_punctuation_heuristic(text)
                    
                output_queue.put(("result", text))
                
            except Exception as e:
                print(f"[ASR-Proc] 转写中错误: {e}")
                output_queue.put(("result", f"Error: {str(e)}"))
            sys.stdout.flush()
            
    except Exception as e:
        import traceback
        err = f"ASR进程崩溃: {str(e)}\n{traceback.format_exc()}"
        print(err)
        output_queue.put(("fatal", err))
    finally:
        print("[ASR-Proc] 进程已退出")
        sys.stdout.flush()

# ===== 引擎抽象 =====
class BaseASREngine(ABC):
    def __init__(self):
        self.is_loaded = False
    
    @abstractmethod
    def load(self, model_path: str) -> bool: pass
    
    @abstractmethod
    def transcribe(self, audio_data) -> str: pass
    
    @abstractmethod
    def unload(self): pass

# ===== ONNX 引擎代理 (封装进程通信) =====
class OnnxASREngine(BaseASREngine):
    def __init__(self):
        super().__init__()
        self.input_queue = multiprocessing.Queue()
        self.output_queue = multiprocessing.Queue()
        self.process = None
    
    def load(self, model_path: str) -> bool:
        try:
            print(f"[OnnxASREngine] 正在通过多进程加载: {model_path}")
            if self.process and self.process.is_alive():
                self.unload()
            
            self.process = multiprocessing.Process(
                target=onnx_inference_worker,
                args=(model_path, self.input_queue, self.output_queue),
                daemon=True
            )
            self.process.start()
            
            # 等待确认信号
            try:
                msg_type, val = self.output_queue.get(timeout=30)
                if msg_type == "ready":
                    self.is_loaded = True
                    return True
                else:
                    return False
            except Exception as e:
                return False
        except Exception as e:
            return False
    
    def transcribe(self, audio_data) -> str:
        if not self.is_loaded or not self.process.is_alive():
            return "引擎未就绪"
        try:
            if isinstance(audio_data, np.ndarray):
                audio_list = audio_data.tolist()
            else:
                audio_list = audio_data
            
            self.input_queue.put(audio_list)
            msg_type, val = self.output_queue.get(timeout=60)
            return val
        except Exception as e:
            return f"转写失败: {str(e)}"

    def unload(self):
        if self.process and self.process.is_alive():
            try:
                self.input_queue.put(None)
                self.process.join(timeout=2)
                if self.process.is_alive():
                    self.process.terminate()
            except:
                pass
        self.process = None
        self.is_loaded = False

# ===== PyTorch 引擎 (支持标点) =====
class PyTorchASREngine(BaseASREngine):
    def __init__(self):
        super().__init__()
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
    
    def load(self, model_path: str) -> bool:
        try:
            from funasr import AutoModel
            self.model = AutoModel(model=model_path, device=self.device, disable_update=True)
            self.is_loaded = True
            return True
        except Exception as e:
            return False
    
    def transcribe(self, audio_data) -> str:
        if not self.is_loaded or self.model is None: return ""
        try:
            res = self.model.generate(
                input=audio_data, cache={}, language="auto", use_itn=True,
                batch_size_s=60, merge_vad=True, merge_length_s=15,
            )
            if res:
                text = res[0].get('text', '')
                # PyTorch版本通常自带标点，仅需移除标签
                text = clean_asr_output(text, remove_tags_only=True)
                return text.strip()
            return ""
        except Exception as e:
            return ""

    def unload(self):
        if self.model:
            del self.model
            self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        self.is_loaded = False

# ===== ASR Worker & Manager =====
class ASRWorker(QObject):
    model_ready = pyqtSignal()
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.config = get_model_config()
        self.engine: Optional[BaseASREngine] = None
    
    @pyqtSlot()
    def load_model(self):
        engine_type = self.config.current_asr_engine
        if self.engine: self.engine.unload()
        
        if engine_type == ASREngineType.SENSEVOICE_ONNX.value:
            self.engine = OnnxASREngine()
        else:
            self.engine = PyTorchASREngine()
        
        model_path = self.config.get_asr_model_path(engine_type)
        self.status_changed.emit(f"正在加载ASR模型...")
        if self.engine.load(model_path):
            self.status_changed.emit("ASR模型加载完成")
            self.model_ready.emit()
        else:
            self.error_occurred.emit("ASR模型加载失败")
    
    @pyqtSlot(object)
    def transcribe(self, audio_data):
        if not self.engine or not self.engine.is_loaded:
            self.error_occurred.emit("ASR引擎未就绪")
            return
        try:
            text = self.engine.transcribe(audio_data)
            # 全量清理 (去除语气词等)
            if self.config.asr_output_mode == ASROutputMode.CLEANED.value:
                text = clean_asr_output(text)
            
            if text:
                self.result_ready.emit(text)
        except Exception as e:
            self.error_occurred.emit(f"转写异常: {str(e)}")

class ASRManager(QObject):
    _instance = None
    _initialized = False
    
    model_ready = pyqtSignal()
    result_ready = pyqtSignal(str)
    error = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    _sig_load_model = pyqtSignal()
    _sig_transcribe = pyqtSignal(object)
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ASRManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not ASRManager._initialized:
            super().__init__()
            ASRManager._initialized = True
            self.config = get_model_config()
            self.worker = ASRWorker()
            self.thread = QThread()
            self.worker.moveToThread(self.thread)
            
            self.worker.model_ready.connect(self.model_ready.emit)
            self.worker.result_ready.connect(self.result_ready.emit)
            self.worker.error_occurred.connect(self.error.emit)
            self.worker.status_changed.connect(self.status_changed.emit)
            self._sig_load_model.connect(self.worker.load_model)
            self._sig_transcribe.connect(self.worker.transcribe)
            
            self.thread.start()
            self._sig_load_model.emit()
    
    def transcribe_async(self, audio_data):
        if isinstance(audio_data, np.ndarray):
            data_to_send = audio_data.tolist()
        else:
            data_to_send = audio_data
        self._sig_transcribe.emit(data_to_send)
    
    def switch_engine(self, engine_type: str):
        self.config.current_asr_engine = engine_type
        self._sig_load_model.emit()
    
    def set_output_mode(self, mode: str):
        self.config.asr_output_mode = mode

    def cleanup(self):
        if self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        if self.worker.engine:
            self.worker.engine.unload()
