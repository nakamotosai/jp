"""
模型配置管理模块
管理所有ASR和翻译模型的配置、路径、可用性检测和ZIP解压
"""

import os
import zipfile
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List


class ASREngineType(Enum):
    """ASR引擎类型"""
    SENSEVOICE_ONNX = "sensevoice_onnx"      # 轻量ONNX版(默认)
    SENSEVOICE_PYTORCH = "sensevoice_pytorch" # 全量PyTorch版


class ASROutputMode(Enum):
    """ASR输出模式"""
    RAW = "raw"         # 原始输出
    CLEANED = "cleaned" # 清理后输出


class TranslatorEngineType(Enum):
    """翻译引擎类型"""
    NLLB_1_2B_CT2 = "nllb_1_2b_ct2"     # 1.2B高质量版(ctranslate2)
    NLLB_600M_CT2 = "nllb_600m_ct2"     # 600M标准版(ctranslate2)
    NLLB_ORIGINAL = "nllb_original"     # 原始版(transformers)


@dataclass
class ModelInfo:
    """模型信息数据类"""
    name: str           # 显示名称
    path: str           # 模型路径
    engine_type: str    # 引擎类型枚举值
    loader: str         # 加载方式: "funasr_onnx", "funasr", "ctranslate2", "transformers"
    is_zip: bool = False # 是否为压缩包
    available: bool = False # 是否可用

