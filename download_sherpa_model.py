import os
import requests
import tarfile
import sys

URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
DEST_DIR = os.path.join(os.getcwd(), "models")
FILENAME = os.path.join(DEST_DIR, "sherpa-onnx-sense-voice.tar.bz2")

def download_and_extract():
    print(f"开始下载: {URL}")
    if not os.path.exists(DEST_DIR):
        os.makedirs(DEST_DIR)
        
    try:
        response = requests.get(URL, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded = 0
        
        with open(FILENAME, 'wb') as f:
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = downloaded * 100 / total_size
                        sys.stdout.write(f"\r下载进度: {percent:.1f}%")
                        sys.stdout.flush()
        print("\n下载完成！")
        
        print("正在解压...")
        with tarfile.open(FILENAME, "r:bz2") as tar:
            tar.extractall(path=DEST_DIR)
        print(f"解压完成，位置: {DEST_DIR}")
        
    except Exception as e:
        print(f"\n错误: {e}")

if __name__ == "__main__":
    download_and_extract()
