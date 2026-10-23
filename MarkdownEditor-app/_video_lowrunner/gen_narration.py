# -*- coding: utf-8 -*-
"""low runner 宣传片旁白：按 podcast-maker 成熟链生成。

不自己拼 HTTP、不自己凑基线 —— 直接调 tts_engine.synthesize(script, out_dir, cfg)。
产物：_video_lowrunner/tts/audio/0000_A.wav ... 0011_A.wav + tts_meta.json（实际时长）
"""
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PM = r"C:\Users\sm001\WorkBuddy\podcast-maker"
sys.path.insert(0, PM)

from narration import SEGMENTS, VOICE_A  # noqa: E402

OUT = os.path.join(HERE, "tts", "audio")
META = os.path.join(HERE, "tts", "tts_meta.json")
PM_OUT = os.path.join(HERE, "tts", "pm_out")
os.makedirs(OUT, exist_ok=True)
os.makedirs(PM_OUT, exist_ok=True)


def main():
    from podcast_maker.config_manager import ConfigManager
    from podcast_maker import tts_engine

    cfg = ConfigManager().load()
    # 与 MDEditor-intro / syntax 一致：锁定 A 角音色
    cfg["tts.qwen3tts_voice_a"] = VOICE_A
    print("引擎: %s | A角: %s | 语速A: %s"
          % (cfg.get("tts.engine"),
             cfg.get("tts.qwen3tts_voice_a"),
             cfg.get("tts.speed_a", 1.0)))
    print("体检开关: timbre_guard=%s  retries=%s"
          % (cfg.get("tts.timbre_guard", True),
             cfg.get("tts.timbre_seed_retries", 3)))

    lines = [{"speaker": "A", "text": s["text"]} for s in SEGMENTS]
    # 体检基线门槛：正式段不足 10 句时补同音色填充行凑基线
    fillers = [
        {"speaker": "A", "text": "分块增量渲染按章节切块，只重渲染变化的部分。"},
        {"speaker": "A", "text": "粘贴的图片会存进同名资源目录，引用自动改写成相对路径。"},
        {"speaker": "A", "text": "导出的分页版自带目录和页码，浏览器里直接打印成 PDF。"},
        {"speaker": "A", "text": "关闭页面之后，本地服务会自己退出，不留后台进程。"},
    ]
    need = max(0, 10 - len(lines))
    lines += fillers[:need]

    r = tts_engine.synthesize(
        lines, PM_OUT, cfg,
        log=lambda m: print("  " + str(m)),
        voice_root=os.path.join(PM, "podcast_maker", "resources", "voices"))
    if not r or not r.get("files"):
        print("合成失败：无产物")
        return 1

    for i in range(len(SEGMENTS)):
        shutil.copyfile(r["files"][i], os.path.join(OUT, "%04d_A.wav" % i))
    durs = [round(float(d), 2) for d in r["durations"][:len(SEGMENTS)]]
    io.open(META, "w", encoding="utf-8").write(
        json.dumps({"durations": durs}, ensure_ascii=False))
    print()
    print("时长:", durs, " 总计 %.2f 秒" % sum(durs))
    print("产物:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
