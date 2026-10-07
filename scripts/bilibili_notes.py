#!/usr/bin/env python3
"""
B站视频 → 带时间戳转录文本（Agent Skill 核心脚本）

设计原则：
- 字幕提取路径：纯标准库（urllib），无任何第三方依赖
- 转录路径：按需导入 yt-dlp + faster-whisper，缺失时给出明确的安装指引
- 结构化笔记由 Agent 基于本脚本输出的转录文本撰写，脚本不做"假摘要"

子命令：
    info <url|BV号>                       视频元信息 + 是否有CC字幕（JSON）
    subtitles <url|BV号> [-o 输出文件]     提取CC字幕为带时间戳Markdown
    transcribe <url|BV号> [-m 模型]        下载音频 + 本地Whisper转录
    danmaku <url|BV号> [--top N]          提取弹幕（辅助参考）

示例：
    python3 bilibili_notes.py info https://www.bilibili.com/video/BV1nyQGBaEKW
    python3 bilibili_notes.py subtitles BV1nyQGBaEKW
    python3 bilibili_notes.py transcribe https://www.bilibili.com/video/BV1nyQGBaEKW?p=2
    python3 bilibili_notes.py transcribe BV1nyQGBaEKW -m small --device cpu
"""

import argparse
import ctypes
import glob
import json
import os
import re
import sys
import urllib.request

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}

DEFAULT_MODEL = "small"  # 中文内容的最低可用推荐；tiny/base 中文同音字错误率过高

BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")


# ---------------------------------------------------------------- 基础工具

def http_get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers=API_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_bvid(url_or_bvid: str) -> str:
    m = BV_RE.search(url_or_bvid.strip())
    if not m:
        raise ValueError(f"无法从 '{url_or_bvid}' 中提取BV号（形如 BV1xx411c7mD）")
    return m.group(0)


def extract_page(url_or_bvid: str) -> int:
    m = re.search(r"[?&]p=(\d+)", url_or_bvid)
    return int(m.group(1)) if m else 1


def fetch_view(bvid: str) -> dict:
    data = http_get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    if data.get("code") != 0:
        raise RuntimeError(f"B站API错误 code={data.get('code')}: {data.get('message')}")
    return data["data"]


def resolve_cid(view: dict, page: int) -> int:
    pages = view.get("pages") or [{"cid": view["cid"], "page": 1, "part": view["title"]}]
    for p in pages:
        if p.get("page") == page:
            return p["cid"], p.get("part", view["title"])
    raise ValueError(f"视频只有 {len(pages)} 个分P，没有第 {page} P")


def format_ts(seconds: float) -> str:
    seconds = int(seconds)
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_duration(sec: int) -> str:
    return f"{sec // 60}分{sec % 60}秒"


# ---------------------------------------------------------------- info / 字幕

def fetch_subtitle_tracks(bvid: str, cid: int) -> list:
    data = http_get_json(
        f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}")
    return data.get("data", {}).get("subtitle", {}).get("subtitles", [])


def cmd_info(args) -> None:
    bvid = extract_bvid(args.url)
    view = fetch_view(bvid)
    cid, part = resolve_cid(view, args.page)
    tracks = fetch_subtitle_tracks(bvid, cid)
    info = {
        "bvid": bvid,
        "title": view["title"],
        "page": args.page,
        "page_title": part,
        "owner": view["owner"]["name"],
        "duration_sec": view["duration"],
        "desc": view["desc"][:200],
        "has_cc_subtitle": bool(tracks),
        "subtitle_languages": [t["lan_doc"] for t in tracks],
        "url": f"https://www.bilibili.com/video/{bvid}" + (f"?p={args.page}" if args.page > 1 else ""),
        "note": "has_cc_subtitle 只统计UP主上传的CC字幕；B站AI字幕需要登录Cookie，本工具不支持",
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))


def cmd_subtitles(args) -> None:
    bvid = extract_bvid(args.url)
    view = fetch_view(bvid)
    cid, part = resolve_cid(view, args.page)
    tracks = fetch_subtitle_tracks(bvid, cid)
    if not tracks:
        print("该视频没有CC字幕。请改用 transcribe 子命令本地转录，或让 Agent 引导你手动获取文本。",
              file=sys.stderr)
        sys.exit(2)

    # 优先选中文字幕，其次第一个
    track = next((t for t in tracks if "zh" in t["lan"]), tracks[0])
    sub_url = track["subtitle_url"]
    if sub_url.startswith("//"):
        sub_url = "https:" + sub_url
    body = http_get_json(sub_url).get("body", [])
    if not body:
        print("字幕文件为空", file=sys.stderr)
        sys.exit(2)

    md = transcription_markdown(
        title=view["title"], part=part, owner=view["owner"]["name"],
        duration=view["duration"], bvid=bvid, page=args.page,
        source=f"CC字幕（{track['lan_doc']}）",
        segments=[(item["from"], item["content"]) for item in body],
    )
    out = args.output or f"{bvid}" + (f"_p{args.page}" if args.page > 1 else "") + "_transcript.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已保存: {out}（{len(body)} 段字幕）")


# ---------------------------------------------------------------- 转录

