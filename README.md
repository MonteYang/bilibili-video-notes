# bilibili-video-notes

把B站视频链接变成结构化学习笔记的 [Agent Skill](https://agentskills.io)。

**纯本地 · 零 API key · 跨 Agent 通用**——不注册任何云服务，不装桌面应用，不给视频上传到任何第三方。有 CC 字幕直接提取（秒出），没有就用本地 Whisper 转录（GPU/CPU 自动选择），然后由你的 AI Agent 基于转录文本撰写结构化笔记。

```text
B站链接 ──► 有CC字幕？──是──► 提取字幕（纯标准库，秒出）
                │
                否
                ▼
         下载音频（yt-dlp）
                ▼
         本地 Whisper 转录（faster-whisper，自动 GPU/CPU）
                ▼
         带时间戳转录文本 .md
                ▼
         Agent 撰写结构化学习笔记
```

## 安装

```bash
# Claude Code / 通用 skills 目录
git clone https://github.com/MonteYang/bilibili-video-notes.git ~/.claude/skills/bilibili-video-notes

# Hermes Agent
git clone https://github.com/MonteYang/bilibili-video-notes.git ~/.hermes/skills/bilibili-video-notes
```

依赖分两档：

```bash
# 字幕提取：零第三方依赖，Python 3.8+ 标准库即可用
# 转录（无字幕视频需要）：
pip install yt-dlp faster-whisper
# 可选（GPU 提速，无 NVIDIA 卡跳过）：
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

首次转录会自动下载 Whisper 模型（small 约 466MB，国内网络自动走 hf-mirror.com 镜像）。

## 使用

对任何支持 Agent Skills 的助手（Claude Code、Cursor、Hermes Agent 等）说：

```text
帮我做这个B站视频的学习笔记 https://www.bilibili.com/video/BV1nyQGBaEKW
```

或者直接用命令行：

```bash
cd ~/.claude/skills/bilibili-video-notes   # 或你的安装位置

# 看视频信息、有没有CC字幕
python3 scripts/bilibili_notes.py info https://www.bilibili.com/video/BV1nyQGBaEKW

# 有CC字幕：直接提取
python3 scripts/bilibili_notes.py subtitles BV1nyQGBaEKW -o notes/transcript.md

# 没有CC字幕：本地转录（默认 small 模型，GPU 自动检测）
python3 scripts/bilibili_notes.py transcribe BV1nyQGBaEKW -o notes/transcript.md

# 多P视频：第3P
python3 scripts/bilibili_notes.py transcribe "https://www.bilibili.com/video/BVxxx?p=3"

# 弹幕（辅助参考，不是视频内容）
python3 scripts/bilibili_notes.py danmaku BV1nyQGBaEKW --top 20
```

### 转录模型怎么选

| 模型 | 下载大小 | 中文质量 | 说明 |
|------|---------|---------|------|
| tiny | 72MB | 差 | 中文同音字错误极多，**不推荐**中文视频 |
| base | 142MB | 一般 | 同音字错误多 |
| **small**（默认） | 466MB | 高 | 中文视频最低推荐 |
| medium | 1.5GB | 很高 | 慢，专业内容 |
| large-v3 | 2.9GB | 最好 | 需要较多内存/显存 |

速度参考（14 分钟视频）：GPU（MX330 级别老卡 + int8）约 4 分钟；CPU 约等于音频时长。

## 输出示例

转录文件（`BV1nyQGBaEKW_transcript.md`）：

```markdown
# 什么是Harness？不就是Agent的Infra嘛

- UP主：ZOMI酱
- 时长：14分09秒
- 链接：https://www.bilibili.com/video/BV1nyQGBaEKW
- 文本来源：Whisper small（cuda）

## 转录文本

**[00:00]** 大家好，今天我们来聊一个最近特别火的概念……

**[00:38]** 那什么是Harness呢……
```

结构化笔记由 Agent 基于转录文本撰写，模板见 [SKILL.md](SKILL.md)：核心要点（带时间戳）、关键概念表、实践建议、相关资源。

## 与同类项目的区别

| | 本项目 | BiliNote 等GUI工具 | 云端转录类skill |
|---|---|---|---|
| 安装 | git clone 即用 | 桌面应用/自建服务 | 需注册API key |
| 网络依赖 | 仅B站+模型下载 | 自行部署 | 视频文本上传境外云 |
| GPU/CPU | 自动检测，CPU可跑 | 需配置 | 无本地算力 |
| 笔记质量 | Agent 撰写，可定制 | 固定模板 | 固定模板 |
| 适用Agent | 任何 Skills 兼容 Agent | 独立使用 | Claude Code 为主 |

## 实测数据（2026-10）

- 无登录态下，B站 CC 字幕覆盖率极低：热门榜 100 个视频 0 个带 CC 字幕（课程区、TED 类多为内嵌硬字幕，API 拿不到）
- 所以 **Whisper 转录才是主路径**，字幕提取是少数视频的加速通道
- B站 AI 字幕（"AI视频总结"）需要登录 Cookie，本工具不获取、不模拟登录

## 已知限制

- 需要登录才能看的视频（充电专属、会员专享）无法处理
- 硬字幕（烧在画面里的）无法提取，只能转录
- 转录耗时：CPU 下约为音频时长的 0.8-1 倍，长视频建议后台运行

## License

MIT
