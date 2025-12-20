"""
翻译引擎模块 - 支持多引擎
支持:
1. NLLB-200 1.2B (ctranslate2) - 高质量版
2. NLLB-200 600M (ctranslate2) - 标准版
3. NLLB-200 Original (transformers) - 原始版
4. Google Translate (在线备用)
"""

import os
import gc
import requests
import multiprocessing
import queue
import time
from abc import ABC, abstractmethod
from typing import Optional, List
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from model_config import (
    get_model_config,
    TranslatorEngineType,
    ModelInfo
)


# ===== 常量 =====
SOURCE_LANG = "zho_Hans"
TARGET_LANG = "jpn_Jpan"
GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"


# ===== 翻译引擎基类 =====

class BaseTranslatorEngine(ABC):
    """翻译引擎抽象基类"""
    
    def __init__(self):
        self.is_loaded = False
    
    @abstractmethod
    def load(self, model_path: str) -> bool:
        """加载模型"""
        pass
    
    @abstractmethod
    def translate(self, text: str) -> str:
        """翻译文本"""
        pass
    
    def unload(self):
        """卸载模型，释放资源"""
        self.is_loaded = False
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except:
            pass
        print(f"[{self.__class__.__name__}] 模型已卸载")


# ===== CTranslate2 引擎 =====

class CT2TranslatorEngine(BaseTranslatorEngine):
    """使用CTranslate2的高性能翻译引擎"""
    
    def __init__(self):
        super().__init__()
        self.translator = None
        self.sp = None
        self.tokenizer = None  # HF tokenizer备用
    
    def load(self, model_path: str) -> bool:
        try:
            import ctranslate2
            
            print(f"[CT2Engine] 加载模型: {model_path}")
            
            # 检查设备
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            print(f"[CT2Engine] 使用设备: {device}")
            
            # 加载翻译器
            self.translator = ctranslate2.Translator(model_path, device=device)
            
            # 尝试加载分词器
            # 方法1: SentencePiece模型
            sp_paths = [
                os.path.join(model_path, "sentencepiece.model"),
                os.path.join(model_path, "sentencepiece.bpe.model"),
                os.path.join(model_path, "spm.model"),
            ]
            
            for sp_path in sp_paths:
                if os.path.exists(sp_path):
                    import sentencepiece as spm
                    self.sp = spm.SentencePieceProcessor(sp_path)
                    print(f"[CT2Engine] 使用SentencePiece: {sp_path}")
                    self.is_loaded = True
                    print("[CT2Engine] 模型加载成功")
                    return True
            
            # 方法2: 使用shared_vocabulary.txt时，使用transformers tokenizer
            vocab_path = os.path.join(model_path, "shared_vocabulary.txt")
            if os.path.exists(vocab_path):
                try:
                    from transformers import NllbTokenizer
                    # 尝试从原始NLLB模型加载tokenizer (使用固定路径)
                    base_models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
                    original_model_path = os.path.join(base_models_dir, "nllb-200-distilled-600M")
                    print(f"[CT2Engine] 尝试加载Tokenizer from: {original_model_path}")
                    if os.path.exists(original_model_path):
                        self.tokenizer = NllbTokenizer.from_pretrained(original_model_path)
                        print(f"[CT2Engine] 使用HF Tokenizer")
                        self.is_loaded = True
                        print("[CT2Engine] 模型加载成功")
                        return True
                    else:
                        print(f"[CT2Engine] 原始模型不存在: {original_model_path}")
                except Exception as e:
                    print(f"[CT2Engine] 加载HF Tokenizer失败: {e}")
            
            print(f"[CT2Engine] 警告: 未找到有效的分词器")
            return False
            
        except Exception as e:
            print(f"[CT2Engine] 加载失败: {e}")
            self.is_loaded = False
            return False
    
    def translate(self, text: str) -> str:
        if not self.is_loaded or self.translator is None:
            return text
        
        if self.sp is None and self.tokenizer is None:
            return text
        
        try:
            # 按行处理，保持换行符
            lines = text.split('\n')
            results = []
            
            for line in lines:
                if not line.strip():
                    results.append("")
                    continue
                
                # 根据可用的分词器进行分词
                if self.sp is not None:
                    # 使用SentencePiece分词
                    source_tokens = self.sp.encode(line, out_type=str)
                    source_tokens = [SOURCE_LANG] + source_tokens + ["</s>"]
                    target_prefix = [[TARGET_LANG]]
                    
                    output = self.translator.translate_batch(
                        [source_tokens],
                        target_prefix=target_prefix,
                        beam_size=5,
                        num_hypotheses=1,
                        no_repeat_ngram_size=3,
                    )
                    
                    output_tokens = output[0].hypotheses[0][1:]
                    result_line = self.sp.decode(output_tokens)
                else:
                    # 使用HuggingFace Tokenizer
                    self.tokenizer.src_lang = SOURCE_LANG
                    encoded = self.tokenizer(line, return_tensors=None)
                    source_tokens = self.tokenizer.convert_ids_to_tokens(encoded["input_ids"])
                    target_prefix = [[TARGET_LANG]]
                    
                    output = self.translator.translate_batch(
                        [source_tokens],
                        target_prefix=target_prefix,
                        beam_size=5,
                        num_hypotheses=1,
                        no_repeat_ngram_size=3,
                    )
                    
                    output_tokens = output[0].hypotheses[0][1:]
                    output_ids = self.tokenizer.convert_tokens_to_ids(output_tokens)
                    result_line = self.tokenizer.decode(output_ids, skip_special_tokens=True)
                
                results.append(result_line)
            
            return '\n'.join(results)
            
        except Exception as e:
            print(f"[CT2Engine] 翻译错误: {e}")
            return text
    
    def unload(self):
        if self.translator is not None:
            del self.translator
            self.translator = None
        if self.sp is not None:
            del self.sp
            self.sp = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        super().unload()


