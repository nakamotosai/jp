import os
import sys
import numpy as np
import traceback

def log(msg):
    print(msg)
    sys.stdout.flush()

def test_onnx_direct():
    model_path = r"C:\Users\sai\jp\models\SenseVoiceSmall-onnx"
    log(f"Testing model at: {model_path}")
    
    try:
        from funasr_onnx import SenseVoiceSmall
        log("Imported SenseVoiceSmall from funasr_onnx")
        
        log("Initializing model (quantize=True)...")
        # Ensure the model path exists
        if not os.path.exists(model_path):
            log(f"Error: {model_path} does not exist!")
            return

        model = SenseVoiceSmall(model_path, quantize=True)
        log("Model initialized successfully.")
        
        # Create a 1-second dummy audio (16kHz, mono)
        audio = np.zeros(16000, dtype=np.float32)
        log(f"Starting inference with dummy audio (length: {len(audio)})...")
        
        result = model(audio, language="zh")
        log(f"Inference finished. Result type: {type(result)}")
        log(f"Result content: {result}")
        
    except Exception as e:
        log(f"\n[ERROR] Caught exception: {e}")
        traceback.print_exc()
    except BaseException as b:
        log(f"\n[FATAL] Caught base exception (possibly crash): {b}")
        traceback.print_exc()

if __name__ == "__main__":
    test_onnx_direct()
