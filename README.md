# 多模态智能创作平台

这是一个基于 Gradio 的智能创作应用，包含小说创作、公文生成、剧本创作和语音输入功能。

## 环境要求

- Python 3.10 或 3.11
- 可用的麦克风（使用语音输入时）

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

复制环境变量模板并填写实际密钥：

```powershell
Copy-Item .env.example .env
```

应用启动时会自动读取 `.env`；也可以直接设置系统环境变量。不要提交 `.env`。

## 运行

```powershell
python main.py
```

默认访问地址为 <http://127.0.0.1:7860>。如需公网分享，将 `GRADIO_SHARE` 设置为 `true`。

## 主要文件

- `main.py`：完整 Gradio 应用入口
- `AIGC.py`：公文生成逻辑
- `AIGN.py`：小说生成逻辑
- `SCRIPT.py`：剧本生成逻辑
- `voice_input.py`：录音、语音识别和情感分析
- `Prompt/`：各模块使用的提示词

其余 `app*.py`、`add.py`、`mix_all.py` 和 `*work.py` 为早期实验入口，保留用于对照。

## 凭据说明

项目通过环境变量读取 DashScope、腾讯云、MindCraft 和阿里云凭据。首次公开提交前，请轮换曾经写入源码的旧凭据。
