# 🚀 软件发布与分发指南 (Release Guide)

本文档详细说明了 AI 日语输入法发布前的准备工作、模型托管方案、自动更新机制以及最终打包发布的完整流程。

---

## 📅 任务清单 (Checklist)

### 1. 模型托管 (Model Hosting)
- [ ] 注册 HuggingFace 账号并创建 Model Repo
- [ ] 上传大模型文件 (ASR & Translation) 到 HuggingFace
- [ ] 确保国内用户可以通过镜像 (hf-mirror.com) 下载

### 2. 自动更新 (Auto-Update)
- [ ] 确定版本号规范 (Semantic Versioning, e.g., v1.0.0)
- [ ] 搭建更新元数据服务器 (推荐 GitHub Pages 或 Gitee Pages)
- [ ] 在 `main.py` 或 `startup_manager.py` 中集成版本检测逻辑
- [ ] 实现更新提示与下载跳转

### 3. 打包与安装 (Packaging)
- [ ] 优化 PyInstaller 构建脚本 (减小体积)
- [ ] 制作 Windows 安装包 (Inno Setup)
- [ ] 配置安装包元数据 (图标、版本信息、版权)
- [ ] 测试安装、卸载及覆盖安装流程

---

## 🛠️ 第一部分：模型托管与镜像设置

由于模型文件巨大 (2GB+)，不建议直接打包进 EXE，而是建议托管在 HuggingFace，并利用国内镜像加速下载。

### 1. 上传模型到 HuggingFace
你需要两个 Repo：
1.  **ASR 模型**: 例如 `your-username/ai-jp-input-asr`
2.  **翻译模型**: 例如 `your-username/ai-jp-input-nllb`

**操作步骤：**
1.  登录 [HuggingFace](https://huggingface.co/) 创建 New Model。
2.  使用 Web 界面或 `huggingface-cli` 上传文件。
    *   *推荐使用 Web 界面上传 zip 压缩包，方便用户下载。*

### 2. 设置国内镜像 (hf-mirror.com)
国内用户直接访问 HF 极其缓慢。你需要修改 `model_downloader.py` 中的下载逻辑，或者指导用户设置环境变量。

**代码修改方案 (`model_downloader.py`)：**
在下载代码中，将 `https://huggingface.co` 替换为 `https://hf-mirror.com`。

```python
# 示例：智能切换下载源
HF_DOMAIN = "https://huggingface.co"
HF_MIRROR = "https://hf-mirror.com"

def get_download_url(repo_id, filename, use_mirror=True):
    domain = HF_MIRROR if use_mirror else HF_DOMAIN
    # 构造下载链接
    return f"{domain}/{repo_id}/resolve/main/{filename}"
```

---

## 🔄 第二部分：自动更新机制 (Auto-Update)

对于轻量级应用，推荐采用 **"检测 + 提示"** 的轻量级更新方案。

### 1. 版本控制文件 `version.json`
在你的 GitHub 仓库（或 Gitee）的根目录放置一个 `version.json`：

```json
{
    "latest_version": "1.0.1",
    "release_date": "2025-12-25",
    "download_url": "https://github.com/your-user/your-repo/releases/download/v1.0.1/AI_JP_Input_Setup_v1.0.1.exe",
    "changelog": "1. 修复了设置面板崩溃问题\n2. 优化了启动速度"
}
```

### 2. 在应用中集成检测逻辑
在 `main.py` (AppController 初始化时) 或 `startup_manager.py` 中添加：

```python
import requests
from packaging import version

CURRENT_VERSION = "1.0.0"
VERSION_CHECK_URL = "https://raw.githubusercontent.com/your-username/your-repo/main/version.json"
# 如果用 Gitee (国内访问更快):
# VERSION_CHECK_URL = "https://gitee.com/your-username/your-repo/raw/master/version.json"

def check_update():
    try:
        resp = requests.get(VERSION_CHECK_URL, timeout=5)
        data = resp.json()
        remote_ver = data["latest_version"]
        
        if version.parse(remote_ver) > version.parse(CURRENT_VERSION):
            # 触发更新提示弹窗（建议使用 PyQt 弹窗）
            return data
    except Exception as e:
        print(f"检查更新失败: {e}")
    return None
```

---

## 📦 第三部分：打包成安装文件 (Inno Setup)

使用 PyInstaller 生成的只是一个裸 EXE，我们需要把它封装成专业的安装程序 (`setup.exe`)，以便处理快捷方式、卸载等。

### 1. 准备工作
- 下载并安装 [Inno Setup Compiler](https://jrsoftware.org/isdl.php) (Windows 免费软件)。
- 确保你已经运行了 `python build_exe.py` 并在 `dist` 目录下生成了 `AI_JP_Input.exe`。

### 2. 创建安装脚本 `setup_script.iss`
在项目根目录创建一个文本文件 `setup_script.iss`，内容如下：

```iss
; 脚本生成向导
#define MyAppName "AI 日语输入法"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Cai Siyang"
#define MyAppURL "https://github.com/your-repo"
#define MyAppExeName "AI_JP_Input.exe"

[Setup]
; NOTE: 下面的 AppId 的值唯一标识该应用程序。
; 不要在这个安装程序中用于其他应用程序。
; (使用 Inno Setup IDE 中的 "Tools" -> "Generate GUID" 生成一个新的 GUID)
AppId={{YOUR-GUID-HERE}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\AI_JP_Input
DisableProgramGroupPage=yes
; 移除下面这行如果想让用户选择安装目录
DisableDirPage=no
; 输出文件名
OutputBaseFilename=AI_JP_Input_Setup_v{#MyAppVersion}
; 压缩算法
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 主程序
Source: "dist\AI_JP_Input.exe"; DestDir: "{app}"; Flags: ignoreversion
; 下面添加其他依赖文件（如果有的话，注意不要包含巨大的 models 文件夹）
; Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
; source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
```

### 3. 生成安装包
双击 `setup_script.iss` 用 Inno Setup 打开，点击 "Compile" (播放按钮)，它会在 `Output` 文件夹下生成 `AI_JP_Input_Setup_v1.0.0.exe`。

---

## 🚀 总结：你的发布路线图

1.  **First**: 运行 `build_exe.py` 确保 EXE 能正常工作。
2.  **Next**: 按上面的步骤注册 HuggingFace 并上传模型。
3.  **Then**: 实现 `check_update` 代码，并在 GitHub/Gitee 上传 `version.json`。
4.  **Finally**: 使用 Inno Setup 制作安装包，并发布到 GitHub Releases。
