---
name: bilibili-video-notes
license: MIT
compatibility: "Claude Code / Cursor / Hermes Agent / 任何支持 Agent Skills 的助手"
when_to_use: 用户提供B站视频链接，要求做笔记、总结、转录或提取内容时
---

# B站视频学习笔记生成器

把一个B站视频链接变成结构化学习笔记。三步：**取文本 → Agent 撰写 → 保存笔记**。

设计哲学：**纯本地、零 API key**。字幕提取纯标准库零第三方依赖；无字幕时用本地 Whisper 转录；结构化笔记由 Agent 基于转录文本撰写——脚本不做摘要，笔记质量取决于 Agent。

## 工作流程

### 第 1 步：获取转录文本（按优先级）

**优先 CC 字幕**（零依赖、秒出、无转录误差）：

```bash
python3 scripts/bilibili_notes.py info <视频链接或BV号>
```

返回 JSON 里 `has_cc_subtitle: true` 时：

```bash
python3 scripts/bilibili_notes.py subtitles <视频链接或BV号> -o 输出.md
```

输出为带时间戳的 Markdown 转录文本。

**无 CC 字幕（B站大多数视频）→ 本地 Whisper 转录**：

```bash
python3 scripts/bilibili_notes.py transcribe <视频链接或BV号> -o 输出.md
```

参数说明：
- `-m` 模型：`tiny / base / small / medium / large-v3`，**默认 small**。
  中文视频务必 small 及以上——tiny/base 中文同音字错误率过高，几乎不可读。
- `--device auto|cpu|cuda`：默认 auto（检测到 CUDA 就用 GPU int8，否则 CPU）
- `--page N`：多P视频的第 N P，也支持直接粘贴带 `?p=N` 的链接
- `--language zh`：音频语言，默认中文

依赖（仅 transcribe 需要）：`pip install yt-dlp faster-whisper`，可选 `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`（GPU 提速）。
首次转录会从 HuggingFace（国内自动走 hf-mirror.com 镜像）下载模型：small 约 466MB。

**仍无结果时的兜底**：引导用户手动提供文本（B站页面"AI总结"复制、或任意字幕工具导出的 SRT），跳过脚本直接进入第 2 步。

### 第 2 步：Agent 撰写结构化笔记

基于转录文本撰写学习笔记，保存为 `<BV号>_notes.md`，与转录文件放在一起。模板：

```markdown
# {视频标题}

**UP主**：{owner}
**时长**：{duration}
**链接**：{url}
**文本来源**：CC字幕 / Whisper small

## 核心要点

### 1. {要点标题}
- 关键内容（附时间戳，如 [05:12]）
- ...

## 关键概念解释

| 概念 | 解释 |
|------|------|
| {概念} | {用转录文本中的原话或你的准确解释} |

## 实践建议

## 相关资源

- {视频、文章、代码仓库等，仅列转录文本中实际提到的，不编造}
```

写作要求：
- 所有要点尽量带时间戳，方便读者跳回视频对应位置
- 修正转录文本中明显的同音字错误，但**不要改写原意**
- 转录文本没有的内容不要编造；"相关资源"只列视频里实际提到的
- 长视频（>1h）可按视频章节组织，不必强行压缩成 3-5 个要点

### 第 3 步：交付

把笔记路径告诉用户，并提示：转录文件（`*_transcript.md`）也保留了，
需要检索原文、引用原话、或生成其他形态输出（思维导图、闪卡）时可基于它。

## 辅助子命令

| 命令 | 用途 |
|------|------|
| `info <url>` | 视频元信息 JSON，含 `has_cc_subtitle`（决定走哪条路径） |
| `subtitles <url>` | 提取CC字幕为带时间戳 Markdown |
| `transcribe <url>` | 下载音频 + 本地 Whisper 转录（需要 yt-dlp + faster-whisper） |
| `danmaku <url>` | 提取弹幕（观众评论，仅辅助参考，不是视频内容） |

## 边界与已知限制

- `has_cc_subtitle` 只统计 UP 主上传的 CC 字幕；B站 AI 字幕需要登录 Cookie，本工具不获取
- 需要登录才能看的视频（充电专属等）无法处理
- 转录是耗时操作：CPU small 约为音频时长的 0.8-1 倍，长视频请用后台运行并在完成后通知用户
- 弹幕是观众评论不是视频内容，可作为热点的旁证，不能当转录文本用
