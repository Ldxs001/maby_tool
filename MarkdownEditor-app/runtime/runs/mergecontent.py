# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
# run-name: mergecontent
# 数据形式：行文抽取 (( ))（片段来自同一句原文；句子只用于显示，不进 data）
# 数据点写法：@@ MDE_甲{今天遇到一个((外国人))，他对我说"你好"，我也回应他"你好"。我们((聊了))一下午，说了((很多各自的见闻))，最后我才发现，他说的竟然是中国话。}（这一行是包含标出内容的原文）
# 执行点写法：@@ MDE from mergecontent import merge is 甲
# 返回值：外国人聊了很多各自的见闻
# 注意：只有这一行数据点；原文里圈几处就合并几处，代码不用改
def merge(data):
    parts = []
    for item in data['vals']:
        if isinstance(item, list):
            parts.extend(str(x) for x in item)
        elif isinstance(item, str):
            parts.append(item)
    if not parts:
        return '未找到标出内容，请用 (( )) 在文中圈出要合并的片段'
    return ''.join(parts)

def run(data):
    return merge(data)