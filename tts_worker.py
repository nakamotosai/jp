"""
TTS Worker - 使用 Edge-TTS 合成日语语音，通过 sounddevice 播放

核心特性：
1. 显式选择 Stereo 输出设备，绕过蓝牙 Hands-Free 端点
2. 支持中断播放：新的语音请求会立即中断当前播放
"""
import edge_tts
import sounddevice as sd
import numpy as np
import asyncio
import io
import threading
import logging

# 语音选择 (ja-JP-NanamiNeural 是目前音质最好的日语女声之一)
VOICE = "ja-JP-NanamiNeural"


def _find_stereo_output_device():
    """
    查找可用的 Stereo (双声道) 输出设备，避开 Hands-Free (单声道) 端点。
    """
    try:
        devices = sd.query_devices()
        default_output = sd.default.device[1]
        
        # 第一轮：寻找蓝牙耳机的 Stereo 端点
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] < 2:
                continue
            
            name = dev['name'].lower()
            is_headphone = '耳机' in dev['name'] or 'headphone' in name or 'headset' in name
            is_hands_free = 'hands' in name or 'free' in name or 'hfp' in name
            
            if is_headphone and not is_hands_free:
                return i
        
        # 第二轮：任意双声道输出设备
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] < 2:
                continue
            
            name = dev['name'].lower()
            if 'hands' in name or 'free' in name or 'hfp' in name:
                continue
                
            return i
        
        return default_output
        
    except Exception as e:
        logging.warning(f"[TTS] 设备查询失败: {e}")
        return None


def _decode_mp3_to_pcm(mp3_data):
    """使用 pydub 将 MP3 数据解码为 PCM numpy 数组"""
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
    except ImportError:
        logging.error("[TTS] pydub 未安装。请运行: pip install pydub")
        return None, None
    except Exception as e:
        logging.error(f"[TTS] MP3 解码错误: {e}")
        return None, None


class TTSWorker:
    def __init__(self):
        self._lock = threading.Lock()
        self._output_device = None
        self._stop_event = threading.Event()  # 用于中断当前播放
        self._current_text = None  # 当前正在播放的文本
    
    def _refresh_device(self):
        """刷新输出设备选择"""
        self._output_device = _find_stereo_output_device()

    async def _get_audio_data(self, text):
        """调用 Edge-TTS 获取音频二进制数据"""
        communicate = edge_tts.Communicate(text, VOICE)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
        return audio_stream.getvalue()

    def stop(self):
        """中断当前播放"""
        self._stop_event.set()
        try:
            sd.stop()  # 立即停止 sounddevice 播放
        except:
            pass
        print("[TTS] 播放已中断")

    def say(self, text):
        """
        播放语音。如果有新的播放请求，会中断当前播放。
        """
        if not text or not text.strip():
            return

        # 如果有正在播放的语音，先中断它
        if self._current_text:
            self.stop()
        
        # 重置停止标志
        self._stop_event.clear()
        self._current_text = text

        with self._lock:
            try:
                # 检查是否已被中断
                if self._stop_event.is_set():
                    self._current_text = None
                    return

                # 1. 获取音频数据
                print(f"[TTS] 正在合成: {text[:30]}...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                mp3_data = loop.run_until_complete(self._get_audio_data(text))
                loop.close()

                # 检查是否已被中断
                if self._stop_event.is_set():
                    print("[TTS] 合成完成但已被中断，跳过播放")
                    self._current_text = None
                    return

                if not mp3_data:
                    self._current_text = None
                    return

                # 2. 解码 MP3 为 PCM
                samples, sample_rate = _decode_mp3_to_pcm(mp3_data)
                if samples is None:
                    self._current_text = None
                    return

                # 检查是否已被中断
                if self._stop_event.is_set():
                    self._current_text = None
                    return

                # 3. 刷新设备选择
                self._refresh_device()

                # 4. 播放
                print(f"[TTS] 开始播放...")
                sd.play(samples, samplerate=sample_rate, device=self._output_device)
                
                # 使用轮询方式等待播放完成，以便可以被中断
                while sd.get_stream().active:
                    if self._stop_event.is_set():
                        sd.stop()
                        print("[TTS] 播放被新请求中断")
                        break
                    sd.sleep(100)  # 每 100ms 检查一次
                else:
                    print("[TTS] 播放完成")
                    
            except Exception as e:
                logging.error(f"[TTS] 播放错误: {e}")
            finally:
                self._current_text = None


_instance = TTSWorker()

def say(text):
    """供外部调用的主函数 - 会中断当前播放"""
    _instance.say(text)

def stop():
    """立即停止当前播放"""
    _instance.stop()
