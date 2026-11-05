#!/usr/bin/env bash
# Waste of Time 专用母带链：收紧超低频、提升人声存在感与高频空气感，保留更多动态。
# 用法: scripts/enhance_waste_of_time.sh input.wav output.wav
set -euo pipefail
IN="$1"; OUT="$2"
CHAIN="aformat=sample_fmts=dbl,highpass=f=30:poles=2,equalizer=f=45:t=q:w=1.0:g=-2,equalizer=f=260:t=q:w=1.0:g=-1.5,equalizer=f=3000:t=q:w=1.2:g=2,highshelf=f=9000:g=3:t=s:w=0.6,extrastereo=m=1.12:c=false,acompressor=threshold=-18dB:ratio=1.6:attack=30:release=250:makeup=1:knee=6"
LIM="volume=5.7dB,aresample=192000:resampler=soxr,alimiter=limit=0.85:attack=3:release=80:level=false:asc=1,aresample=48000:resampler=soxr:precision=28"
ffmpeg -hide_banner -y -i "$IN" -af "$CHAIN,$LIM" -c:a pcm_s24le "$OUT"
