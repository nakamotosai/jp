import sys
import os
import time
import numpy as np

# Add current dir to path
sys.path.append(os.getcwd())

from model_config import get_model_config, ASROutputMode, ASREngineType
from asr_manager import OnnxASREngine

def test_asr():
    print("=== ASR Debug Start ===")
    
    # 1. Config Check
    cfg = get_model_config()
    print(f"Data Dir: {cfg.DATA_DIR}")
    
    # 2. Model Path Check
    print("Scanning models...")
    # Force scan (since it might be cached or lazy)
    cfg._scan_models()
    
    model = cfg.ASR_MODELS[ASREngineType.SENSEVOICE_ONNX.value]
    print(f"ASR Model Available: {model.available}")
    
    model_path = cfg.get_asr_model_path()
    print(f"ASR Model Path: {model_path}")
    
    if not model_path or not os.path.exists(model_path):
        print("ERROR: ASR Model path not found!")
        return
        
    # 3. Engine Load Check
    engine = OnnxASREngine()
    print("Loading Engine...")
    success = engine.load(model_path)
    print(f"Engine Load Success: {success}")
    
    if not success:
        print("ERROR: Engine failed to load.")
        return

    # 4. Dummy Inference Check
    # Create 1 second of silence/noise
    print("Running dummy inference...")
    dummy_audio = np.random.uniform(-0.1, 0.1, 16000).astype(np.float32)
    try:
        result = engine.transcribe(dummy_audio)
        print(f"Inference Result: '{result}'")
    except Exception as e:
        print(f"Inference Error: {e}")
        
    print("=== ASR Debug End ===")

if __name__ == "__main__":
    test_asr()
