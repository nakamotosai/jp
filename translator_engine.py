"""
翻译引擎模块 - CPU 纯净版
强制使用 CPU 模式，避免 CUDA 检测导致的挂起问题
"""

import os
import gc
import sys
import requests
import time
import traceback
from abc import ABC, abstractmethod
from typing import Optional
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


def log_translator(msg):
    """统一日志函数"""
    try:
        cfg = get_model_config()
        log_file = os.path.join(cfg.DATA_DIR, "translator_debug.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except: pass
    print(f"[Translator] {msg}")


class BaseTranslatorEngine(ABC):
    def __init__(self):
        self.is_loaded = False
    
    @abstractmethod
    def load(self, model_path: str) -> bool: pass
    
    @abstractmethod
    def translate(self, text: str) -> str: pass
    
    def unload(self):
        self.is_loaded = False
        gc.collect()


class CT2TranslatorEngine(BaseTranslatorEngine):
    def __init__(self):
        super().__init__()
        self.translator = None
        self.sp = None
        self.is_loaded = False
        self.src_prefix = f"__{SOURCE_LANG}__"
        self.tgt_prefix_token = f"__{TARGET_LANG}__"

    def _find_lang_tokens(self, model_dir):
        """探测词典中真实的语言标识符格式"""
        voc_files = ["shared_vocabulary.txt", "vocabulary.txt", "shared_vocabulary.json", "vocabulary.json"]
        voc_content = ""
        for f_name in voc_files:
            p = os.path.join(model_dir, f_name)
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f_in:
                        voc_content = f_in.read()
                        break
                except: continue
        
        def find_best(lang):
            candidates = [f"__{lang}__", lang, lang.replace('_', '-'), lang.split('_')[1] if '_' in lang else lang]
            for c in candidates:
                if c in voc_content:
                    return c
            return f"__{lang}__" 

        self.src_prefix = find_best(SOURCE_LANG)
        self.tgt_prefix_token = find_best(TARGET_LANG)

    def load(self, model_path: str) -> bool:
        if not model_path:
            log_translator("load() 失败: model_path 为空")
            return False
            
        if not os.path.exists(model_path):
            log_translator(f"load() 失败: 路径不存在 {model_path}")
            return False
            
        try:
            import ctranslate2
            actual_model_dir = model_path
            if os.path.isdir(model_path):
                if not os.path.exists(os.path.join(model_path, "model.bin")):
                    for root, dirs, files in os.walk(model_path):
                        if "model.bin" in files:
                            actual_model_dir = root
                            break
            
            log_translator(f"开始加载模型 (CPU 模式): {actual_model_dir}")
            
            # === 打包环境下的 DLL 加载补丁 ===
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
                ct2_dll_dir = os.path.join(base_dir, "_internal", "ctranslate2")
                if os.path.exists(ct2_dll_dir):
                    log_translator(f"添加 DLL 搜索路径: {ct2_dll_dir}")
                    if sys.platform == 'win32':
                        # 核心：将 DLL 目录加入 PATH 环境变量，确保扩展能找到它
                        os.environ["PATH"] = ct2_dll_dir + os.pathsep + os.environ["PATH"]
                        if hasattr(os, 'add_dll_directory'):
                            try: os.add_dll_directory(ct2_dll_dir)
                            except: pass
            
            # 强制使用 CPU 模式，避免 CUDA 检测导致的挂起问题
            self.translator = ctranslate2.Translator(
                actual_model_dir, 
                device="cpu", 
                compute_type="int8"
            )
            self._find_lang_tokens(actual_model_dir)
            
            # 预热
            self.translator.translate_batch([[" "]], target_prefix=[[self.tgt_prefix_token]])
            log_translator("预热完成")

            sp_files = ["sentencepiece.bpe.model", "sentencepiece.model", "spm.model", "tokenizer.model"]
            for f in sp_files:
                sp_path = os.path.join(actual_model_dir, f)
                if os.path.exists(sp_path):
                    import sentencepiece as spm
                    self.sp = spm.SentencePieceProcessor(sp_path)
                    self.is_loaded = True
                    log_translator("模型加载成功 (CPU)")
                    return True
            
            log_translator("未找到 sentencepiece 模型文件")
            return False
            
        except Exception as e:
            log_translator(f"load() 异常: {e}")
            traceback.print_exc()
            return False
    
    def translate(self, text: str) -> str:
        if not self.is_loaded or self.translator is None or self.sp is None:
            return text
        
        try:
            lines = text.split('\n')
            results = []
            for line in lines:
                if not line.strip():
                    results.append("")
                    continue
                
                tokens = self.sp.encode(line, out_type=str)
                source_tokens = [self.src_prefix] + tokens + ["</s>"]
                
                output = self.translator.translate_batch(
                    [source_tokens],
                    target_prefix=[[self.tgt_prefix_token]],
                    beam_size=4,
                    max_decoding_length=256,
                    replace_unknowns=True
                )
                
                output_tokens = output[0].hypotheses[0]
                
                # 精准移除标识符
                if output_tokens:
                    first_token = output_tokens[0].lower()
                    if "jpn" in first_token or "zho" in first_token or first_token.startswith("__"):
                        output_tokens = output_tokens[1:]
                
                result_line = self.sp.decode(output_tokens)
                results.append(result_line)
            
            return '\n'.join(results)
        except Exception as e:
            log_translator(f"翻译错误: {e}")
            return text

    def unload(self):
        if self.translator: 
            del self.translator
        if self.sp: 
            del self.sp
        self.translator = self.sp = None
        self.is_loaded = False
        super().unload()


class OnlineTranslatorEngine(BaseTranslatorEngine):
    def __init__(self):
        super().__init__()
        self.is_loaded = True
        
    def load(self, model_path: str = None) -> bool: 
        return True
        
    def translate(self, text: str) -> str:
        try:
            params = {"client": "gtx", "sl": "zh-CN", "tl": "ja", "dt": "t", "q": text}
            response = requests.get(GOOGLE_URL, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data and data[0]: 
                return "".join([part[0] for part in data[0] if part[0]])
            return text
        except Exception as e:
            log_translator(f"Google 翻译失败: {e}")
            return text


class TranslatorEngine(QObject):
    status_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.config = get_model_config()
        self._engine = None
        self._current_engine_type = None
        self._online_engine = OnlineTranslatorEngine()
        self.mode = "online"
        self.local_is_ready = False
    
    @property
    def current_engine_id(self) -> str:
        if self.mode == "online": 
            return "online"
        return self._current_engine_type if self.local_is_ready else "online"
    
    def switch_engine(self, engine_type: str):
        """
        切换翻译引擎
        重要：此方法必须始终发出 status_changed 信号，否则 UI 会卡住
        """
        log_translator(f"switch_engine 被调用: {engine_type}")
        
        # 如果已经是目标引擎且已就绪，直接返回成功
        if engine_type == self._current_engine_type and self.mode == "local" and self.local_is_ready:
            log_translator("引擎已就绪，无需切换")
            self.status_changed.emit("翻译模型准备就绪")
            return
        
        # [MODIFIED] Force usage of online engine (User Request: Disable Local NLLB)
        if engine_type != "online":
            log_translator(f"请求切换到 {engine_type}，但本地模型已被禁用。强制回退到 online。")
            engine_type = "online"
            
        # 发送切换中状态
        self.status_changed.emit("正在切换模型，请稍等")
        
        # 卸载旧引擎
        if self._engine: 
            log_translator("卸载旧引擎...")
            self._engine.unload()
            self._engine = None
        
        # 切换到在线引擎
        if engine_type == "online":
            self.mode = "online"
            self._current_engine_type = "online"
            self.local_is_ready = False
            log_translator("已切换到 Google 在线翻译")
            self.status_changed.emit("idle")
            return
        
        # 切换到本地引擎
        try:
            model_path = self.config.get_translator_model_path(engine_type)
            log_translator(f"本地模型路径: {model_path}")
            
            if not model_path:
                log_translator("模型路径为空，切换失败")
                self.mode = "online"
                self.local_is_ready = False
                self.status_changed.emit("本地模型未找到，已回退到在线翻译")
                return
            
            self._engine = CT2TranslatorEngine()
            if self._engine.load(model_path):
                self.local_is_ready = True
                self.mode = "local"
                self._current_engine_type = engine_type
                log_translator("本地引擎加载成功")
                self.status_changed.emit("翻译模型准备就绪")
            else:
                log_translator("本地引擎加载失败")
                self._engine = None
                self.mode = "online"
                self.local_is_ready = False
                self.status_changed.emit("本地引擎启动失败，已回退到在线翻译")
                
        except Exception as e:
            log_translator(f"switch_engine 异常: {e}")
            traceback.print_exc()
            self.mode = "online"
            self.local_is_ready = False
            self.status_changed.emit(f"切换失败: {str(e)}")

    def translate(self, text: str) -> str:
        if not text: 
            return ""
        if self.mode == "local" and self.local_is_ready and self._engine:
            return self._engine.translate(text)
        return self._online_engine.translate(text)

    def cleanup(self):
        if self._engine: 
            self._engine.unload()


class TranslationWorker(QObject):
    result_ready = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    def __init__(self, engine: TranslatorEngine):
        super().__init__()
        self.engine = engine
        self.engine.status_changed.connect(self.status_changed.emit)
        
    @pyqtSlot(str)
    def on_translate_requested(self, text: str): 
        self.result_ready.emit(self.engine.translate(text))
        
    @pyqtSlot(str)
    def on_engine_change_requested(self, engine_id: str): 
        self.engine.switch_engine(engine_id)
