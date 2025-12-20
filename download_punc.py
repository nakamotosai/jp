from modelscope.hub.snapshot_download import snapshot_download
import os
import shutil

def download_punc_model():
    print("正在下载标点恢复模型 (Punctuation Model)...")
    try:
        # 尝试 iic 命名空间
        model_id = 'iic/punc_ct_transformer_zh-cn-common-vocab272727-onnx'
        print(f"尝试下载: {model_id}")
        model_dir = snapshot_download(model_id)
        print(f"模型下载完成，路径: {model_dir}")
        
        target_dir = os.path.join(os.getcwd(), 'models', 'punc_ct_transformer_zh-cn-common-vocab272727-onnx')
        
        if os.path.exists(target_dir):
            print(f"目标目录已存在: {target_dir}")
        else:
            print(f"正在移动模型到: {target_dir}")
            shutil.copytree(model_dir, target_dir)
            
    except Exception as e:
        print(f"下载失败: {e}")
        # 备用尝试 damo 命名空间 (非 onnx 版，pyTorch 版也许能用 onnxruntime 跑？不行)
        print("尝试备用ID...")

if __name__ == "__main__":
    download_punc_model()
