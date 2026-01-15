import sys
import os
print(f"Executable: {sys.executable}")
print(f"Path: {sys.path}")
try:
    import pyperclip
    print(f"pyperclip found: {pyperclip.__file__}")
except ImportError as e:
    print(f"pyperclip NOT found: {e}")

try:
    import win32clipboard
    print("win32clipboard found")
except ImportError:
    print("win32clipboard NOT found")
