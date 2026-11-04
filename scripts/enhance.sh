#!/usr/bin/env bash
# 音质增强母带处理链 (ffmpeg)。用法: scripts/enhance.sh input.wav output.wav
set -euo pipefail
IN="$1"; OUT="$2"
CHAIN="aformat=sample_fmts=dbl,highpass=f=28:poles=2,equalizer=f=320:t=q:w=1.0:g=-1.5,equalizer=f=3500:t=q:w=1.2:g=1.5,highshelf=f=10000:g=2.5:t=s:w=0.6,extrastereo=m=1.12:c=false,acompressor=threshold=-20dB:ratio=2:attack=25:release=200:makeup=1:knee=4"
LIM="volume=7.4dB,aresample=192000:resampler=soxr,alimiter=limit=0.85:attack=3:release=80:level=false:asc=1,aresample=48000:resampler=soxr:precision=28"
ffmpeg -hide_banner -y -i "$IN" -af "$CHAIN,$LIM" -c:a pcm_s24le "$OUT"
