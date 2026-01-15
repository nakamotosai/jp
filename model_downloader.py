"""
模型下载管理器
支持多源下载（HuggingFace镜像站、GitHub、自定义源）
"""
import os
import json
import requests
import threading
import zipfile
import tarfile
import time
from typing import Callable, Optional, Dict, List
from dataclasses import dataclass
from enum import Enum


class DownloadStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str
    description: str
    size_mb: int
    required: bool  # 是否必需
    target_dir: str  # 解压目标目录（相对于models目录）
    mirrors: List[str]  # 下载镜像列表


# 模型定义 - 修正为 resolve 下载直链
MODELS = {
    "sensevoice_onnx": ModelInfo(
        id="sensevoice_onnx",
        name="SenseVoice 语音识别模型",
        description="阿里达摩院开源的多语言语音识别模型，支持中日英韩粤语",
        size_mb=156,
        required=True,
        target_dir="sensevoice_sherpa",
        mirrors=[
            "https://hf-mirror.com/nakamotosai/ai-jp-input-asr/resolve/main/sensevoice_v1.zip",
            "https://huggingface.co/nakamotosai/ai-jp-input-asr/resolve/main/sensevoice_v1.zip",
        ]
    ),
    # "nllb_600m": ModelInfo(
    #     id="nllb_600m",
    #     name="NLLB 翻译模型 (600M)",
    #     description="Meta开源的多语言翻译模型，支持离线中日翻译",
    #     size_mb=578,
    #     required=False,
    #     target_dir="nllb_600m_v1",
    #     mirrors=[
    #         "https://hf-mirror.com/nakamotosai/ai-jp-input-nllb/resolve/main/nllb_600m_v1.zip",
    #         "https://huggingface.co/nakamotosai/ai-jp-input-nllb/resolve/main/nllb_600m_v1.zip",
    #     ]
    # ),
    "punc_ct_transformer": ModelInfo(
        id="punc_ct_transformer",
        name="专业标点恢复模型",
        description="阿里FunASR CT-Transformer 标点恢复模型，大幅提升断句准确性",
        size_mb=45,
        required=False,
        target_dir="punc_ct_transformer",
        mirrors=[
            "https://hf-mirror.com/nakamotosai/ai-jp-input-asr/resolve/main/punc_ct-transformer_zh-cn-common-vocab272727.zip",
            "https://huggingface.co/nakamotosai/ai-jp-input-asr/resolve/main/punc_ct-transformer_zh-cn-common-vocab272727.zip",
        ]
    )
}


