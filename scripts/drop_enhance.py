#!/usr/bin/env python3
"""分段母带处理：自动检测 Drop（wobble bass 段），只在 Drop 段额外加强。

用法: python3 scripts/drop_enhance.py input.flac output.wav [--target -10] [--drop-gain 2.0] [--report]

流程:
  1. ffmpeg 渲染「基础链」（EQ、120Hz 以下低频单声道、拓宽高频、轻压缩）
  2. ffmpeg 在基础链之后渲染「Drop 链」（低音饱和谐波、超低频提升、并行压缩、更宽、更亮）
  3. 按检测到的 Drop 区间（30-150Hz 能量占比高且整体响）用包络混合两条链，Drop 段额外 +drop_gain dB
  4. 统一增益到目标响度，经 4 倍过采样限制器输出 48kHz/24-bit
"""
import argparse, subprocess, sys, os, re, tempfile
import numpy as np

SR = 48000
BASE = ("aformat=sample_fmts=dbl:sample_rates=48000:channel_layouts=stereo,highpass=f=28:poles=2,"
        "equalizer=f=45:t=q:w=1.0:g=-1,equalizer=f=280:t=q:w=1.0:g=-1.5,"
        "equalizer=f=3200:t=q:w=1.2:g=1.5,highshelf=f=10000:g=2.5:t=s:w=0.6,deesser=i=0.3:m=0.5:f=0.5,"
        "acrossover=split=120:order=4th[lo][hi];[lo]pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1[lom];"
        "[hi]extrastereo=m=1.15:c=false[hiw];[lom][hiw]amix=inputs=2:normalize=0,"
        "acompressor=threshold=-14dB:ratio=1.8:attack=30:release=220:makeup=1:knee=6")
DROP_EXTRA = (
    "[d]asplit=2[m][sat];"
    # 低音饱和：取 60-250Hz 过驱动产生谐波，只保留 >180Hz 的谐波并行混入（小音箱也能听到 bass 咆哮感）
    "[sat]highpass=f=60:poles=2,lowpass=f=250:poles=2,volume=12dB,asoftclip=type=tanh,volume=-15dB,"
    "highpass=f=180:poles=2,lowpass=f=3000[harm];"
    # 150Hz 以上再拓宽、加亮；150Hz 以下（已是单声道）加厚超低频
    "[m]acrossover=split=150:order=4th[l2][h2];"
    "[h2]extrastereo=m=1.18:c=false,highshelf=f=7000:g=1.5:t=s:w=0.6[h3];"
    "[l2]lowshelf=f=90:g=2.5:t=s:w=0.7[l3];"
    "[l3][h3][harm]amix=inputs=3:normalize=0,"
    # 并行压缩增加密度和冲击力
    "acompressor=threshold=-26dB:ratio=6:attack=8:release=120:makeup=4:knee=4:mix=0.35")

# 流行预设（电音流行 / 四拍底鼓）：低音本来就重，重点是把人声推出来
BASE_POP = BASE.replace("equalizer=f=45:t=q:w=1.0:g=-1", "equalizer=f=45:t=q:w=1.0:g=-2") \
               .replace("equalizer=f=3200:t=q:w=1.2:g=1.5", "equalizer=f=2800:t=q:w=1.0:g=2.5") \
               .replace("highshelf=f=10000:g=2.5", "highshelf=f=10000:g=1.5")
CHORUS_EXTRA = (
    # 副歌段：不加低音，只加强人声存在感、宽度和密度
    "[d]acrossover=split=150:order=4th[l2][h2];"
    "[h2]extrastereo=m=1.15:c=false,equalizer=f=3000:t=q:w=1.0:g=1.5[h3];"
    "[l2][h3]amix=inputs=2:normalize=0,"
    "acompressor=threshold=-24dB:ratio=4:attack=10:release=150:makeup=3:knee=4:mix=0.3")

def ff_float(inp, graph, out):
    subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-y", "-i", inp,
                    "-filter_complex", graph + "[o]", "-map", "[o]", "-f", "f32le", "-ar", str(SR), "-ac", "2", out],
                   check=True)
    return np.fromfile(out, np.float32).reshape(-1, 2).astype(np.float64)

