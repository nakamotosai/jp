
import os

files = ["tts_worker.py", "ui_manager.py", "main.py"]

for filename in files:
    if not os.path.exists(filename): continue
    print(f"Checking {filename}...")
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            for char in line:
                if char == '\u3002':
                    print(f"Found U+3002 at {filename}:{i+1}")
                    print(f"Line content: {line.strip()}")
                if char == '銆':
                    print(f"Found 銆 at {filename}:{i+1}")
    except Exception as e:
        print(f"Error reading {filename}: {e}")
