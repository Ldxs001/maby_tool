# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
# run-name: auto_cite
# 依据：global；利用 data['marks'] 里的标记列表，按顺序生成 ^[x] 替换文本。
# 数据形式：global 标记（正文里写 内容'''ref 声明标记，执行点写 {global ref} 认领）
# 数据点写法：（不需要数据点）正文中：一段话'''ref
# 执行点写法：@@ MDE from auto_cite import run{global ref}
# 返回值：等长 list[str]，按标记出现顺序逐个替换成 ^{[1]} ^{[2]} …
# 注意：编号只按文档出现顺序递增，不查重、不去重；同一标记被两处认领会两处都改
def run(data):
    marks = data.get('marks') or []
    # 遍历所有找到的标记，生成对应的上标格式
    return ['^{[%d]}' % (i + 1) for i in range(len(marks))]