"""
TTS Worker - Robust Implementation
"""
import edge_tts
import sounddevice as sd
import numpy as np
import asyncio
import io
import threading
import logging
import traceback
import os
import sys

# Configure logging
def _setup_logging():
    # Only Log in Main Process
    import multiprocessing
    if multiprocessing.current_process().name != 'MainProcess':
        return

    from model_config import get_model_config
    cfg = get_model_config()
    log_file = os.path.join(cfg.DATA_DIR, "tts_worker.log")
    try:
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            encoding='utf-8',
            force=True
        )
        logging.info("TTS Worker logging started (Clean Rewrite).")
        
        # Check ffmpeg
        import subprocess
        try:
            subprocess.run(['ffmpeg', '-version'], creationflags=0x08000000, capture_output=True)
            logging.info(f"ffmpeg detected.")
        except:
            logging.error("ffmpeg not found.")
    except Exception as e:
        print(f"[TTS] Log init failed: {e}")

_setup_logging()

VOICE = "ja-JP-NanamiNeural"

def _find_stereo_output_device():
    try:
        devices = sd.query_devices()
        default_output = sd.default.device[1]
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] < 2: continue
            name = dev['name'].lower()
            if ('耳机' in dev['name'] or 'headphone' in name or 'headset' in name) and not ('hands' in name or 'free' in name):
                return i
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] < 2: continue
            if 'hands' not in dev['name'].lower():
                return i
        return default_output
    except Exception as e:
        logging.warning(f"Device query failed: {e}")
        return None

def _decode_mp3_to_pcm(mp3_data):
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
        samples = np.array(audio.get_array_of_samples())
        if audio.sample_width == 2:
            samples = samples.astype(np.float32) / 32768.0
        elif audio.sample_width == 1:
            samples = (samples.astype(np.float32) - 128) / 128.0
        if audio.channels == 2:
            samples = samples.reshape((-1, 2))
        return samples, audio.frame_rate
    except Exception as e:
        logging.error(f"MP3 Decode Error: {e}")
        return None, None

class TTSWorker:
    def __init__(self):
        self._lock = threading.Lock()
        self._output_device = None
        self._stop_event = threading.Event()
        self._current_text = None
    
    async def _get_audio_data(self, text):
        try:
            communicate = edge_tts.Communicate(text, VOICE)
            audio_stream = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_stream.write(chunk["data"])
            return audio_stream.getvalue()
        except Exception as e:
            logging.error(f"Edge-TTS Error: {e}")
            return None

    def stop(self):
        self._stop_event.set()
        try: sd.stop()
        except: pass
        print("[TTS] Stopped.")

    def say(self, text):
        if not text or not text.strip(): return
        if self._current_text: self.stop()
        
        self._stop_event.clear()
        self._current_text = text

        try:
            # We use a broad try-block to catch anything crashing the thread
            print(f"[TTS_DEBUG] Preparing to say: {text[:10]}...")
            logging.info(f"Preparing to say: {text[:30]}")
            
            # --- 1. Synthesize (Network IO) ---
            try:
                logging.info(f"debug: start asyncio.run")
                mp3_data = asyncio.run(self._get_audio_data(text))
                logging.info(f"debug: asyncio.run finished, data len: {len(mp3_data) if mp3_data else 0}")
            except Exception as e:
                logging.error(f"Asyncio run failed: {e}")
                print(f"[TTS_DEBUG] Asyncio run failed: {e}")
                return

            if self._stop_event.is_set():
                logging.info("debug: stop event set after synthesis")
                return
            if not mp3_data:
                logging.info("debug: mp3_data is empty")
                return

            # --- 2. Decode (CPU) ---
            samples, sample_rate = _decode_mp3_to_pcm(mp3_data)
            if samples is None: 
                logging.info("debug: samples is None")
                return

            if self._stop_event.is_set(): 
                logging.info("debug: stop event set after decode")
                return

            # --- 3. Play (Audio IO) ---
            logging.info("debug: acquiring lock")
            with self._lock:
                logging.info("debug: lock acquired")
                self._output_device = _find_stereo_output_device()
                logging.info(f"Playing {len(samples)} samples on device {self._output_device}")
                
                try:
                    sd.play(samples, samplerate=sample_rate, device=self._output_device)
                except Exception as e:
                    logging.warning(f"Device playback failed: {e}, trying default.")
                    try:
                        sd.play(samples, samplerate=sample_rate, device=None)
                    except Exception as e2:
                        logging.error(f"All playback failed: {e2}")
                        return
                
                # Wait for completion
                while sd.get_stream().active:
                    if self._stop_event.is_set():
                        sd.stop()
                        break
                    sd.sleep(50)
                logging.info("Playback finished.")

        except Exception as e:
            logging.error(f"CRITICAL TTS ERROR: {e}")
            logging.error(traceback.format_exc())
            print(f"[TTS_DEBUG] Critical: {e}")
        finally:
            self._current_text = None

_instance = TTSWorker()

def say(text):
    _instance.say(text)

def stop():
    _instance.stop()
