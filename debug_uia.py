import uiautomation as auto
import time
import sys

def get_focus_context():
    try:
        # 增加超时保护，防止跨进程调用卡死
        auto.SetGlobalSearchTimeout(1.0)
        el = auto.GetFocusedControl()
        if not el:
            print("No focus")
            return
        
        print(f"Name: {el.Name}")
        print(f"ControlType: {el.ControlTypeName}")
        
        # 尝试获取文本模式
        pattern = el.GetWindowTextPattern()
        if pattern:
            text = pattern.AttributeValue(auto.TextAttributeId.FontNameId)
            print(f"TextPattern found")
            # 实际上更通用的是 ValuePattern
        
        val_pattern = el.GetValuePattern()
        if val_pattern:
            print(f"Value: {val_pattern.Value}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Wait 3s...")
    time.sleep(3)
    get_focus_context()
