#!/usr/bin/env bash
# Static Days 母带链（旋律 Dubstep / 电影感流行）
#  - 120Hz 以下低频单声道化（LR4 分频，相位可完全还原），wobble bass 更集中有力
#  - 只拓宽中高频（supersaw / 合唱铺底），低频保持紧实
#  - 收紧超低频、去浑浊、提升人声存在感与空气感，轻度去齿音
#  - 高阈值压缩只作用于 Drop，保留"安静钢琴 -> 爆发 Drop"的动态对比
# 用法: scripts/enhance_static_days.sh input.flac output.wav [超低频增益dB] [目标LUFS]
set -euo pipefail
IN="$1"; OUT="$2"; SUBG="${3:--1.5}"; TARGET="${4:--10.5}"
PRE="aformat=sample_fmts=dbl,highpass=f=28:poles=2,equalizer=f=45:t=q:w=1.0:g=${SUBG},equalizer=f=280:t=q:w=1.0:g=-1.5,equalizer=f=3200:t=q:w=1.2:g=1.5,highshelf=f=10000:g=2.5:t=s:w=0.6,deesser=i=0.3:m=0.5:f=0.5"
XO="acrossover=split=120:order=4th[lo][hi];[lo]pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1[lom];[hi]extrastereo=m=1.15:c=false[hiw];[lom][hiw]amix=inputs=2:normalize=0"
COMP="acompressor=threshold=-14dB:ratio=1.8:attack=30:release=220:makeup=1:knee=6"
G="[0:a]${PRE},${XO},${COMP}"
I=$(ffmpeg -hide_banner -nostats -i "$IN" -filter_complex "${G},ebur128" -f null - 2>&1 | grep -A3 Summary | grep -oP 'I:\s+\K-?[0-9.]+')
GAIN=$(python3 -c "print(round(${TARGET}-(${I}),2))")
echo "pre-limiter I=${I} LUFS, gain=${GAIN} dB" >&2
ffmpeg -hide_banner -nostats -loglevel error -y -i "$IN" -filter_complex \
  "${G},volume=${GAIN}dB,aresample=192000:resampler=soxr,alimiter=limit=0.85:attack=3:release=80:level=false:asc=1,aresample=48000:resampler=soxr:precision=28[out]" \
  -map "[out]" -c:a pcm_s24le "$OUT"
