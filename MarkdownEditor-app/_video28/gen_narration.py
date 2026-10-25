# -*- coding: utf-8 -*-
"""MDEditor 2.8 宣传片旁白：走 podcast-maker 的正规 TTS 链。

不自己拼 HTTP：直接调 tts_engine.synthesize(script, out_dir, cfg)，
逐句 synth_line（音色来自 cfg 里 qwen3tts_voice_a 的档案）→ 统一 timbre_repair。

前置：本地 TTS 服务在 9880（CUDA）。启动方式见 README 或 _video28/README.md。
产物：tts/audio/0000_A.wav … 0008_A.wav + tts/tts_meta.json（含每段时长）
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

from narration import SEGMENTS  # noqa: E402

OUT = os.path.join(HERE, "tts", "audio")
META = os.path.join(HERE, "tts", "tts_meta.json")
PM_OUT = os.path.join(HERE, "tts", "pm_out")


def main():
    from podcast_maker.config_manager import ConfigManager
    from podcast_maker import tts_engine

    os.makedirs(OUT, exist_ok=True)
    cfg = ConfigManager().load()
    print("引擎: %s | A角: %s | 语速A: %s"
          % (cfg.get("tts.engine"),
             cfg.get("tts.qwen3tts_voice_a"),
             cfg.get("tts.speed_a", 1.0)))

    lines = [{"speaker": "A", "text": s["text"]} for s in SEGMENTS]
    # 体检基线门槛：正式段不足 10 句时补同音色填充行（不进成片）
    fillers = [
        {"speaker": "A", "text": "数据点在文档里写成一行，框架只负责交给函数。"},
        {"speaker": "A", "text": "执行点跑在本地子进程里，超时十秒，输出上限一兆。"},
        {"speaker": "A", "text": "同一个池的数据可以喂给多个执行点，互不干扰。"},
        {"speaker": "A", "text": "需要换解释器，改服务端那一行就够了。"},
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