class ModelDownloader:
    """模型下载管理器"""
    
    def __init__(self, models_dir: str):
        self.models_dir = models_dir
        self.current_download = None
        self._cancel_flag = threading.Event()
        self._lock = threading.Lock()
        
        # 确保模型目录存在
        os.makedirs(models_dir, exist_ok=True)
    
    
    def log_debug(self, msg: str):
        """记录调试日志"""
        try:
            log_path = os.path.join(self.models_dir, "..", "model_debug.log")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg}\n")
        except:
            pass

    def is_model_installed(self, model_id: str) -> bool:
        """检查模型是否已安装"""
        if model_id not in MODELS:
            self.log_debug(f"Check {model_id}: Not in definition")
            return False
        
        model = MODELS[model_id]
        target_path = os.path.join(self.models_dir, model.target_dir)
        
        # 记录检查路径
        self.log_debug(f"Check {model_id}: Path={target_path}")
        
        if not os.path.exists(target_path):
            self.log_debug(f"Check {model_id}: Dir does not exist")
            return False

        # 1. 直接检查是否存在关键文件
        # NLLB 需要确保 Tokenizer 存在
        if model_id == "nllb_600m":
            tok_path = os.path.join(target_path, "sentencepiece.bpe.model")
            if not os.path.exists(tok_path):
                self.log_debug(f"Check {model_id}: Missing tokenizer {tok_path}")
                return False

        if os.path.exists(os.path.join(target_path, "model.bin")):
            self.log_debug(f"Check {model_id}: Found model.bin directly")
            return True
            
        if os.path.exists(os.path.join(target_path, "encoder_model.onnx")): # SenseVoice
            self.log_debug(f"Check {model_id}: Found ONNX directly")
            return True

        # 2. 遍历检查 (防止解压多了一层目录)
        for root, dirs, files in os.walk(target_path):
            if "model.bin" in files:
                self.log_debug(f"Check {model_id}: Found model.bin in {root}")
                return True
            if any(f.endswith(".onnx") for f in files):
                self.log_debug(f"Check {model_id}: Found .onnx in {root}")
                return True
                
        self.log_debug(f"Check {model_id}: No model files found in {target_path}")
        return False
    
    def get_missing_required_models(self) -> List[ModelInfo]:
        """获取缺失的必需模型"""
        missing = []
        for model_id, model in MODELS.items():
            if model.required and not self.is_model_installed(model_id):
                missing.append(model)
        return missing
    
    def download_model(
        self, 
        model_id: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        status_callback: Optional[Callable[[DownloadStatus, str], None]] = None
    ) -> bool:

        """下载指定模型"""
        if model_id not in MODELS:
            if status_callback:
                status_callback(DownloadStatus.FAILED, f"未知模型: {model_id}")
            return False
        
        model = MODELS[model_id]
        
        if not model.mirrors:
            if status_callback:
                status_callback(DownloadStatus.FAILED, "无可用下载源")
            return False
        
        # 检查是否已安装
        if self.is_model_installed(model_id):
            # 即使已安装，对于NLLB也要检查分词器
            if model_id == "nllb_600m":
                self._ensure_tokenizer(model.target_dir, status_callback)
                
            if status_callback:
                status_callback(DownloadStatus.COMPLETED, "已安装")
            return True

        self._cancel_flag.clear()
        
        # 尝试每个镜像源
        for i, url in enumerate(model.mirrors):
            if self._cancel_flag.is_set():
                if status_callback:
                    status_callback(DownloadStatus.CANCELLED, "下载已取消")
                return False
            
            source_name = "镜像站" if "hf-mirror" in url else "官方源"
            if status_callback:
                status_callback(DownloadStatus.DOWNLOADING, f"正在连接{source_name} ({i+1}/{len(model.mirrors)})...")
            
            print(f"[Downloader] 正在连接: {url}")
            try:
                success = self._download_file(url, model, progress_callback, status_callback)
                if success:
                    # 特殊处理: NLLB需要额外下载tokenizer
                    if model_id == "nllb_600m":
                        self._ensure_tokenizer(model.target_dir, status_callback)

                    if status_callback:
                        status_callback(DownloadStatus.COMPLETED, "安装完成")
                    return True
            except Exception as e:
                print(f"[Downloader] 源 {i+1} 失败: {e}")

                if "404" in str(e):
                    msg = "文件未找到(404)"
                elif "Timeout" in str(e):
                    msg = "连接超时"
                else:
                    msg = "网络连接失败"
                
                if i == len(model.mirrors) - 1: # 最后一个源也失败了
                    if status_callback:
                        status_callback(DownloadStatus.FAILED, msg)
                continue
        
        return False
    
    def _ensure_tokenizer(
        self, 
        target_dir_name: str, 
        status_callback: Optional[Callable] = None
    ):
        """确保NLLB模型的tokenizer存在"""
        target_path = os.path.join(self.models_dir, target_dir_name)
        tokenizer_path = os.path.join(target_path, "sentencepiece.bpe.model")
        
        if os.path.exists(tokenizer_path) and os.path.getsize(tokenizer_path) > 1000:
            return

        urls = [
            "https://hf-mirror.com/facebook/nllb-200-distilled-600M/resolve/main/sentencepiece.bpe.model",
            "https://huggingface.co/facebook/nllb-200-distilled-600M/resolve/main/sentencepiece.bpe.model"
        ]
        
        if status_callback:
            status_callback(DownloadStatus.DOWNLOADING, "正在补全分词器文件...")
            
        for url in urls:
            try:
                print(f"[Downloader] 下载Tokenizer: {url}")
                # 使用简单的requests下载，不需要进度条
                resp = requests.get(url, timeout=30, stream=True)
                resp.raise_for_status()
                
                with open(tokenizer_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"[Downloader] Tokenizer下载成功")
                return
            except Exception as e:
                print(f"[Downloader] Tokenizer下载失败 ({url}): {e}")
                
        # 如果都失败了，记录日志但不阻断流程 (用户可能会手动解决)
        self.log_debug(f"Failed to download tokenizer for {target_dir_name}")

    def _download_file(
        self,
        url: str,
        model: ModelInfo,
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None
    ) -> bool:
        """从指定URL下载文件"""
        
        filename = url.split("/")[-1].split("?")[0]
        if not filename:
            filename = f"{model.id}.zip"
        
        temp_path = os.path.join(self.models_dir, f".{model.id}.tmp")
        target_dir = os.path.join(self.models_dir, model.target_dir)
        
        # 常用的 User-Agent，防止被拦截
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        try:
            # 发起请求
            response = requests.get(url, stream=True, timeout=(10, 60), headers=headers, allow_redirects=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            if total_size == 0:
                # 尝试从模型定义中获取预估大小
                total_size = model.size_mb * 1024 * 1024
                
            downloaded = 0
            start_time = time.time()
            last_report_time = 0
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=32768): # 32KB buffer
                    if self._cancel_flag.is_set():
                        return False
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 降低回调频率，每 0.1 秒回调一次，提高性能
                        curr_time = time.time()
                        if curr_time - last_report_time > 0.1:
                            duration = curr_time - start_time
                            speed = downloaded / duration if duration > 0 else 0
                            speed_str = self._format_speed(speed)
                            if progress_callback:
                                progress_callback(downloaded, total_size, speed_str)
                            last_report_time = curr_time
            
            # 处理下载的文件
            if status_callback:
                status_callback(DownloadStatus.EXTRACTING, "正在解压模型...")
            
            os.makedirs(target_dir, exist_ok=True)
            
            # 如果是 zip
            if zipfile.is_zipfile(temp_path):
                with zipfile.ZipFile(temp_path, 'r') as zf:
                    zf.extractall(target_dir)
            else:
                # 可能是其他格式或者是单文件
                import shutil
                # 如果 URL 包含 .zip 但 requests 下载的不是 zip (可能被拦截成 html 了)
                if ".zip" in url and not zipfile.is_zipfile(temp_path):
                    # 检查文件内容，看是不是 HTML
                    with open(temp_path, 'rb') as f:
                        head = f.read(100)
                        if b"<!DOCTYPE html>" in head or b"<html" in head:
                            raise Exception("下载的文件无效(可能是镜像站拦截页)")
                
                # 直接移动
                shutil.move(temp_path, os.path.join(target_dir, filename))
            
            # 清理
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    print(f"[Downloader] 清理临时文件失败 (可忽略): {e}")
                
            return True
            
        except Exception as e:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            raise e
    
    def cancel_download(self):
        """取消当前下载"""
        self._cancel_flag.set()
    
    @staticmethod
    def _format_speed(speed: float) -> str:
        """格式化速度显示"""
        if speed < 1024:
            return f"{speed:.0f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed/1024:.1f} KB/s"
        else:
            return f"{speed/1024/1024:.1f} MB/s"


# 全局实例
_downloader = None

def get_downloader() -> ModelDownloader:
    global _downloader
    if _downloader is None:
        from model_config import get_model_config
        cfg = get_model_config()
        _downloader = ModelDownloader(cfg.MODELS_DIR)
    return _downloader
