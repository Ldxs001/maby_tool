# -*- coding: utf-8 -*-
"""MDEditor 宣传片旁白（14 段，与 demo.html 的 14 个场景一一对应；商店预告片版，无版本号）

原则：
  1. 不用第一人称，按产品宣发口径；不出现"我们""大家"。
  2. 每段字数按 4.4 字/秒估算，与场景时长对齐；实际时长以 TTS 实测为准，
     合成后回填 scene_start、demo.html 的 TL、record.js 的 CHECKS、compose.py 的 DELAYS。
  3. 不念代码标识符（PORTABLE_PY 之类），只说它是什么，画面负责显示具体行。
  4. scene_start 为 TTS 实测回填值（tts/timeline.json），与 demo.html 的 TL、
     record.js 的 CHECKS、compose.py 的 DELAYS 四处同源。
  5. 重点：排版（s9–s11 三连段）按主人要求说清楚；作图（s4）单列一段。
"""
SEGMENTS = [
    dict(idx=0, scene="s0", scene_start=0.0, target_sec=7.0,
         text="MDEditor。一台编辑器，写文档，跑代码，还能把文档排成书。"),
    dict(idx=1, scene="s1", scene_start=7.2, target_sec=10.0,
         text="写到要算一下的时候，只能切出去：Excel、脚本、画图绕一圈，贴回来的只是一段死数字。"),
    dict(idx=2, scene="s2", scene_start=16.62, target_sec=15.0,
         text="数据写进文档。数据点一行键值，两个下划线是隐性——屏幕不显示，只把数据交给 run。"
              "执行点声明调哪个函数、吃哪个池，一个池可以喂多个执行点。"),
    dict(idx=3, scene="s3", scene_start=32.7, target_sec=11.0,
         text="返回表格，靠 run 自己拼字符串：表头行、分隔行、数据行，缺一行前端就不认。"
              "单元格里的竖线记得转义。"),
    dict(idx=4, scene="s4", scene_start=44.16, target_sec=12.0,
         text="要作图也一样：run 把图画好、存进文档资产目录，返回一个文件名，"
              "柱状图、折线图、环形图就地渲染，图片跟着文档走。"),
    dict(idx=5, scene="s5", scene_start=55.98, target_sec=8.0,
         text="文件名必须逐字相同：写出去叫什么，返回就写什么，扩展名和大小写都别改。"),
    dict(idx=6, scene="s6", scene_start=64.33, target_sec=7.0,
         text="解释器改一行，三方包放进运行时目录，整条链路都在本机。"),
    dict(idx=7, scene="s7", scene_start=71.53, target_sec=7.0,
         text="默认手动：执行点停在待运行，你点它，它才跑。"),
    dict(idx=8, scene="s9", scene_start=77.57, target_sec=11.0,
         text="写完只是第一步，排版才是老大难：导出堆成纯文本，图片乱跑，公式变成乱码，打印没有版式。"),
    dict(idx=9, scene="s10", scene_start=87.96, target_sec=14.0,
         text="MDEditor 内置分页排版：纸张、页边距、页码模板、自动目录，预览里直接是印刷品的样子；"
              "排版面板按元素定字体、字号、首行缩进、三线表。"),
    dict(idx=10, scene="s11", scene_start=102.8, target_sec=12.0,
         text="图片有专门的排版语法：对齐、题注、宽度、间距各管各的；多图吸底拼版，"
              "一页排满自动换页，这是打印级的细节。"),
    dict(idx=11, scene="s12", scene_start=116.13, target_sec=12.0,
         text="数学公式本地渲染；选中一段文字，可以加批注，也可以交给 AI 润色改写——"
              "模型连本地服务，文稿不出机器。"),
    dict(idx=12, scene="s13", scene_start=127.24, target_sec=10.0,
         text="存成自包含文档：正文、图片、数据、run 全部打进一个文件，拷给别人，打开就能看、能跑。"),
    dict(idx=13, scene="s14", scene_start=137.99, target_sec=9.0,
         text="数据进来，结果回去，版式留下来。MDEditor，写文档，跑代码，排成书。"),
]
