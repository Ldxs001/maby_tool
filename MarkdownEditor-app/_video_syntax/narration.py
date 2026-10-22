# -*- coding: utf-8 -*-
"""语法与排版宣传片旁白（13 段，对应 demo-syntax.html 的 13 个场景）

原则（沿用 MDEditor-intro 口径）：
  1. 正规产品介绍口径，无第一人称、无播客腔（不出现"这一集/欢迎收听/订阅"）；
  2. 每段对应一个画面场景，内容与该场景动画严格对齐；
  3. 时长由合成音频驱动，场景起点随音频回填（下方 scene_start 为初版占位，
     与 demo-syntax.html TL / record.js CHECKS / compose.py DELAYS 四处同步维护）。

场景时间线（起点随音频回填，初版占位）：
  s0 标题卡      0.0
  s1 基础语法    ~5.5
  s2 列表方言    ~13.5
  s3 代码块      ~22.5
  s4 表格对齐    ~28.5
  s5 公式        ~34.5
  s6 图表引擎    ~41.5
  s7 图片宽度    ~50.5
  s8 分栏        ~58.0
  s9 缩进块      ~64.0
  s10 排版面板   ~71.0
  s11 语法速查   ~79.0
  s12 收尾       ~88.5
"""

SEGMENTS = [
    dict(
        idx=0, scene="s0", scene_start=0.0, target_sec=7.0,
        text=(
            "MDEditor，本地 Markdown 编辑器，用一套自有方言把写作、排版、导出收进一个窗口。"
        ),
    ),
    dict(
        idx=1, scene="s1", scene_start=7.0, target_sec=10.0,
        text=(
            "井号写标题，双星加粗、单星斜体、波浪线删除线、反引号包代码；大于号写引用——左边写，右边立刻渲染。"
        ),
    ),
    dict(
        idx=2, scene="s2", scene_start=17.0, target_sec=11.0,
        text=(
            "列表是方言第一处不同：加号实心、减号空心，样式跟标记走；星号不作列表。任务用中括号 x，有序列表按编号接力。"
        ),
    ),
    dict(
        idx=3, scene="s3", scene_start=28.0, target_sec=6.0,
        text=(
            "代码块用三反引号包住，后面标注语言，预览就按语言高亮。"
        ),
    ),
    dict(
        idx=4, scene="s4", scene_start=34.0, target_sec=6.5,
        text=(
            "表格竖线分列，第二行冒号定对齐：左、右、居中，一眼可辨。"
        ),
    ),
    dict(
        idx=5, scene="s5", scene_start=40.5, target_sec=7.5,
        text=(
            "公式由 KaTeX 本地渲染：一个美元行内、两个美元块级，断网也能用。"
        ),
    ),
    dict(
        idx=6, scene="s6", scene_start=48.0, target_sec=11.0,
        text=(
            "四种图表引擎离线渲染：mermaid 流程图、dot 拓扑、wavedrom 波形、vega 数据图，写文本即出图。"
        ),
    ),
    dict(
        idx=7, scene="s7", scene_start=59.0, target_sec=8.5,
        text=(
            "图片后跟花括号数字，宽是版面百分比，原图只读；c/l/r 控制单图对齐。"
        ),
    ),
    dict(
        idx=8, scene="s8", scene_start=67.5, target_sec=7.5,
        text=(
            "多图并排用 @ 分栏包起，比例是版面宽度的百分比，几栏相加为一百。"
        ),
    ),
    dict(
        idx=9, scene="s9", scene_start=75.0, target_sec=8.0,
        text=(
            "整体缩进用三个小于号包起，即缩进包围块；紧邻块逐级递进，空行打断继承。"
        ),
    ),
    dict(
        idx=10, scene="s10", scene_start=83.0, target_sec=9.5,
        text=(
            "排版面板上，正文、标题、引用、列表各自独立设字体、字号、对齐；缩进分首行与悬挂。"
        ),
    ),
    dict(
        idx=11, scene="s11", scene_start=92.5, target_sec=8.0,
        text=(
            "一张速查表收全：哪些写法不同于标准 Markdown，哪些是本工具独有。"
        ),
    ),
    dict(
        idx=12, scene="s12", scene_start=100.5, target_sec=5.0,
        text=(
            "MDEditor，写作方言，排版自由。全部离线，永不丢稿。"
        ),
    ),
]

# 音色：与 MDEditor-intro 一致（用户 config 的 tts.qwen3tts_voice_a）
VOICE_A = "library:说书女-惊堂"

if __name__ == "__main__":
    tot = sum(s["target_sec"] for s in SEGMENTS)
    print("共 %d 段，期望总时长约 %.1f 秒（场景跨度 %.1f 秒）"
          % (len(SEGMENTS), tot, SEGMENTS[-1]["scene_start"] + SEGMENTS[-1]["target_sec"]))
    for s in SEGMENTS:
        print("  [%d] @%5.1fs  %2d 字  %s..."
              % (s["idx"], s["scene_start"], len(s["text"]), s["text"][:24]))
