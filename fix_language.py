import os

path = r'C:\Users\sai\jp\ui_manager.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(len(lines)):
    if '入력을ください' in lines[i]:
        print(f"Found mixed string at line {i+1}")
        lines[i] = lines[i].replace('入력을ください', '等待输入...')

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Finished replacement.")
