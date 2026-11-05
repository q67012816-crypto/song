#!/usr/bin/env bash
# Afterglow 专用母带链（源文件为 192kbps MP3，18kHz 以上被编码器切除）：
# 收紧超低频、轻度提升人声存在感，用轻度谐波激励补一点高频泛音，保留动态。
# 用法: scripts/enhance_afterglow.sh input.mp3 output.wav
set -euo pipefail
IN="$1"; OUT="$2"
CHAIN="aformat=sample_fmts=dbl,highpass=f=30:poles=2,equalizer=f=50:t=q:w=1.0:g=-1.5,equalizer=f=280:t=q:w=1.0:g=-1.5,equalizer=f=3000:t=q:w=1.2:g=1.5,highshelf=f=9000:g=2:t=s:w=0.6,aexciter=level_in=1:level_out=1:amount=0.6:drive=5:blend=0:freq=9000:ceil=20000,extrastereo=m=1.1:c=false,acompressor=threshold=-18dB:ratio=1.6:attack=30:release=250:makeup=1:knee=6"
LIM="volume=5.5dB,aresample=192000:resampler=soxr,alimiter=limit=0.85:attack=3:release=80:level=false:asc=1,aresample=48000:resampler=soxr:precision=28"
ffmpeg -hide_banner -y -i "$IN" -map 0:a -af "$CHAIN,$LIM" -c:a pcm_s24le "$OUT"