class PersonalityManager:
    """个性化提示词管理类"""
    def __init__(self, config_path):
        self.config_path = config_path
        self.data = {"schemes": [], "current_scheme": "default"}
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except: pass

    def save(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except: pass

    @property
    def current_scheme(self):
        sid = self.data.get("current_scheme", "default")
        for s in self.data["schemes"]:
            if s["id"] == sid: return s
        return self.data["schemes"][0] if self.data["schemes"] else None

    def get_prompt(self, key):
        scheme = self.current_scheme
        return scheme["prompts"].get(key, "") if scheme else ""

    def set_scheme(self, scheme_id):
        self.data["current_scheme"] = scheme_id
        self.save()

    def get_all_schemes(self):
        return [(s["id"], s["name"]) for s in self.data["schemes"]]

    def is_any_placeholder(self, text):
        if not text: return True
        for s in self.data["schemes"]:
            if text in s["prompts"].values(): return True
        return False


class ModelConfig:
    """模型配置管理器"""
    
    # 模型基础目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    MODELS_DIR = os.path.join(BASE_DIR, "models")
    CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
    PROMPTS_PATH = os.path.join(BASE_DIR, "prompts.json")
    
    # ASR模型定义
    ASR_MODELS: Dict[str, ModelInfo] = {
        ASREngineType.SENSEVOICE_ONNX.value: ModelInfo(
            name="SenseVoice-Sherpa (ONNX/标点支持)", 
            path="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
            engine_type=ASREngineType.SENSEVOICE_ONNX.value,
            loader="sherpa_onnx",
            available=True
        ),
        ASREngineType.SENSEVOICE_PYTORCH.value: ModelInfo(
            name="SenseVoiceSmall (全量/备用)",
            path="SenseVoiceSmall",
            engine_type=ASREngineType.SENSEVOICE_PYTORCH.value,
            loader="funasr"
        ),
    }
    
    # 翻译模型定义
    TRANSLATOR_MODELS: Dict[str, ModelInfo] = {
        TranslatorEngineType.NLLB_1_2B_CT2.value: ModelInfo(
            name="NLLB-200 1.2B (高质量)",
            path="nllb-200_1.2B_int8_ct2.zip",
            engine_type=TranslatorEngineType.NLLB_1_2B_CT2.value,
            loader="ctranslate2",
            is_zip=True
        ),
        TranslatorEngineType.NLLB_600M_CT2.value: ModelInfo(
            name="NLLB-200 600M (标准)",
            path="nllb-200_600M_int8_ct2.zip",
            engine_type=TranslatorEngineType.NLLB_600M_CT2.value,
            loader="ctranslate2",
            is_zip=True
        ),
        TranslatorEngineType.NLLB_ORIGINAL.value: ModelInfo(
            name="NLLB-200 Original (原始)",
            path="nllb-200-distilled-600M",
            engine_type=TranslatorEngineType.NLLB_ORIGINAL.value,
            loader="transformers"
        ),
    }
    
    def __init__(self):
        self._current_asr_engine = ASREngineType.SENSEVOICE_ONNX.value  # 使用 Sherpa-ONNX 默认
        self._current_translator_engine = TranslatorEngineType.NLLB_600M_CT2.value
        self._asr_output_mode = ASROutputMode.RAW.value
        self.data = {}
        self._load_config()
        self._scan_models()
        self.personality = PersonalityManager(self.PROMPTS_PATH)
    
    def _load_config(self):
        """从config.json加载配置"""
        try:
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                    self._current_asr_engine = self.data.get('asr_engine', self._current_asr_engine)
                    self._current_translator_engine = self.data.get('translator_engine', self._current_translator_engine)
                    self._asr_output_mode = self.data.get('asr_output_mode', self._asr_output_mode)
        except Exception as e:
            print(f"[ModelConfig] 加载配置失败: {e}")
    
    def save_config(self):
        """保存配置到config.json"""
        try:
            config = {}
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            config['asr_engine'] = self._current_asr_engine
            config['translator_engine'] = self._current_translator_engine
            config['asr_output_mode'] = self._asr_output_mode
            
            with open(self.CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ModelConfig] 保存配置失败: {e}")
    
    def _scan_models(self):
        """扫描模型目录，检测模型可用性"""
        # 扫描ASR模型
        for key, model in self.ASR_MODELS.items():
            full_path = os.path.join(self.MODELS_DIR, model.path)
            model.available = os.path.exists(full_path)
        
        # 扫描翻译模型
        for key, model in self.TRANSLATOR_MODELS.items():
            if model.is_zip:
                zip_path = os.path.join(self.MODELS_DIR, model.path)
                extracted_path = self._get_extracted_path(model.path)
                # ZIP存在或已解压目录存在都算可用
                model.available = os.path.exists(zip_path) or os.path.exists(extracted_path)
            else:
                full_path = os.path.join(self.MODELS_DIR, model.path)
                model.available = os.path.exists(full_path)
    
    def _get_extracted_path(self, zip_filename: str) -> str:
        """获取解压后的目录路径"""
        # 去掉.zip后缀作为目录名
        dir_name = zip_filename.replace('.zip', '')
        return os.path.join(self.MODELS_DIR, dir_name)
    
    def ensure_model_extracted(self, engine_type: str) -> Optional[str]:
        """
        确保模型已解压（如果是ZIP格式）
        返回模型的实际路径（处理嵌套目录的情况）
        """
        # 查找模型信息
        model = None
        if engine_type in self.TRANSLATOR_MODELS:
            model = self.TRANSLATOR_MODELS[engine_type]
        elif engine_type in self.ASR_MODELS:
            model = self.ASR_MODELS[engine_type]
        
        if not model:
            return None
        
        full_path = os.path.join(self.MODELS_DIR, model.path)
        
        if not model.is_zip:
            return full_path if os.path.exists(full_path) else None
        
        # 处理ZIP文件
        extracted_path = self._get_extracted_path(model.path)
        
        # 检查解压后的实际模型路径
        actual_model_path = self._find_actual_model_path(extracted_path)
        if actual_model_path:
            print(f"[ModelConfig] 模型已解压: {actual_model_path}")
            return actual_model_path
        
        # 需要解压
        zip_path = full_path
        if not os.path.exists(zip_path):
            print(f"[ModelConfig] ZIP文件不存在: {zip_path}")
            return None
        
        print(f"[ModelConfig] 正在解压模型: {zip_path}")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extracted_path)
            print(f"[ModelConfig] 解压完成: {extracted_path}")
            
            # 返回实际的模型路径（处理嵌套）
            return self._find_actual_model_path(extracted_path) or extracted_path
        except Exception as e:
            print(f"[ModelConfig] 解压失败: {e}")
            return None
    
    def _find_actual_model_path(self, extracted_path: str) -> Optional[str]:
        """
        查找实际的模型路径
        处理ZIP解压后可能存在的嵌套目录结构
        """
        if not os.path.exists(extracted_path):
            return None
        
        # 检查是否包含model.bin（ctranslate2模型标志）
        if os.path.exists(os.path.join(extracted_path, "model.bin")):
            return extracted_path
        
        # 检查是否包含sentencepiece.model（也是CT2模型的标志）
        if os.path.exists(os.path.join(extracted_path, "sentencepiece.model")):
            return extracted_path
        
        # 检查嵌套目录
        items = os.listdir(extracted_path)
        subdirs = [d for d in items if os.path.isdir(os.path.join(extracted_path, d))]
        
        # 如果只有一个子目录，检查其中是否有model.bin
        if len(subdirs) == 1:
            nested_path = os.path.join(extracted_path, subdirs[0])
            if os.path.exists(os.path.join(nested_path, "model.bin")):
                return nested_path
            if os.path.exists(os.path.join(nested_path, "sentencepiece.model")):
                return nested_path
        
        # 没有找到有效的模型目录，但目录存在
        if os.path.isdir(extracted_path):
            return extracted_path
        
        return None
    
    def get_model_path(self, engine_type: str) -> Optional[str]:
        """获取模型的完整路径（自动处理ZIP解压）"""
        return self.ensure_model_extracted(engine_type)
    
    # === ASR引擎设置 ===
    
    @property
    def current_asr_engine(self) -> str:
        return self._current_asr_engine
    
    @current_asr_engine.setter
    def current_asr_engine(self, value: str):
        if value in self.ASR_MODELS:
            self._current_asr_engine = value
            self.save_config()
    
    def get_asr_model_info(self, engine_type: str = None) -> Optional[ModelInfo]:
        """获取ASR模型信息"""
        engine = engine_type or self._current_asr_engine
        return self.ASR_MODELS.get(engine)
    
    def get_asr_model_path(self, engine_type: str = None) -> Optional[str]:
        """获取ASR模型路径"""
        engine = engine_type or self._current_asr_engine
        model = self.ASR_MODELS.get(engine)
        if model:
            return os.path.join(self.MODELS_DIR, model.path)
        return None
    
    # === 翻译引擎设置 ===
    
    @property
    def current_translator_engine(self) -> str:
        return self._current_translator_engine
    
    @current_translator_engine.setter
    def current_translator_engine(self, value: str):
        if value in self.TRANSLATOR_MODELS:
            self._current_translator_engine = value
            self.save_config()
    
    def get_translator_model_info(self, engine_type: str = None) -> Optional[ModelInfo]:
        """获取翻译模型信息"""
        engine = engine_type or self._current_translator_engine
        return self.TRANSLATOR_MODELS.get(engine)
    
    def get_translator_model_path(self, engine_type: str = None) -> Optional[str]:
        """获取翻译模型路径（自动处理ZIP解压）"""
        engine = engine_type or self._current_translator_engine
        return self.get_model_path(engine)
    
    # === ASR输出模式 ===
    
    @property
    def asr_output_mode(self) -> str:
        return self._asr_output_mode
    
    @asr_output_mode.setter
    def asr_output_mode(self, value: str):
        if value in [m.value for m in ASROutputMode]:
            self._asr_output_mode = value
            self.save_config()
    
    # === 辅助方法 ===
    
    def get_available_asr_engines(self) -> List[ModelInfo]:
        """获取所有可用的ASR引擎"""
        return [m for m in self.ASR_MODELS.values() if m.available]
    
    def get_available_translator_engines(self) -> List[ModelInfo]:
        """获取所有可用的翻译引擎"""
        return [m for m in self.TRANSLATOR_MODELS.values() if m.available]
    
    def get_prompt(self, key) -> str:
        """获取当前个性化方案的提示词"""
        return self.personality.get_prompt(key)

    def set_personality_scheme(self, scheme_id):
        """设置当前个性化方案"""
        self.personality.set_scheme(scheme_id)

    def get_personality_schemes(self):
        """获取所有可选方案"""
        return self.personality.get_all_schemes()
    
    def is_placeholder_text(self, text):
        """检查文本是否为任何模式下的提示词"""
        return self.personality.is_any_placeholder(text)
    
    def print_status(self):
        """打印模型状态"""
        print("\n=== 模型状态 ===")
        print("ASR模型:")
        for key, model in self.ASR_MODELS.items():
            status = "✓" if model.available else "✗"
            current = "←当前" if key == self._current_asr_engine else ""
            print(f"  [{status}] {model.name} {current}")
        
        print("\n翻译模型:")
        for key, model in self.TRANSLATOR_MODELS.items():
            status = "✓" if model.available else "✗"
            current = "←当前" if key == self._current_translator_engine else ""
            print(f"  [{status}] {model.name} {current}")
        
        print(f"\nASR输出模式: {self._asr_output_mode}")
        print("================\n")


# 全局单例
_model_config_instance: Optional[ModelConfig] = None

def get_model_config() -> ModelConfig:
    """获取模型配置单例"""
    global _model_config_instance
    if _model_config_instance is None:
        _model_config_instance = ModelConfig()
    return _model_config_instance


if __name__ == "__main__":
    # 测试
    config = get_model_config()
    config.print_status()
