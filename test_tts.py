
import logging
import time
import sys
import os

# Setup logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

print("Importing tts_worker...")
try:
    import tts_worker
    print("tts_worker imported.")
except ImportError as e:
    print(f"Failed to import tts_worker: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Crash during import: {e}")
    sys.exit(1)

print("Testing TTS in a background THREAD...")
try:
    import threading
    t = threading.Thread(target=tts_worker.say, args=("こんにちは、これはスレッドテストです。",))
    t.start()
    t.join()
    print("TTS thread finished.")
except Exception as e:
    print(f"Error during TTS: {e}")
    import traceback
    traceback.print_exc()

print("Test finished.")
