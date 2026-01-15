
import sys
import os
import time
import win32gui
import uiautomation as auto

def print_caret_info():
    print("Waiting 3 seconds... Please switch to target input window.")
    time.sleep(3)
    
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    print(f"Active Window: {hex(hwnd)} - {title}")
    
    focused = auto.GetFocusedControl()
    if not focused:
        print("UIA: No focused control found.")
        return

    print(f"Focused Control: {focused.Name} ({focused.ControlTypeName})")
    
    # Try TextPattern
    pattern = focused.GetPattern(auto.PatternId.TextPattern)
    if pattern:
        print("Support TextPattern: Yes")
        selections = pattern.GetSelection()
        if not selections:
            print("  Selection: None")
        else:
            try:
                caret = selections[0]
                
                # Method 1: Clone and Expand
                # We clone the caret range, then move the End endpoint to the end of the document.
                # Then we check if the text in this new range is empty.
                chk_range = caret.Clone()
                chk_range.MoveEndpoint(auto.TextPatternRangeEndpoint.End, auto.TextUnit.Document, 1)
                
                remaining_text = chk_range.GetText()
                print(f"  Remaining text length: {len(remaining_text)}")
                # print(f"  Remaining text: '{remaining_text}'")
                
                if len(remaining_text) == 0:
                     print("  => Verdict: Cursor IS AT END (is_at_end = True)")
                else:
                     print("  => Verdict: Cursor NOT AT END (is_at_end = False)")
                     
            except Exception as e:
                print(f"  Error checking range: {e}")

    else:
        print("Support TextPattern: No")
        
    # Try ValuePattern
    val_pattern = focused.GetPattern(auto.PatternId.ValuePattern)
    if val_pattern:
        print("Support ValuePattern: Yes")
        val = val_pattern.Value
        print(f"  Value Length: {len(val)}")
        if not val:
            print("  => Verdict: Empty Value (is_at_end = True)")
        else:
            print("  => Verdict: Non-empty Value (Cannot determine cursor)")
    else:
        print("Support ValuePattern: No")

if __name__ == "__main__":
    while True:
        print("\n-----------------------------")
        print_caret_info()
        input("Press Enter to test again, Ctrl+C to exit...")
