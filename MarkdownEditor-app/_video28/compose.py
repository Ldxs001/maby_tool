# -*- coding: utf-8 -*-
"""MDEditor 2.8 宣传片 · 合成器
   python compose.py
   入：raw28/capture.mp4（record.js 产出的无声画面轨）
       tts/audio/000N_A.wav（gen_narration.py 产出的 9 段旁白）
       tts/timeline.json（实测时长与场景起点，由 gen_narration 后自动回填）
       音乐库/_draft.wav（BGM）
   出：MDEditor-2.8.mp4（成品，覆盖写入）
"""
import json
import os
import subprocess

FF = (r"C:\Users\sm001\AppData\Local\Microsoft\WinGet\Packages"
      r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw28", "capture.mp4")
VID = os.path.join(HERE, "video_only.mp4")
NARR = os.path.join(HERE, "narr.m4a")
BGM_A = os.path.join(HERE, "bgm.m4a")
TTS = os.path.join(HERE, "tts", "audio")
TL = os.path.join(HERE, "tts", "timeline.json")
BGM = r"C:\Users\sm001\WorkBuddy\podcast-maker\音乐库\_draft.wav"
FINAL = r"C:\Users\sm001\WorkBuddy\MarkdownEditor-app\MDEditor-2.8.mp4"

meta = json.load(open(TL, encoding="utf-8"))
DUR = float(meta["total"])
DELAYS = [int(round(s * 1000)) for s in meta["starts"]]
N = len(DELAYS)


def run(args, what):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("[FAIL] %s\n%s" % (what, (r.stderr or "")[-800:]))
    print("  ok  %s" % what)


def main():
    for p in (RAW, BGM, TL):
        if not os.path.exists(p):
            raise SystemExit("[FAIL] 缺少输入：%s" % p)

    # 1) 画面轨裁到成片时长
    run([FF, "-y", "-i", RAW, "-vf", "trim=0:%.2f,setpts=PTS-STARTPTS" % DUR,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-an", VID], "1/4 画面轨 → video_only.mp4")

    # 2) 旁白轨：9 段各延迟到自己的场景起点
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
         "-ar", "48000", "-ac", "2", "-t", "%.2f" % DUR, NARR],
        "2/4 %d 段旁白 → narr.m4a" % N)

    # 3) BGM：循环铺满，压低音量，首尾淡入淡出
    run([FF, "-y", "-stream_loop", "-1", "-i", BGM, "-t", "%.2f" % DUR,
         "-af", "volume=0.12,afade=t=in:st=0:d=2,afade=t=out:st=%.2f:d=2.5"
                % (DUR - 2.5), BGM_A], "3/4 BGM → bgm.m4a")

    # 4) 合流：画面 + 旁白 + BGM，响度归一到视频常用口径
    run([FF, "-y", "-i", VID, "-i", NARR, "-i", BGM_A,
         "-filter_complex",
         "[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[mix];"
         "[mix]loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", "-shortest", FINAL], "4/4 合流 → MDEditor-2.8.mp4")

    print("\n成品：%s  %.2f MB  %.1fs" %
          (FINAL, os.path.getsize(FINAL) / 1048576, DUR))


if __name__ == "__main__":
    main()