def preload_nvidia_libs() -> None:
    """如果通过 pip 安装了 nvidia-*-cu12 运行库，把其 lib 目录预载入，
    让 ctranslate2（不自带CUDA运行库）能找到 libcublas/libcudnn。"""
    candidates = set()
    for path in sys.path:
        for lib in glob.glob(os.path.join(path, "nvidia", "*", "lib")):
            candidates.add(lib)
    for lib_dir in sorted(candidates):
        for so in glob.glob(os.path.join(lib_dir, "lib*.so*")):
            try:
                ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def pick_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def load_model(model_size: str, device: str):
    # 国内网络默认走 hf-mirror 镜像；用户显式设置了 HF_ENDPOINT 时尊重其配置。
    # xet 协议镜像不支持，必须禁用。
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    from faster_whisper import WhisperModel

    if device == "cuda":
        preload_nvidia_libs()
        for compute_type in ("int8_float16", "int8"):
            try:
                return WhisperModel(model_size, device="cuda", compute_type=compute_type)
            except Exception as e:
                last_err = e
        print(f"GPU 加载失败（{last_err}），回退 CPU。", file=sys.stderr)
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def cmd_transcribe(args) -> None:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("缺少依赖：pip install yt-dlp faster-whisper", file=sys.stderr)
        sys.exit(1)
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        print("缺少依赖：pip install faster-whisper", file=sys.stderr)
        sys.exit(1)

    bvid = extract_bvid(args.url)
    view = fetch_view(bvid)
    cid, part = resolve_cid(view, args.page)

    url = f"https://www.bilibili.com/video/{bvid}"
    if args.page > 1:
        url += f"?p={args.page}"
    if args.to:
        url += ("&" if "?" in url else "?") + f"t={args.to}"

    import tempfile
    tmpdir = tempfile.mkdtemp(prefix=f"bvn_{bvid}_")
    audio_path = os.path.join(tmpdir, "audio.m4a")
    print(f"下载音频: {view['title']}" + (f"（P{args.page} {part}）" if args.page > 1 else ""), flush=True)
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": audio_path,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    if not os.path.exists(audio_path):
        # 某些源直接给出 webm/opus 等容器，找到实际产物即可（faster-whisper 经 ffmpeg 解码）
        produced = [p for p in os.listdir(tmpdir) if not p.endswith(".part")]
        if not produced:
            raise RuntimeError("音频下载失败")
        audio_path = os.path.join(tmpdir, produced[0])

    device = pick_device(args.device)
    print(f"加载 Whisper 模型 {args.model}（device={device}），首次使用会先下载模型…", flush=True)
    model = load_model(args.model, device)

    print("开始转录（长视频可能需要数分钟到数十分钟）…", flush=True)
    segments_iter, info = model.transcribe(
        audio_path, language=args.language, beam_size=5, vad_filter=True)
    segments = [(seg.start, seg.text.strip()) for seg in segments_iter]

    device_used = f"Whisper {args.model}（{device}）"
    md = transcription_markdown(
        title=view["title"], part=part, owner=view["owner"]["name"],
        duration=int(info.duration), bvid=bvid, page=args.page,
        source=device_used, segments=segments,
    )
    out = args.output or f"{bvid}" + (f"_p{args.page}" if args.page > 1 else "") + "_transcript.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    total_chars = sum(len(t) for _, t in segments)
    print(f"转录完成: {len(segments)} 段 / {total_chars} 字 / 音频 {fmt_duration(int(info.duration))}")
    print(f"已保存: {out}")

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------- 弹幕

def cmd_danmaku(args) -> None:
    import zlib
    bvid = extract_bvid(args.url)
    view = fetch_view(bvid)
    cid, _ = resolve_cid(view, args.page)
    req = urllib.request.Request(
        f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}", headers=API_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    try:
        xml = zlib.decompress(raw, -zlib.MAX_WBITS).decode("utf-8", errors="ignore")
    except zlib.error:
        xml = raw.decode("utf-8", errors="ignore")

    danmakus = re.findall(r'<d p="([\d.]+),.*?">(.*?)</d>', xml)
    danmakus.sort(key=lambda x: float(x[0]))
    lines = [f"[{format_ts(float(t))}] {text}" for t, text in danmakus]
    if args.top:
        lines = lines[: args.top]
    print("\n".join(lines) if lines else "该视频没有弹幕")


# ---------------------------------------------------------------- 公共输出

def transcription_markdown(title, part, owner, duration, bvid, page, source, segments):
    lines = [
        f"# {title}" + (f"（P{page} {part}）" if page > 1 and part != title else ""),
        "",
        f"- UP主：{owner}",
        f"- 时长：{fmt_duration(int(duration))}",
        f"- 链接：https://www.bilibili.com/video/{bvid}" + (f"?p={page}" if page > 1 else ""),
        f"- 文本来源：{source}",
        f"- 生成时间：{__import__('datetime').datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## 转录文本",
        "",
    ]
    lines.extend(f"**[{format_ts(t)}]** {text}\n" for t, text in segments)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="视频元信息 + 是否有CC字幕")
    p.add_argument("url")
    p.add_argument("--page", type=int, default=1)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("subtitles", help="提取CC字幕")
    p.add_argument("url")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_subtitles)

    p = sub.add_parser("transcribe", help="下载音频并本地转录")
    p.add_argument("url")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("-m", "--model", default=DEFAULT_MODEL,
                   choices=["tiny", "base", "small", "medium", "large-v3"])
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--language", default="zh", help="音频语言，默认 zh")
    p.add_argument("--to", help="从第几秒开始（调试用）")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("danmaku", help="提取弹幕")
    p.add_argument("url")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--top", type=int, help="只取前N条")
    p.set_defaults(func=cmd_danmaku)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)
    except (ValueError, RuntimeError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