# ===== HuggingFace Transformers 引擎 =====

class HFTranslatorEngine(BaseTranslatorEngine):
    """使用HuggingFace Transformers的翻译引擎"""
    
    def __init__(self):
        super().__init__()
        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.tgt_lang_id = None
    
    def load(self, model_path: str) -> bool:
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            import torch
            
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"[HFEngine] 加载模型: {model_path} on {self.device}")
            
            # 加载配置
            load_kwargs = {}
            if self.device == "cuda":
                load_kwargs["torch_dtype"] = torch.float16
            
            # 加载模型和分词器
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_path, **load_kwargs).to(self.device)
            
            # 获取目标语言ID
            self.tgt_lang_id = self.tokenizer.convert_tokens_to_ids(TARGET_LANG)
            
            # 预热
            self._warmup()
            
            self.is_loaded = True
            print("[HFEngine] 模型加载成功")
            return True
            
        except Exception as e:
            print(f"[HFEngine] 加载失败: {e}")
            self.is_loaded = False
            return False
    
    def _warmup(self):
        """预热模型"""
        import torch
        self.tokenizer.src_lang = SOURCE_LANG
        dummy_inputs = self.tokenizer("你好", return_tensors="pt").to(self.device)
        with torch.inference_mode():
            self.model.generate(**dummy_inputs, forced_bos_token_id=self.tgt_lang_id, max_length=5)
    
    def translate(self, text: str) -> str:
        if not self.is_loaded or self.model is None:
            return text
        
        try:
            import torch
            
            # 按行处理
            lines = text.split('\n')
            results = []
            
            for line in lines:
                if not line.strip():
                    results.append("")
                    continue
                
                self.tokenizer.src_lang = SOURCE_LANG
                inputs = self.tokenizer(line, return_tensors="pt").to(self.device)
                
                with torch.inference_mode():
                    translated_tokens = self.model.generate(
                        **inputs,
                        forced_bos_token_id=self.tgt_lang_id,
                        max_length=256,
                        num_beams=5,
                        no_repeat_ngram_size=3,
                        length_penalty=1.0,
                        early_stopping=True,
                        do_sample=False
                    )
                
                result_line = self.tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
                results.append(result_line)
            
            return '\n'.join(results)
            
        except Exception as e:
            print(f"[HFEngine] 翻译错误: {e}")
            return text
    
    def unload(self):
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        super().unload()


# ===== 在线翻译引擎 =====

