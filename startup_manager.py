"""
开机自启动管理器
管理Windows开机自启动功能
"""
import os
import sys
import winreg
from typing import Optional


class StartupManager:
    """Windows 开机自启动管理"""
    
    APP_NAME = "AIJapaneseInput"
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    @classmethod
    def get_executable_path(cls) -> str:
        """获取当前可执行文件路径"""
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后
            return sys.executable
        else:
            # 开发模式
            return f'"{sys.executable}" "{os.path.abspath(__file__)}"'
    
    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否已启用开机自启动"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                cls.REG_PATH,
                0,
                winreg.KEY_READ
            )
            try:
                value, _ = winreg.QueryValueEx(key, cls.APP_NAME)
                return bool(value)
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            print(f"[StartupManager] 检查自启动状态失败: {e}")
            return False
    
    @classmethod
    def enable(cls, minimized: bool = True) -> bool:
        """
        启用开机自启动
        
        Args:
            minimized: 是否以最小化方式启动
        
        Returns:
            是否成功
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                cls.REG_PATH,
                0,
                winreg.KEY_SET_VALUE
            )
            
            exe_path = cls.get_executable_path()
            if minimized:
                exe_path += " --minimized"
            
            winreg.SetValueEx(key, cls.APP_NAME, 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            
            print(f"[StartupManager] 已启用开机自启动: {exe_path}")
            return True
            
        except Exception as e:
            print(f"[StartupManager] 启用自启动失败: {e}")
            return False
    
    @classmethod
    def disable(cls) -> bool:
        """禁用开机自启动"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                cls.REG_PATH,
                0,
                winreg.KEY_SET_VALUE
            )
            
            try:
                winreg.DeleteValue(key, cls.APP_NAME)
            except FileNotFoundError:
                pass  # 已经不存在
            
            winreg.CloseKey(key)
            
            print("[StartupManager] 已禁用开机自启动")
            return True
            
        except Exception as e:
            print(f"[StartupManager] 禁用自启动失败: {e}")
            return False
    
    @classmethod
    def set_enabled(cls, enabled: bool, minimized: bool = True) -> bool:
        """设置开机自启动状态"""
        if enabled:
            return cls.enable(minimized)
        else:
            return cls.disable()
