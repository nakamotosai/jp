
import { ISystemService } from "../types";

/**
 * 【系统底层专家】
 * 职责：负责全局热键监控（模拟）、剪贴板操作、模拟键盘发送指令。
 */
export class DesktopSystemService implements ISystemService {
  /**
   * 将文本写入剪贴板
   */
  async copyToClipboard(text: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(text);
      console.log("[System] Clipboard updated:", text);
      return true;
    } catch (err) {
      console.error("[System] Failed to copy:", err);
      return false;
    }
  }

  /**
   * 模拟系统发送按键（Enter/Cmd+V）
   * 在 Web 模拟环境中，通过控制台或 UI 反馈演示。
   */
  async simulateSend(): Promise<void> {
    try {
      console.log("[System] Simulating Paste & Enter keys...");
      // 在真实 Python 环境中，这里会调用 pyautogui 或 pynput
    } catch (err) {
      console.error("[System] Simulation failed:", err);
    }
  }

  /**
   * 发送系统通知
   */
  notify(msg: string): void {
    console.log(`[System Notification] ${msg}`);
  }
}
