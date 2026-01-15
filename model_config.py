"""
模型配置管理模块
管理 ASR 和翻译模型的配置、路径、可用性检测

重要：所有路径检测在运行时通过辅助函数完成，而非类级别属性
"""

import os
import sys
import zipfile
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List


class ASREngineType(Enum):
    """ASR引擎类型 (目前仅支持内置 Sherpa 版)"""
    SENSEVOICE_ONNX = "sensevoice_onnx"


class ASROutputMode(Enum):
    """ASR输出模式 (目前默认原始输出即可，Sherpa 自带标点)"""
    RAW = "raw"
    CLEANED = "cleaned"


class EmojiMode(Enum):
    """Emoji 模式"""
    OFF = "off"
    AUTO = "auto"       # 自动根据语气添加
    TRIGGER = "trigger" # 仅通过语音触发

class TranslatorEngineType(Enum):
    """翻译引擎类型"""
    NLLB_1_2B_CT2 = "nllb_1_2b_ct2"     # 1.2B高质量版(ctranslate2)
    NLLB_600M_CT2 = "nllb_600m_ct2"     # 600M标准版(ctranslate2)
    NLLB_ORIGINAL = "nllb_original"     # 原始版(transformers)
    GOOGLE = "online"                   # Google 在线翻译


@dataclass
class ModelInfo:
    """模型信息数据类"""
    name: str           # 显示名称
    path: str           # 模型路径（文件夹名）
    engine_type: str    # 引擎类型枚举值
    loader: str         # 加载方式
    is_zip: bool = False # 是否为压缩包
    available: bool = False # 是否可用


# ===== 运行时路径检测辅助函数 =====

