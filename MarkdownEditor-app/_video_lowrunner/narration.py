# -*- coding: utf-8 -*-
"""low runner 宣传片旁白（12 段，对应 demo-lowrunner.html 的 12 个场景）

原则（沿用 MDEditor-intro / syntax 口径）：
  1. 正规产品介绍口径，无第一人称、无播客腔（不出现"这一集/欢迎收听/订阅"）；
  2. 每段对应一个画面场景，内容与该场景动画严格对齐；
  3. 全部事实逐字取自 docs/MDEditor 使用指南「low runner」章节与 runs/ 示例源码；
  4. 时长由合成音频驱动，场景起点随音频回填（scene_start 为初版占位，
     与 demo-lowrunner.html TL / record.js CHECKS / compose.py DELAYS 四处同步维护）。

场景时间线（起点随音频回填，初版占位）：
  s0 标题卡        0.0
  s1 工作流总览    ~6.5
  s2 数据点语法    ~15.5
  s3 执行点语法    ~26.0
  s4 run 协议      ~36.0
  s5 四则运算示例  ~45.5
  s6 词频统计示例  ~55.5
  s7 管理界面      ~64.5
  s8 AI 生成       ~74.5
  s9 手动与错误    ~83.0
  s10 防护与依赖   ~92.0
  s11 收尾         ~100.0
"""

SEGMENTS = [
    dict(
        idx=0, scene="s0", scene_start=0.0, target_sec=6.5,
        text=(
            "MDEditor low runner，文档内数据自动化计算：在写作中声明数据，用 Python 直接加工。"
        ),
    ),
    dict(
        idx=1, scene="s1", scene_start=6.5, target_sec=9.0,
        text=(
            "写作时声明数据点，执行点调用 run——计算、合并、筛选、统计、画图，结果直接替换进文档。"
        ),
    ),
    dict(
        idx=2, scene="s2", scene_start=15.5, target_sec=10.5,
        text=(
            "数据点写法五种：显性写法显示值，隐性双下划线只为运行供数；别名池定向喂给指定执行点，裸数据进原文兜底。"
        ),
    ),
    dict(
        idx=3, scene="s3", scene_start=26.0, target_sec=10.0,
        text=(
            "执行点一行调用：import 执行 run 库里的模块；加 is 切到别名池；from 形式还能指定到具体函数。"
        ),
    ),
    dict(
        idx=4, scene="s4", scene_start=36.0, target_sec=9.5,
        text=(
            "run 代码协议极简：函数名固定 run；入参 kv 是按等号剥离好的键值，raw 是原文兜底；返回字符串，替换执行点。"
        ),
    ),
    dict(
        idx=5, scene="s5", scene_start=45.5, target_sec=10.0,
        text=(
            "默认示例四则运算：表格里声明苹果三、梨四，执行点调用加法函数，渲染后自动算出七，全程无需手动操作。"
        ),
    ),
    dict(
        idx=6, scene="s6", scene_start=55.5, target_sec=9.0,
        text=(
            "第二个默认示例词频统计：词表和长文都写成数据点，run 自动轮询统计每个词的出现次数，结果写回文档。"
        ),
    ),
    dict(
        idx=7, scene="s7", scene_start=64.5, target_sec=10.5,
        text=(
            "工具栏 run 按钮打开管理界面：运行模式三选一，即改即生效；run 库全文档共用；保存自动做依赖检测，缺哪个包红色列出并给出安装命令。"
        ),
    ),
    dict(
        idx=8, scene="s8", scene_start=75.0, target_sec=8.5,
        text=(
            "不会写代码也没关系：说出需求，AI 按协议生成代码并建议名称，人工查阅后再保存入库。"
        ),
    ),
    dict(
        idx=9, scene="s9", scene_start=83.5, target_sec=9.0,
        text=(
            "手动模式下，执行点渲染为待运行按钮，点一下单独跑，左下角一次跑全部；失败紧跟红色错误和重试按钮，修好即点即跑。"
        ),
    ),
    dict(
        idx=10, scene="s10", scene_start=92.5, target_sec=8.5,
        text=(
            "执行防护齐备：单次超时十秒，输出上限一兆；解释器是自带便携 Python，作图走 matplotlib，返回图片名自动渲染。"
        ),
    ),
    dict(
        idx=11, scene="s11", scene_start=101.0, target_sec=5.5,
        text=(
            "MDEditor low runner——数据写在文档里，计算留在文档里。"
        ),
    ),
]

# 音色：与 MDEditor-intro / syntax 一致
VOICE_A = "library:说书女-惊堂"

if __name__ == "__main__":
    tot = sum(s["target_sec"] for s in SEGMENTS)
    print("共 %d 段，期望总时长约 %.1f 秒（场景跨度 %.1f 秒）"
          % (len(SEGMENTS), tot, SEGMENTS[-1]["scene_start"] + SEGMENTS[-1]["target_sec"]))
    for s in SEGMENTS:
        print("  [%d] @%5.1fs  %3d 字  %s..."
              % (s["idx"], s["scene_start"], len(s["text"]), s["text"][:24]))