def detect_drops(x, hop=0.25, margin=6.0):
    m = x.mean(1); N = int(SR * 1.0); H = int(SR * hop)
    f = np.fft.rfftfreq(N, 1 / SR); win = np.hanning(N)
    L, B = [], []
    for i in range(0, len(m) - N, H):
        P = np.abs(np.fft.rfft(m[i:i + N] * win)) ** 2
        tot = P.sum() + 1e-12
        L.append(10 * np.log10(tot)); B.append(10 * np.log10(P[(f > 30) & (f < 150)].sum() / tot + 1e-12))
    L = np.array(L); B = np.array(B)
    k = int(2 / hop); ker = np.ones(k) / k
    Ls = np.convolve(L, ker, "same"); Bs = np.convolve(B, ker, "same")
    raw = (Bs > -5.0) & (Ls > np.percentile(Ls, 95) - margin)
    # 填补 <3s 的空洞，去掉 <6s 的片段
    seg = raw.copy()
    def runs(a):
        r, s = [], None
        for i, v in enumerate(np.append(a, False)):
            if v and s is None: s = i
            if not v and s is not None: r.append((s, i)); s = None
        return r
    rr = runs(seg)
    for (a0, a1), (b0, b1) in zip(rr, rr[1:]):
        if (b0 - a1) * hop < 3: seg[a1:b0] = True
    out = np.zeros_like(seg)
    for s, e in runs(seg):
        if (e - s) * hop >= 6: out[s:e] = True
    # 帧中心对齐：帧 i 覆盖 [i*H, i*H+N)，中心偏移 0.5s
    segs = [((s * H + N // 2) / SR, (e * H + N // 2) / SR) for s, e in runs(out)]
    return segs

def make_mask(n, segs, attack=0.12, release=1.0, pre=0.35):
    mk = np.zeros(n)
    for s, e in segs:
        s = max(0.0, s - pre)  # 稍微提前，确保 Drop 第一下完整被加强
        a0, a1 = int(s * SR), int((s + attack) * SR)
        r0, r1 = int(e * SR), int((e + release) * SR)
        a1 = min(a1, n); r1 = min(r1, n); r0 = min(r0, n)
        mk[a0:a1] = np.maximum(mk[a0:a1], 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a1 - a0)))
        mk[a1:r0] = 1.0
        mk[r0:r1] = np.maximum(mk[r0:r1], 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r1 - r0)))
    return mk

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--target", type=float, default=-10.0)
    ap.add_argument("--drop-gain", type=float, default=2.0)
    ap.add_argument("--preset", choices=["dubstep", "pop"], default="dubstep",
                    help="dubstep：Drop 加低音饱和与超低频；pop：副歌只加强人声、宽度与密度")
    ap.add_argument("--margin", type=float, default=6.0, help="Drop 判定：比全曲最响处低多少 dB 以内（越小越严格）")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        B, X = (BASE_POP, CHORUS_EXTRA) if a.preset == "pop" else (BASE, DROP_EXTRA)
        base = ff_float(a.inp, "[0:a]" + B, os.path.join(td, "base.f32"))
        drop = ff_float(a.inp, "[0:a]" + B + "[d];" + X,
                        os.path.join(td, "drop.f32"))
        n = min(len(base), len(drop)); base, drop = base[:n], drop[:n]
        segs = detect_drops(base, margin=a.margin)
        for s, e in segs:
            print(f"Drop: {int(s)//60}:{s%60:05.2f} - {int(e)//60}:{e%60:05.2f}", file=sys.stderr)
        mk = make_mask(n, segs)[:, None]
        g = 10 ** (a.drop_gain / 20)
        mix = base * (1 - mk) + drop * g * mk
        raw = os.path.join(td, "mix.f32"); mix.astype(np.float32).tofile(raw)
        fin = ["-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", raw]
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *fin, "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True)
        I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])
        gain = a.target - I
        print(f"pre-limiter I={I:.1f} LUFS, gain={gain:+.1f} dB", file=sys.stderr)
        subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-y", *fin, "-af",
                        f"volume={gain:.2f}dB,aresample=192000:resampler=soxr,"
                        "alimiter=limit=0.85:attack=3:release=80:level=false:asc=1,"
                        "aresample=48000:resampler=soxr:precision=28",
                        "-c:a", "pcm_s24le", a.out], check=True)

if __name__ == "__main__":
    main()