def get_exe_dir() -> str:
    """获取 EXE 所在目录（打包后）或脚本目录（开发时）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_internal_dir() -> str:
    """获取 _internal 目录（打包后资源所在位置）"""
    if getattr(sys, 'frozen', False):
        exe_dir = get_exe_dir()
        # PyInstaller 默认把资源放在 _internal 文件夹
        internal = os.path.join(exe_dir, "_internal")
        if os.path.exists(internal):
            return internal
        # 回退到 _MEIPASS（某些 PyInstaller 配置）
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return meipass
        return exe_dir
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_bundled_models_dir() -> str:
    """获取内置模型目录"""
    internal = get_internal_dir()
    models_dir = os.path.join(internal, "models")
    return models_dir


def get_data_dir() -> str:
    """获取数据存储目录（需要写权限）"""
    exe_dir = get_exe_dir()
    
    # 检查 EXE 目录是否可写
    is_writable = False
    try:
        test_file = os.path.join(exe_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('1')
        os.remove(test_file)
        is_writable = True
    except:
        pass

    if is_writable:
        return exe_dir
    else:
        # 使用 LOCALAPPDATA
        app_data = os.environ.get('LOCALAPPDATA', os.environ.get('APPDATA', os.path.expanduser('~')))
        data_root = os.path.join(app_data, "CNJP_Input")
        os.makedirs(data_root, exist_ok=True)
        return data_root


def get_prompts_path() -> str:
    """获取 prompts.json 路径"""
    internal = get_internal_dir()
    return os.path.join(internal, "prompts.json")


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
    
    def __init__(self):
        # ===== 运行时初始化所有路径 =====
        self.EXE_DIR = get_exe_dir()
        self.INTERNAL_DIR = get_internal_dir()
        self.DATA_DIR = get_data_dir()
        self.BUNDLED_MODELS_DIR = get_bundled_models_dir()
        self.MODELS_DIR = os.path.join(self.DATA_DIR, "models")
        self.CONFIG_PATH = os.path.join(self.DATA_DIR, "config.json")
        self.PROMPTS_PATH = get_prompts_path()
        
        # 确保目录存在
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.MODELS_DIR, exist_ok=True)
        
        # ===== 模型定义 =====
        self.ASR_MODELS: Dict[str, ModelInfo] = {
            ASREngineType.SENSEVOICE_ONNX.value: ModelInfo(
                name="内置 AI 语音引擎", 
                path="sensevoice_sherpa",
                engine_type=ASREngineType.SENSEVOICE_ONNX.value,
                loader="sherpa_onnx",
                is_zip=False,
                available=True
            )
        }
        
        self.TRANSLATOR_MODELS: Dict[str, ModelInfo] = {
            TranslatorEngineType.NLLB_600M_CT2.value: ModelInfo(
                name="NLLB-200 600M (标准)",
                path="nllb_600m_v1",
                engine_type=TranslatorEngineType.NLLB_600M_CT2.value,
                loader="ctranslate2",
                is_zip=False
            ),
            TranslatorEngineType.GOOGLE.value: ModelInfo(
                name="Google 在线翻译 (推荐/快速)",
                path="",
                engine_type=TranslatorEngineType.GOOGLE.value,
                loader="online",
                available=True
            ),
        }
        
        # ===== 配置属性 =====
        self._current_asr_engine = ASREngineType.SENSEVOICE_ONNX.value
        self._current_translator_engine = TranslatorEngineType.GOOGLE.value
        self._asr_output_mode = ASROutputMode.RAW.value
        self._hotkey_asr = "ctrl+windows"
        self._hotkey_toggle_ui = "alt+windows"
        self._auto_tts = True
        self._tts_delay_ms = 0
        self._wizard_completed = True
        self._theme_mode = "Dark"
        self._window_scale = 1.0
        self._font_name = "思源宋体"
        self._app_mode = "asr"
        self._tip_shown = False
        self._show_on_start = True
        self._window_x = -1 # -1 表示初次启动
        self._window_y = -1
        self.data = {}
        
        # ===== 日志和初始化 =====
        self._log_paths()
        
        is_first_run = not os.path.exists(self.CONFIG_PATH)
        self._load_config()
        
        if is_first_run:
            from startup_manager import StartupManager
            StartupManager.enable()
            self._show_on_start = True
            self.save_config()
            
        self._scan_models()
        self.personality = PersonalityManager(self.PROMPTS_PATH)
    
    def _log_paths(self):
        """记录路径调试信息"""
        try:
            log_path = os.path.join(self.DATA_DIR, "model_debug.log")
            with open(log_path, "a", encoding="utf-8") as f:
                import time
                f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                f.write(f"sys.frozen: {getattr(sys, 'frozen', False)}\n")
                f.write(f"sys.executable: {sys.executable}\n")
                f.write(f"EXE_DIR: {self.EXE_DIR}\n")
                f.write(f"INTERNAL_DIR: {self.INTERNAL_DIR}\n")
                f.write(f"DATA_DIR: {self.DATA_DIR}\n")
                f.write(f"BUNDLED_MODELS_DIR: {self.BUNDLED_MODELS_DIR}\n")
                f.write(f"BUNDLED_MODELS_DIR exists: {os.path.exists(self.BUNDLED_MODELS_DIR)}\n")
                if os.path.exists(self.BUNDLED_MODELS_DIR):
                    try:
                        f.write(f"Contents: {os.listdir(self.BUNDLED_MODELS_DIR)}\n")
                    except: pass
                f.write(f"MODELS_DIR (user): {self.MODELS_DIR}\n")
                f.write(f"CONFIG_PATH: {self.CONFIG_PATH}\n")
        except: pass
    
    def _load_config(self):
        try:
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                    self._current_asr_engine = ASREngineType.SENSEVOICE_ONNX.value
                    # [MODIFIED] Force online engine, ignore saved NLLB setting
                    self._current_translator_engine = TranslatorEngineType.GOOGLE.value
                    # self._current_translator_engine = self.data.get('translator_engine', self._current_translator_engine)
                    self._asr_output_mode = self.data.get('asr_output_mode', self._asr_output_mode)
                    self._emoji_mode = self.data.get('emoji_mode', "off") # string: off, auto, trigger
                    self._hotkey_asr = self.data.get('hotkey_asr', self._hotkey_asr)
                    self._hotkey_toggle_ui = self.data.get('hotkey_toggle_ui', self._hotkey_toggle_ui)
                    self._auto_tts = self.data.get('auto_tts', self._auto_tts)
                    self._tts_delay_ms = self.data.get('tts_delay_ms', self._tts_delay_ms)
                    self._wizard_completed = True 
                    self._theme_mode = self.data.get('theme_mode', self._theme_mode)
                    self._window_scale = self.data.get('window_scale', self._window_scale)
                    self._font_name = self.data.get('font_name', self._font_name)
                    self._app_mode = self.data.get('app_mode', self._app_mode)
                    self._tip_shown = self.data.get('tip_shown', self._tip_shown)
                    self._show_on_start = self.data.get('show_on_start', self._show_on_start)
                    self._window_x = self.data.get('window_x', -1)
                    self._window_y = self.data.get('window_y', -1)
        except Exception as e:
            try:
                log_path = os.path.join(self.DATA_DIR, "error.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[_load_config] {e}\n")
            except: pass
        
        # 加载学习到的规则 (额外文件，不污染主配置)
        self.learned_rules_path = os.path.join(self.DATA_DIR, "learned_rules.json")
        self.learned_no_period_words = {} # 词 -> 拒绝次数
        self.learned_force_period_words = {} # 词 -> 强制次数
        
        if os.path.exists(self.learned_rules_path):
            try:
                with open(self.learned_rules_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 兼容旧格式（直接是dict）和新格式（{no_period:..., force_period:...}）
                    if "no_period" in data:
                        self.learned_no_period_words = data["no_period"]
                        self.learned_force_period_words = data.get("force_period", {})
                    else:
                        self.learned_no_period_words = data
            except: pass

    def save_config(self):
        """保存当前配置到文件"""
        data = {
            "app_mode": self._app_mode,
            "window_scale": self._window_scale,
            "theme_mode": self._theme_mode,
            "font_name": self._font_name,
            "asr_engine": self._current_asr_engine,
            "asr_output_mode": self._asr_output_mode,
            "emoji_mode": self.emoji_mode, # 新增
            "translator_engine": self._current_translator_engine,
            "hotkey_asr": self._hotkey_asr,
            "hotkey_toggle_ui": self._hotkey_toggle_ui,
            "auto_tts": self._auto_tts,
            "tts_delay_ms": self._tts_delay_ms,
            "wizard_completed": True,
            "tip_shown": self._tip_shown,
            "show_on_start": self._show_on_start
        }
        
        # The instruction's save_config included 'font_size_factor' and 'personality_scheme.name'
        # which are not defined in the provided ModelConfig. I've omitted them to maintain
        # syntactic correctness and avoid AttributeError.
        # The original save_config used self.data, but the new one constructs a dict.
        # I'm following the new instruction's structure.

        # 保存窗口位置 (如果存在)
        if hasattr(self, "_window_x"): data["window_x"] = self._window_x
        if hasattr(self, "_window_y"): data["window_y"] = self._window_y

        try:
            with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            try:
                log_path = os.path.join(self.DATA_DIR, "error.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[save_config] {e}\n")
            except: pass
            
    def learn_no_period_rule(self, word: str):
        """
        学习不加句号的规则
        当检测到用户删除了某个词后面的句号时调用
        """
        if not word: return
        count = self.learned_no_period_words.get(word, 0) + 1
        self.learned_no_period_words[word] = count
        
        # 立即保存
        self.save_learned_rules()
            
    def learn_force_period_rule(self, word: str):
        """
        学习强制加句号的规则
        当检测到用户手动补充了句号时调用
        """
        if not word: return
        # 如果之前在"不加句号"的名单里，先移除
        if word in self.learned_no_period_words:
            del self.learned_no_period_words[word]
            
        count = self.learned_force_period_words.get(word, 0) + 1
        self.learned_force_period_words[word] = count
        
        self.save_learned_rules()

    def save_learned_rules(self):
        try:
            data = {
                "no_period": self.learned_no_period_words,
                "force_period": self.learned_force_period_words
            }
            with open(self.learned_rules_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[Learning] Rules saved.")
        except Exception as e:
            print(f"[Learning] Save error: {e}")
            
    def get_learned_markers_regex(self) -> str:
        """获取所有学习到的（达到阈值的）不加句号的词，组合成正则"""
        threshold = 1 
        words = [w for w, c in self.learned_no_period_words.items() if c >= threshold]
        if not words: return ""
        escaped_words = [re.escape(w) for w in words]
        return "|".join(escaped_words)

    def get_learned_force_period_regex(self) -> str:
        """获取所有学习到的（达到阈值的）强制加句号的词，组合成正则"""
        threshold = 1
        words = [w for w, c in self.learned_force_period_words.items() if c >= threshold]
        if not words: return ""
        escaped_words = [re.escape(w) for w in words]
        return "|".join(escaped_words)

    @property
    def emoji_mode(self) -> str: 
        return getattr(self, '_emoji_mode', "off")
    @emoji_mode.setter
    def emoji_mode(self, value: str):
        self._emoji_mode = value
        self.save_config()
    
    def _scan_models(self):
        """扫描所有可用模型"""
        self.ASR_MODELS[ASREngineType.SENSEVOICE_ONNX.value].available = True
        
        for key, model in self.TRANSLATOR_MODELS.items():
            if model.loader == "online":
                model.available = True
                continue
                
            # [MODIFIED] Disable all local NLLB scanning
            if "nllb" in key:
                model.available = False
                continue

            found = False
            found_path = None
            
            # Skip actual file check for disabled models
            # for root in [self.MODELS_DIR, self.BUNDLED_MODELS_DIR]: ... (skipped)
        
        # 扫描 ASR 模型
        asr_model = self.ASR_MODELS[ASREngineType.SENSEVOICE_ONNX.value]
        asr_found = False
        asr_path = None
        for root in [self.MODELS_DIR, self.BUNDLED_MODELS_DIR]:
            if not root or not os.path.exists(root):
                continue
            folder_path = os.path.join(root, asr_model.path)
            if os.path.isdir(folder_path):
                # 检查模型文件
                model_file = os.path.join(folder_path, "model.int8.onnx")
                if not os.path.exists(model_file):
                    model_file = os.path.join(folder_path, "model.onnx")
                if os.path.exists(model_file):
                    asr_found = True
                    asr_path = folder_path
                    break
        
        asr_model.available = asr_found
        
        try:
            log_path = os.path.join(self.DATA_DIR, "model_debug.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"ASR sensevoice_onnx: available={asr_found}, path={asr_path}\n")
        except: pass
    
    def _find_model_path(self, model_folder_name: str) -> Optional[str]:
        """在所有可能的位置查找模型文件夹"""
        for root in [self.MODELS_DIR, self.BUNDLED_MODELS_DIR]:
            if not root or not os.path.exists(root):
                continue
            folder_path = os.path.join(root, model_folder_name)
            if os.path.isdir(folder_path):
                return folder_path
        return None
    
    def ensure_model_extracted(self, engine_type: str) -> Optional[str]:
        """确保模型已解压并返回路径"""
        model = self.TRANSLATOR_MODELS.get(engine_type) or self.ASR_MODELS.get(engine_type)
        if not model: 
            return None
        
        # 直接查找文件夹
        found_path = self._find_model_path(model.path)
        if found_path:
            return found_path
        
        # 如果是 zip 文件，尝试解压（主要用于用户下载的情况）
        if model.is_zip:
            for root in [self.MODELS_DIR, self.BUNDLED_MODELS_DIR]:
                if not root:
                    continue
                zip_path = os.path.join(root, model.path + ".zip")
                if os.path.exists(zip_path):
                    target_path = os.path.join(self.MODELS_DIR, model.path)
                    if not os.path.exists(target_path):
                        try:
                            os.makedirs(self.MODELS_DIR, exist_ok=True)
                            with zipfile.ZipFile(zip_path, 'r') as zf:
                                zf.extractall(target_path)
                        except:
                            return None
                    return target_path
        
        return None

    def get_model_path(self, engine_type: str) -> Optional[str]:
        return self.ensure_model_extracted(engine_type)
    
    @property
    def current_asr_engine(self) -> str: 
        return self._current_asr_engine
    
    @current_asr_engine.setter
    def current_asr_engine(self, value: str): 
        pass
    
    def get_asr_model_path(self) -> Optional[str]:
        return self.get_model_path(ASREngineType.SENSEVOICE_ONNX.value)
    
    @property
    def current_translator_engine(self) -> str: 
        return self._current_translator_engine
    
    @current_translator_engine.setter
    def current_translator_engine(self, value: str):
        if value in self.TRANSLATOR_MODELS:
            self._current_translator_engine = value
            self.save_config()
    
    def get_translator_model_path(self, engine_type: str = None) -> Optional[str]:
        engine = engine_type or self._current_translator_engine
        return self.get_model_path(engine)
    
    @property
    def asr_output_mode(self) -> str: 
        return self._asr_output_mode
    
    @asr_output_mode.setter
    def asr_output_mode(self, value: str):
        if value in [m.value for m in ASROutputMode]:
            self._asr_output_mode = value
            self.save_config()

    @property
    def hotkey_asr(self) -> str: 
        return self._hotkey_asr
    @hotkey_asr.setter
    def hotkey_asr(self, value: str):
        self._hotkey_asr = value
        self.save_config()

    @property
    def hotkey_toggle_ui(self) -> str: 
        return self._hotkey_toggle_ui
    @hotkey_toggle_ui.setter
    def hotkey_toggle_ui(self, value: str):
        self._hotkey_toggle_ui = value
        self.save_config()

    @property
    def auto_tts(self) -> bool: 
        return self._auto_tts
    @auto_tts.setter
    def auto_tts(self, value: bool):
        self._auto_tts = value
        self.save_config()

    @property
    def tts_delay_ms(self) -> int: 
        return getattr(self, '_tts_delay_ms', 5000)
    @tts_delay_ms.setter
    def tts_delay_ms(self, value: int):
        self._tts_delay_ms = max(0, int(value))
        self.save_config()

    @property
    def theme_mode(self) -> str: 
        return self._theme_mode
    @theme_mode.setter
    def theme_mode(self, value: str):
        self._theme_mode = value
        self.save_config()

    @property
    def window_scale(self) -> float: 
        return float(self._window_scale)
    @window_scale.setter
    def window_scale(self, value: float):
        self._window_scale = float(value)
        self.save_config()

    @property
    def font_name(self) -> str: 
        return self._font_name
    @font_name.setter
    def font_name(self, value: str):
        self._font_name = value
        self.save_config()

    @property
    def wizard_completed(self) -> bool: 
        return True
    @wizard_completed.setter
    def wizard_completed(self, value: bool): 
        pass

    @property
    def app_mode(self) -> str: 
        return self._app_mode
    @app_mode.setter
    def app_mode(self, value: str):
        self._app_mode = value
        self.save_config()

    @property
    def tip_shown(self) -> bool: 
        return self._tip_shown
    @tip_shown.setter
    def tip_shown(self, value: bool):
        self._tip_shown = value
        self.save_config()

    def get_show_on_start(self) -> bool: 
        return self._show_on_start
    def set_show_on_start(self, value: bool):
        self._show_on_start = value
        self.save_config()

    def get_available_translator_engines(self) -> List[ModelInfo]:
        return [m for m in self.TRANSLATOR_MODELS.values() if m.available]
    
    def get_prompt(self, key) -> str: 
        return self.personality.get_prompt(key)
    def set_personality_scheme(self, scheme_id): 
        self.personality.set_scheme(scheme_id)
    def get_personality_schemes(self): 
        return self.personality.get_all_schemes()
    def is_placeholder_text(self, text): 
        return self.personality.is_any_placeholder(text)

    @property
    def window_pos(self) -> tuple:
        return (getattr(self, '_window_x', -1), getattr(self, '_window_y', -1))

    def set_window_pos(self, x: int, y: int):
        self._window_x = x
        self._window_y = y
        self.save_config()


# ===== 全局单例 =====
_model_config_instance: Optional[ModelConfig] = None

def get_model_config() -> ModelConfig:
    global _model_config_instance
    if _model_config_instance is None:
        _model_config_instance = ModelConfig()
    return _model_config_instance
