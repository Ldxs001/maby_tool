# -*- coding: utf-8 -*-
"""MDEditor 2.8 宣传片旁白（9 段，与 demo.html 的 9 个场景一一对应）

原则：
  1. 不用第一人称，按产品宣发口径；不出现"我们""大家"。
  2. 每段字数按 4.4 字/秒估算，与场景时长对齐；实际时长以 TTS 实测为准，
     合成后回填 scene_start、demo.html 的 TL、record.js 的 CHECKS、compose.py 的 DELAYS。
  3. 不念代码标识符（PORTABLE_PY 之类），只说它是什么，画面负责显示具体行。
  4. scene_start 为 TTS 实测回填值（tts/timeline.json），与 demo.html 的 TL、
     record.js 的 CHECKS、compose.py 的 DELAYS 四处同源。
"""
SEGMENTS = [
    dict(idx=0, scene="s0", scene_start=0.0, target_sec=8.0,
         text="MDEditor 2.8。数据点写数据，执行点调函数，返回值就地渲染。"),
    dict(idx=1, scene="s1", scene_start=7.9, target_sec=10.0,
         text="写到要算一下的时候，只能切出去：Excel、脚本、画图绕一圈，贴回来的只是一段死数字。"),
    dict(idx=2, scene="s2", scene_start=17.86, target_sec=16.0,
         text="现在把数据写进文档。数据点一行键值，两个下划线是隐性——屏幕不显示，只把数据交给 run。"
              "执行点声明调哪个函数、吃哪个池，一个池可以喂多个执行点。"),
    dict(idx=3, scene="s3", scene_start=33.86, target_sec=14.0,
         text="返回表格，靠 run 自己拼字符串：表头行、分隔行、数据行。缺了分隔行，前端就不认表格，"
              "整段原样当文字。单元格里的竖线要转义。"),
    dict(idx=4, scene="s4", scene_start=48.7, target_sec=14.0,
         text="返回图片，写进当前目录就够了。当前目录就是文档的资产目录，图片跟着文档走，"
              "不用拼任何路径，也不用框架替你画。同名重跑直接覆盖。"),
    dict(idx=5, scene="s5", scene_start=63.09, target_sec=16.0,
         text="文件名必须逐字相同。写出去叫什么，返回就写什么，扩展名和大小写都别改。"
              "写成绝对路径，反而找不到文件。同名重跑覆盖旧的，不会堆出一堆副本。"),
    dict(idx=6, scene="s6", scene_start=78.02, target_sec=14.0,
         text="解释器改一行：服务端那个变量指向便携 Python，没有就用系统解释器。"
              "三方包装在 runtime 下的 pylibs，安装要带参数，版本对上三点十一。"),
    dict(idx=7, scene="s7", scene_start=92.41, target_sec=12.0,
         text="默认手动。执行点停在待运行，你点它，它才跑。想自动，切成立即或者等待几秒，选一次就记住。"),
    dict(idx=8, scene="s8", scene_start=104.24, target_sec=10.0,
         text="数据进来，结果回去，代码只在你自己机器上跑。MDEditor 2.8，在文档里跑自己的代码。"),
]
