#!/usr/bin/env bash
# 环境自检：报告哪些功能可用、缺什么
set -u

PASS=0; FAIL=0
ok()   { echo "  [OK] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [缺] $1"; FAIL=$((FAIL+1)); }
chk()  { command -v "$1" >/dev/null 2>&1 && ok "$1 $2" || bad "$1 —— $3"; }
pym()  { python3 -c "import $1" 2>/dev/null && ok "python3-$1" || bad "python3-$1 —— $2"; }

echo "bilibili-video-notes 环境自检"
echo "== 字幕提取路径（无第三方依赖，理应总是可用）="
chk python3 "" "安装 Python 3.8+"
python3 -c "import urllib.request, json, zlib" 2>/dev/null && ok "标准库 urllib/json/zlib" || bad "标准库异常"

echo "== 转录路径（无CC字幕的视频需要）="
pym yt_dlp   "pip install yt-dlp"
pym faster_whisper "pip install faster-whisper"
chk ffmpeg "" "安装 ffmpeg（转录解码需要）"
python3 -c "import ctranslate2; n=ctranslate2.get_cuda_device_count(); print('  [info] CUDA 设备:', n)"

echo "== 模型缓存 ="
CACHE="${HF_HOME:-$HOME/.cache}/huggingface"
ls "$CACHE"/hub 2>/dev/null | grep -q "whisper" && ok "已有 Whisper 模型缓存" || echo "  [info] 尚无模型缓存，首次转录会自动下载（small≈466MB）"

echo
echo "结果: $PASS 项可用, $FAIL 项缺失"
[ $FAIL -eq 0 ] && echo "全部功能可用" || echo "缺的项按上面提示安装即可；只缺转录相关不影响字幕提取"
