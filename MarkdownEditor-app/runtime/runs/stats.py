# run-name: stats
# 数据形式：形式4 键值对向量（样例中为 A == 3 这类写法）
# 数据点写法：@@ MDE_甲{A == 3, B == 4, C == 5}
# 执行点写法：@@ MDE from stats import add is 甲
# 执行点写法：@@ MDE from stats import sub is 甲
# 执行点写法：@@ MDE from stats import mul is 甲
# 执行点写法：@@ MDE from stats import div is 甲
# 执行点写法：@@ MDE from stats import median is 甲
# 执行点写法：@@ MDE from stats import mean is 甲
# 执行点写法：@@ MDE from stats import stdev is 甲
# 执行点写法：@@ MDE from stats import rsd is 甲
# 返回值：各函数各自返回 str，如 add → 和 12、rsd → 相对标准偏差 42.6%
# 注意：值须可转数字，非数字项跳过；除数为 0、样本不足 2 个、平均数为 0 时返回说明文字
import statistics

def _nums(data):
    out = []
    for v in data['kv'].values():
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    for item in data['vals']:
        seq = item if isinstance(item, list) else [item]
        for v in seq:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
    return out

def add(data):
    n = _nums(data)
    if not n:
        return '未找到可计算的数字，请检查数据点写法'
    return '和 ' + str(sum(n))

def sub(data):
    n = _nums(data)
    if not n:
        return '未找到可计算的数字，请检查数据点写法'
    r = n[0]
    for x in n[1:]:
        r -= x
    return '差 ' + str(r)

def mul(data):
    n = _nums(data)
    if not n:
        return '未找到可计算的数字，请检查数据点写法'
    r = 1.0
    for x in n:
        r *= x
    return '积 ' + str(r)

def div(data):
    n = _nums(data)
    if len(n) < 2:
        return '需要至少两个数字'
    r = n[0]
    for x in n[1:]:
        if x == 0:
            return '除数不能为 0'
        r /= x
    return '商 ' + str(r)

def median(data):
    n = _nums(data)
    if not n:
        return '未找到可计算的数字，请检查数据点写法'
    return '中位数 ' + str(statistics.median(n))

def mean(data):
    n = _nums(data)
    if not n:
        return '未找到可计算的数字，请检查数据点写法'
    return '平均数 ' + str(statistics.fmean(n))

def stdev(data):
    n = _nums(data)
    if len(n) < 2:
        return '标准差需要至少两个数字'
    return '标准差 ' + str(statistics.stdev(n))

def rsd(data):
    n = _nums(data)
    if len(n) < 2:
        return '相对标准偏差需要至少两个数字'
    m = statistics.fmean(n)
    if m == 0:
        return '平均数为 0，相对标准偏差无定义'
    return '相对标准偏差 ' + str(statistics.stdev(n) / abs(m) * 100) + '%'

def run(data):
    return add(data)