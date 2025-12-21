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


# 模型定义
MODELS = {
    "sensevoice_onnx": ModelInfo(
        id="sensevoice_onnx",
        name="SenseVoice 语音识别模型",
        description="阿里达摩院开源的多语言语音识别模型，支持中日英韩粤语",
        size_mb=156,
        required=True,
        target_dir="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
        mirrors=[
            # HuggingFace 镜像站（中国可访问）
            "https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/model.int8.onnx",
            # 官方 HuggingFace
            "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/model.int8.onnx",
        ]
    ),
    "nllb_600m": ModelInfo(
        id="nllb_600m",
        name="NLLB 翻译模型 (600M)",
        description="Meta开源的多语言翻译模型，支持离线中日翻译",
        size_mb=578,
        required=False,
        target_dir="nllb-200_600M_int8_ct2",
        mirrors=[]
    ),
    "nllb_1_2b": ModelInfo(
        id="nllb_1_2b",
        name="NLLB 翻译模型 (1.2B)",
        description="更高质量的翻译模型",
        size_mb=1200,
        required=False,
        target_dir="nllb-200_1.2B_int8_ct2",
        mirrors=[]
    ),
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
    
    def is_model_installed(self, model_id: str) -> bool:
        """检查模型是否已安装"""
        if model_id not in MODELS:
            return False
        
        model = MODELS[model_id]
        target_path = os.path.join(self.models_dir, model.target_dir)
        
        # 检查目录是否存在
        if os.path.isdir(target_path):
            # 递归查找是否有模型文件
            for root, dirs, files in os.walk(target_path):
                for f in files:
                    if f.endswith(('.onnx', '.bin', '.model')):
                        return True
        
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
        """
        下载指定模型
        
        Args:
            model_id: 模型ID
            progress_callback: 进度回调 (downloaded_bytes, total_bytes, speed_str)
            status_callback: 状态回调 (status, message)
        
        Returns:
            是否下载成功
        """
        if model_id not in MODELS:
            if status_callback:
                status_callback(DownloadStatus.FAILED, f"未知模型: {model_id}")
            return False
        
        model = MODELS[model_id]
        
        if not model.mirrors:
            if status_callback:
                status_callback(DownloadStatus.FAILED, "无可用下载源")
            return False
        
        self._cancel_flag.clear()
        
        # 尝试每个镜像源
        for i, url in enumerate(model.mirrors):
            if self._cancel_flag.is_set():
                if status_callback:
                    status_callback(DownloadStatus.CANCELLED, "下载已取消")
                return False
            
            if status_callback:
                status_callback(DownloadStatus.DOWNLOADING, f"尝试下载源 {i+1}/{len(model.mirrors)}")
            
            try:
                success = self._download_file(url, model, progress_callback, status_callback)
                if success:
                    if status_callback:
                        status_callback(DownloadStatus.COMPLETED, "下载完成")
                    return True
            except Exception as e:
                print(f"[Downloader] Mirror {i+1} failed: {e}")
                continue
        
        if status_callback:
            status_callback(DownloadStatus.FAILED, "所有下载源均失败")
        return False
    
    def _download_file(
        self,
        url: str,
        model: ModelInfo,
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None
    ) -> bool:
        """从指定URL下载文件"""
        
        # 确定文件名
        filename = url.split("/")[-1]
        if not filename:
            filename = f"{model.id}_download"
        
        # 临时文件路径
        temp_path = os.path.join(self.models_dir, f".{filename}.tmp")
        target_dir = os.path.join(self.models_dir, model.target_dir)
        
        try:
            # 发起请求
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            last_time = 0
            speed_samples = []
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._cancel_flag.is_set():
                        return False
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 计算速度
                        import time
                        current_time = time.time()
                        if last_time > 0:
                            speed = len(chunk) / (current_time - last_time)
                            speed_samples.append(speed)
                            if len(speed_samples) > 10:
                                speed_samples.pop(0)
                        last_time = current_time
                        
                        # 回调进度
                        if progress_callback:
                            avg_speed = sum(speed_samples) / len(speed_samples) if speed_samples else 0
                            speed_str = self._format_speed(avg_speed)
                            progress_callback(downloaded, total_size, speed_str)
            
            # 处理下载的文件
            if status_callback:
                status_callback(DownloadStatus.EXTRACTING, "正在解压...")
            
            os.makedirs(target_dir, exist_ok=True)
            
            if filename.endswith('.zip'):
                with zipfile.ZipFile(temp_path, 'r') as zf:
                    zf.extractall(target_dir)
            elif filename.endswith(('.tar.bz2', '.tar.gz', '.tar')):
                with tarfile.open(temp_path, 'r:*') as tf:
                    tf.extractall(target_dir)
            else:
                # 单文件，直接移动
                import shutil
                final_path = os.path.join(target_dir, filename)
                shutil.move(temp_path, final_path)
                return True
            
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return True
            
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
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
    
    @staticmethod
    def _format_size(size: int) -> str:
        """格式化大小显示"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size/1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size/1024/1024:.1f} MB"
        else:
            return f"{size/1024/1024/1024:.2f} GB"


# 全局实例
_downloader = None

def get_downloader() -> ModelDownloader:
    global _downloader
    if _downloader is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        models_dir = os.path.join(base_dir, "models")
        _downloader = ModelDownloader(models_dir)
    return _downloader
