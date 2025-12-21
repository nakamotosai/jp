import PyInstaller.__main__
import os
import shutil
import sys

def build():
    print("开始打包...")
    
    # 获取当前目录
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    
    # 清理旧构建
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")
        
    # 检查是否有 logo.png
    add_data = []
    if os.path.exists("logo.png"):
        add_data.append('--add-data=logo.png;.')
        
    # PyInstaller 参数
    args = [
        'main.py',
        '--name=AI_JP_Input',
        '--onefile',      # 打包成单文件 exe
        '--noconsole',    # 不显示控制台窗口
        '--clean',        # 清理缓存
        # 排除不需要的模块以减小体积（可选）
        # '--exclude-module=matplotlib',
        # '--exclude-module=tkinter',
        
        # 处理隐藏导入（如果有）
        '--hidden-import=sherpa_onnx',
        '--hidden-import=sounddevice',
        '--hidden-import=ctranslate2',
        
        # 增加递归深度以防报错
        '--runtime-hook=runtime_hook.py' if os.path.exists('runtime_hook.py') else None,
    ]
    
    # 过滤 None
    args = [a for a in args if a] + add_data
    
    # 如果有 icon
    if os.path.exists("logo.png"):
        args.append('--icon=logo.png')
        
    print(f"执行参数: {args}")
    
    try:
        PyInstaller.__main__.run(args)
        print("\n打包成功！文件位于 dist/AI_JP_Input.exe")
    except Exception as e:
        print(f"\n打包失败: {e}")

if __name__ == "__main__":
    build()
