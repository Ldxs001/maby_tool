# -*- coding: utf-8 -*-
"""MDEditor low runner 宣传片 · 合成器
   python compose.py
   入：raw10/capture.mp4（record.js 产出的无声画面轨）
       tts/audio/000N_A.wav（gen_narration.py 产出的旁白，N 段）
       podcast-maker 音乐库/_draft.wav（BGM）
   出：MDEditor-lowrunner.mp4（成品，覆盖写入）
   旁白入点由 tts_meta.json 实测时长自动推算（前缀和），与 demo-lowrunner.html TL / record.js CHECKS 同源对齐。
"""
import io
import json
import os
import subprocess

FF = (r"C:\Users\sm001\AppData\Local\Microsoft\WinGet\Packages"
      r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw10", "capture.mp4")
VID = os.path.join(HERE, "video_only.mp4")
NARR = os.path.join(HERE, "narr.m4a")
BGM_A = os.path.join(HERE, "bgm.m4a")
TTS = os.path.join(HERE, "tts", "audio")
META = os.path.join(HERE, "tts", "tts_meta.json")
BGM = r"C:\Users\sm001\WorkBuddy\podcast-maker\音乐库\_draft.wav"
FINAL = r"C:\Users\sm001\WorkBuddy\maby_tool\MarkdownEditor-app\MDEditor-lowrunner.mp4"


def run(args, what):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("[FAIL] %s\n%s" % (what, (r.stderr or "")[-600:]))
    print("  ok  %s" % what)


def main():
    for p in (RAW, BGM, META):
        if not os.path.exists(p):
            raise SystemExit("[FAIL] 缺少输入：%s" % p)

    with io.open(META, encoding="utf-8") as f:
        durs = json.load(f)["durations"]
    N = len(durs)
    # 旁白入点 = 实测时长前缀和（段间无额外间隙；气口由 TTS 标点停顿自然产生）
    DELAYS = [0]
    for d in durs[:-1]:
        DELAYS.append(DELAYS[-1] + int(round(d * 1000)))
    DUR = DELAYS[-1] / 1000.0 + durs[-1] + 0.3   # DELAYS 为毫秒前缀和，转秒后与末段时长相加
    print("旁白段数 %d，入点(ms)=%s，成片时长 %.2fs" % (N, DELAYS, DUR))

    # 1) 画面轨裁到成片时长
    run([FF, "-y", "-i", RAW, "-vf", "trim=0:%.1f,setpts=PTS-STARTPTS" % DUR,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-an", VID], "1/4 画面轨 → video_only.mp4")

    # 2) 旁白轨：N 段各延迟到自己的场景起点
    ins, flts = [], []
    for i, d in enumerate(DELAYS):
        wav = os.path.join(TTS, "%04d_A.wav" % i)
        if not os.path.exists(wav):
            raise SystemExit("[FAIL] 缺少旁白：%s" % wav)
        ins += ["-i", wav]
        flts.append("[%d:a]adelay=%d:all=1[a%d]" % (i, d, i))
    flt = ";".join(flts) + ";" + "".join("[a%d]" % i for i in range(N)) \
        + "amix=inputs=%d:normalize=0[nar]" % N
    run([FF, "-y"] + ins + ["-filter_complex", flt, "-map", "[nar]",
         "-ar", "48000", "-ac", "2", NARR], "2/4 %d 段旁白 → narr.m4a" % N)

    # 3) BGM：滤镜内 aloop 有限循环(约128s)铺满，压低音量限码率；
    #    成片时长由第4步 -shortest 对齐画面轨(约106s)，不在此用 -t(ffmpeg 对滤镜无限流截断不可靠)
    run([FF, "-y", "-i", BGM, "-af", "volume=0.13,aloop=loop=7:size=2000000",
         "-c:a", "aac", "-b:a", "96k", BGM_A], "3/4 BGM → bgm.m4a")

    # 4) 合流：画面 + 旁白 + BGM
    run([FF, "-y", "-i", VID, "-i", NARR, "-i", BGM_A,
         "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[aout]",
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", "-shortest", FINAL], "4/4 合流 → MDEditor-lowrunner.mp4")

    print("\n成品：%s  %.2f MB" % (FINAL, os.path.getsize(FINAL) / 1048576))


if __name__ == "__main__":
    main()