class OnlineTranslatorEngine(BaseTranslatorEngine):
    """Google Translate在线引擎（备用）"""
    
    def __init__(self):
        super().__init__()
        self.is_loaded = True  # 在线引擎始终可用
    
    def load(self, model_path: str = None) -> bool:
        self.is_loaded = True
        return True
    
    def translate(self, text: str) -> str:
        try:
            params = {
                "client": "gtx",
                "sl": "zh-CN",
                "tl": "ja",
                "dt": "t",
                "q": text
            }
            response = requests.get(GOOGLE_URL, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data and data[0]:
                return "".join([part[0] for part in data[0] if part[0]])
            return text
        except Exception as e:
            print(f"[OnlineEngine] 翻译错误: {e}")
            return text


# ===== 引擎工厂 =====

def create_translator_engine(engine_type: str) -> Optional[BaseTranslatorEngine]:
    """根据类型创建翻译引擎"""
    if engine_type in [TranslatorEngineType.NLLB_1_2B_CT2.value, TranslatorEngineType.NLLB_600M_CT2.value]:
        return CT2TranslatorEngine()
    elif engine_type == TranslatorEngineType.NLLB_ORIGINAL.value:
        return HFTranslatorEngine()
    elif engine_type == "online":
        return OnlineTranslatorEngine()
    else:
        print(f"[TranslatorFactory] 未知引擎类型: {engine_type}")
        return None


# ===== 多进程推理Worker（用于隔离进程） =====

def inference_worker_process(model_path, engine_type, input_queue, output_queue):
    """
    独立进程中运行的推理worker
    完全隔离，避免阻塞主进程
    """
    try:
        # 根据引擎类型创建引擎
        engine = create_translator_engine(engine_type)
        if engine is None:
            output_queue.put(("fatal", f"无法创建引擎: {engine_type}"))
            return
        
        # 加载模型
        if not engine.load(model_path):
            output_queue.put(("fatal", "模型加载失败"))
            return
        
        output_queue.put(("status", "ready"))
        
        # 处理翻译请求
        while True:
            try:
                task = input_queue.get()
                if task is None:
                    break  # 退出信号
                
                result = engine.translate(task)
                output_queue.put(("result", result))
                
            except Exception as e:
                output_queue.put(("error", str(e)))
                
    except Exception as e:
        output_queue.put(("fatal", str(e)))


# ===== 翻译引擎管理器 =====

class TranslatorEngine(QObject):
    """翻译引擎管理器 - 支持多引擎切换"""
    
    status_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.config = get_model_config()
        
        # 引擎实例（同进程模式）
        self._engine: Optional[BaseTranslatorEngine] = None
        self._current_engine_type: Optional[str] = None
        
        # 多进程模式（用于避免阻塞）
        self._use_multiprocess = False
        self._input_queue = None
        self._output_queue = None
        self._proc = None
        
        # 在线引擎（备用）
        self._online_engine = OnlineTranslatorEngine()
        
        # 状态
        self.mode = "online"  # "online" or "local"
        self.local_is_ready = False
    
    def set_mode(self, mode: str):
        """设置翻译模式"""
        self.mode = mode
        if mode == "local" and not self.local_is_ready:
            self._start_local_engine()
    
    def switch_engine(self, engine_type: str):
        """切换翻译引擎"""
        if engine_type == self._current_engine_type:
            print(f"[TranslatorEngine] 引擎未变化: {engine_type}")
            return
        
        self.status_changed.emit("正在切换翻译引擎...")
        
        # 卸载旧引擎
        self._unload_current_engine()
        
        # 更新配置
        self.config.current_translator_engine = engine_type
        self._current_engine_type = engine_type
        
        # 如果当前是本地模式，启动新引擎
        if self.mode == "local":
            self._start_local_engine()
    
    def _start_local_engine(self):
        """启动本地翻译引擎"""
        engine_type = self.config.current_translator_engine
        
        # 获取模型路径（自动解压ZIP）
        model_path = self.config.get_translator_model_path(engine_type)
        if not model_path:
            self.status_changed.emit("模型路径无效")
            return
        
        self.status_changed.emit(f"正在加载翻译模型...")
        print(f"[TranslatorEngine] 加载引擎: {engine_type}, 路径: {model_path}")
        
        if self._use_multiprocess:
            self._start_multiprocess_engine(model_path, engine_type)
        else:
            self._start_inprocess_engine(model_path, engine_type)
    
    def _start_inprocess_engine(self, model_path: str, engine_type: str):
        """同进程加载引擎（简单但可能阻塞UI）"""
        self._engine = create_translator_engine(engine_type)
        if self._engine is None:
            self.status_changed.emit("引擎创建失败")
            return
        
        if self._engine.load(model_path):
            self.local_is_ready = True
            self._current_engine_type = engine_type
            self.status_changed.emit("翻译模型加载完成")
        else:
            self.status_changed.emit("翻译模型加载失败")
    
    def _start_multiprocess_engine(self, model_path: str, engine_type: str):
        """多进程加载引擎（隔离，不阻塞UI）"""
        self._input_queue = multiprocessing.Queue()
        self._output_queue = multiprocessing.Queue()
        self._proc = multiprocessing.Process(
            target=inference_worker_process,
            args=(model_path, engine_type, self._input_queue, self._output_queue),
            daemon=True
        )
        self._proc.start()
    
    def _unload_current_engine(self):
        """卸载当前引擎"""
        # 同进程引擎
        if self._engine is not None:
            self._engine.unload()
            self._engine = None
        
        # 多进程引擎
        if self._proc is not None:
            try:
                self._input_queue.put(None)
                self._proc.terminate()
                self._proc.join(timeout=1)
            except:
                pass
            self._proc = None
            self._input_queue = None
            self._output_queue = None
        
        self.local_is_ready = False
        self._current_engine_type = None
    
    def is_local_ready(self) -> bool:
        """检查本地引擎是否就绪"""
        if self.local_is_ready:
            return True
        
        # 检查多进程模式下的状态
        if self._output_queue is not None:
            try:
                while not self._output_queue.empty():
                    msg_type, val = self._output_queue.get_nowait()
                    if msg_type == "status" and val == "ready":
                        self.local_is_ready = True
                        self.status_changed.emit("翻译模型加载完成")
                        return True
            except:
                pass
        
        return False
    
    def translate(self, text: str, source='zh-CN', target='ja') -> str:
        """翻译文本"""
        if not text:
            return ""
        
        # 本地模式
        if self.mode == "local":
            if self.is_local_ready():
                return self._translate_local(text)
            else:
                # 回退到在线
                return self._online_engine.translate(text)
        else:
            return self._online_engine.translate(text)
    
    def _translate_local(self, text: str) -> str:
        """使用本地引擎翻译"""
        # 同进程模式
        if self._engine is not None:
            return self._engine.translate(text)
        
        # 多进程模式
        if self._proc is not None and self._input_queue is not None:
            # 清空队列
            while not self._output_queue.empty():
                try:
                    self._output_queue.get_nowait()
                except:
                    break
            
            self._input_queue.put(text)
            
            try:
                res_type, val = self._output_queue.get(timeout=15)
                if res_type == "result":
                    return val
                return f"[{res_type}] {val}"
            except queue.Empty:
                return "[Timeout] 本地引擎响应超时"
        
        return text
    
    def get_current_engine_info(self) -> Optional[ModelInfo]:
        """获取当前引擎信息"""
        return self.config.get_translator_model_info()
    
    def get_available_engines(self) -> List[ModelInfo]:
        """获取所有可用引擎"""
        return self.config.get_available_translator_engines()
    
    def cleanup(self):
        """清理资源"""
        self._unload_current_engine()
        print("[TranslatorEngine] 资源已清理")

class TranslationWorker(QObject):
    result_ready = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self, engine: TranslatorEngine):
        super().__init__()
        self.engine = engine
        self.engine.status_changed.connect(self.status_changed.emit)

    @pyqtSlot(str)
    def on_translate_requested(self, text: str):
        if not text:
            self.result_ready.emit("")
            return
        
        try:
            result = self.engine.translate(text)
            self.result_ready.emit(result)
        except Exception as e:
            print(f"[TranslationWorker] Error: {e}")
            self.result_ready.emit(f"[Error] {e}")

    @pyqtSlot(str)
    def on_engine_change_requested(self, engine_id: str):
        try:
            self.status_changed.emit("loading")
            self.engine.set_mode("local")
            # The actual heavy loading happens in set_mode or when engine.translate is called
            # but ModelConfig says what model to use.
            # Usually we need to notify the engine to reload.
            # In current TranslatorEngine, it seems to load based on ModelConfig.
        except Exception as e:
            print(f"[TranslationWorker] Engine change error: {e}")

