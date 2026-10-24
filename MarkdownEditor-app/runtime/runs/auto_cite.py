# run-name: auto_cite
# 依据：global；利用 data['marks'] 里的标记列表，按顺序生成 ^[x] 替换文本。
def run(data):
    marks = data.get('marks') or []
    # 遍历所有找到的标记，生成对应的上标格式
    return ['^{[%d]}' % (i + 1) for i in range(len(marks))]