import sys
import os
import numpy as np
import time

# Add project root to path
sys.path.append(r"c:\Users\sai\jp")

from model_config import get_model_config
from asr_manager import OnnxASREngine

def test_asr():
    print("=== 开始后台 ASR 引擎测试 ===")
    
    # 1. 获取配置
    config = get_model_config()
    print(f"数据目录: {config.DATA_DIR}")
    
    # 2. 获取模型路径
    engine_type = config.current_asr_engine
    print(f"当前引擎类型: {engine_type}")
    
    model_path = config.get_asr_model_path()
    print(f"模型目标路径: {model_path}")
    
    if not model_path or not os.path.exists(model_path):
        print("错误: 模型路径不存在！无法继续测试。")
        return
        
    # 3. 初始化引擎
    engine = OnnxASREngine()
    print("正在加载模型 (可能需要几秒钟)...")
    
    start_time = time.time()
    success = engine.load(model_path)
    end_time = time.time()
    
    if success:
        print(f"✅ 模型加载成功！耗时: {end_time - start_time:.2f}秒")
        
        # 4. 模拟推理 (生成1秒的静音数据)
        print("正在进行推理测试 (1秒静音)...")
        # 16000Hz, 1秒, float32, 范围 -1.0 到 1.0 (静音为0)
        dummy_audio = np.zeros(16000, dtype=np.float32)
        
        result = engine.transcribe(dummy_audio)
        print(f"推理结果 (应为空或乱码): '{result}'")
        print("✅ 推理调用未崩溃")
        
        engine.unload()
        print("引擎已卸载")
    else:
        print("❌ 模型加载失败")

if __name__ == "__main__":
    test_asr()
