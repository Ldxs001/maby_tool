# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
# run-name: wordcount
# 数据形式：形式1 单值文本（正文）+ 形式3 纯值向量（关键词列表）
# 数据点写法：@@ MDE_甲{今天遇到一个外国人，他对我说"你好"，我也回应他"你好"。我们聊了一下午，最后我才发现，他说的竟然是中国话。}（这一行是正文）
# 数据点写法：@@ MDE_甲{你好,中国话}（这一行是关键词列表）
# 执行点写法：@@ MDE from wordcount import count is 甲
# 返回值：你好 出现 2 次；中国话 出现 1 次
# 注意：正文一行、关键词一行，两行用同一个池名；关键词随时增删，代码不用改
def count(data):
    texts = [v for v in data['vals'] if isinstance(v, str)]
    words = [w for seq in data['vals'] if isinstance(seq, list) for w in seq]
    if not texts:
        return '未找到正文，请检查数据点写法'
    if not words:
        return '未找到关键词，请在数据点里写一行词列表，如 {你好,中国话}'
    body = ''.join(texts)
    return '；'.join('%s 出现 %d 次' % (w, body.count(w)) for w in words)

def run(data):
    return count(data)