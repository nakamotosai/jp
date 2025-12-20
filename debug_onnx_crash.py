import os
import sys
import numpy as np
import traceback

def log(msg):
    print(msg)
    sys.stdout.flush()

def test_onnx_crash_condition():
    model_path = r"C:\Users\sai\jp\models\SenseVoiceSmall-onnx"
    log(f"Testing model at: {model_path}")
    
    try:
        from funasr_onnx import SenseVoiceSmall
        log("Imported SenseVoiceSmall")
        
        # SenseVoiceSmall(model_dir, batch_size=1, quantize=False, **kwargs)
        model = SenseVoiceSmall(model_path, quantize=True)
        log("Model initialized.")
        
        # Test with the length that crashed (116736)
        audio = np.random.randn(116736).astype(np.float32)
        log(f"Starting inference with audio length {len(audio)}...")
        
        # Some versions of SenseVoiceSmall-onnx might need 'language="auto"'
        # or specific keys.
        result = model(audio, language="zh")
        log(f"Result: {result}")
        
    except Exception as e:
        log(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_onnx_crash_condition()
