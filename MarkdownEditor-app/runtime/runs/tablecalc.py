# run-name: tablecalc
# 数据形式：形式5 二维表格（vals 里嵌套 list，单元格一律 str）+ 形式4 键值对（参数行）
# 数据点写法：@@ MDE_甲:2(){ 表格 | 项目 | 一月 | 二月 | / | --- | --- | --- | / | 收入 | 100 | 120 | }
# 数据点写法：@@ MDE_甲{行 == 2, 列 == 2, 运算 == *, 数 == 1.1}
# 执行点写法：@@ MDE from tablecalc import cell is 甲
# 执行点写法：@@ MDE from tablecalc import row is 甲
# 执行点写法：@@ MDE from tablecalc import col is 甲
# 执行点写法：@@ MDE from tablecalc import rowagg is 甲
# 执行点写法：@@ MDE from tablecalc import colagg is 甲
# 执行点写法：@@ MDE import tablecalc is 甲
# 返回值：cell → 一个数；row/col → 用「、」连接的一串（不可解析的单元格原样保留）；
#         rowagg/colagg → 一个数；run 等同 cell
# 注意：行号/列号 1-based，与数据点坐标 (rxc) 同一口径，表头行也算第 1 行；
#       单元格可带 % 与千分位、¥$ 前缀、万/亿后缀；不可解析的单元格跳过；
#       除数为 0、行号越界、没有表格时返回中文说明，不抛异常
#
# 参数（全部写在同池的键值对数据点里，键名中英通用）：
#   行 / row / r      1-based 行号，默认 1
#   列 / col / c      1-based 列号，默认 1
#   行2 / row2 / r2   与另一行逐元素运算   ← row
#   列2 / col2 / c2   与另一列逐元素运算   ← col
#   数 / n / 值       标量操作数，默认 1
#   运算 / op          + - * /（也认 ＋ － ＊ ／ × ÷ 与 加 减 乘 除），默认 +
#   分隔 / sep         row/col 结果的连接符，默认「、」
# 操作数优先级：行2/列2 > 数；都没有时 cell 纯取值、row/col 纯取值、*agg 退化为单值
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP

_OPS = {
    '+': '+', '＋': '+', '加': '+', '正': '+',
    '-': '-', '－': '-', '—': '-', '减': '-', '负': '-',
    '*': '*', '＊': '*', '×': '*', 'x': '*', 'X': '*', '乘': '*',
    '/': '/', '／': '/', '÷': '/', '除': '/',
}
_FW = str.maketrans('０１２３４５６７８９．－＋％', '0123456789.-+%')
_NO_TABLE = '未找到二维表格数据，请用 @@ MDE_甲:2(){} 或 :2(2x2){} 写表格'
_BAD_OP = '运算只认 + - * /（加 减 乘 除）'


def _clean(s):
    """单元格/参数 → 去空白、全角转半角、去千分位。返回 str。"""
    if s is None:
        return ''
    t = str(s).translate(_FW).strip()
    return t.replace(',', '').replace('，', '').replace(' ', '').replace('\u3000', '')


def _num(s):
    """'1,200' → (Decimal('1200'), '')；'8%' → (Decimal('8'), '%')；
    '¥56.5' → (Decimal('56.5'), '')；'(5)' → (Decimal('-5'), '')；
    '1.2万' → (Decimal('12000'), '')。不可解析 → None。"""
    t = _clean(s)
    if not t:
        return None
    unit = ''
    if t.endswith('%'):
        unit = '%'
        t = t[:-1]
    for p in ('¥', '$', '￥', '€', '£'):
        if t.startswith(p):
            t = t[1:]
            break
    mult = Decimal(1)
    if t.endswith('亿'):
        mult, t = Decimal(100000000), t[:-1]
    elif t.endswith('万'):
        mult, t = Decimal(10000), t[:-1]
    if t.startswith('(') and t.endswith(')'):
        t = '-' + t[1:-1]
    try:
        return Decimal(t) * mult, unit
    except (InvalidOperation, ValueError):
        return None


def _fmt(d):
    """Decimal → 短字符串：去尾零、最多 10 位小数、不留 -0。"""
    if d is None:
        return ''
    if d.as_tuple().exponent < -10:
        with localcontext() as ctx:
            ctx.prec = 28
            d = d.quantize(Decimal('1e-10'), rounding=ROUND_HALF_UP)
    s = format(d.normalize(), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('', '-0') else s


def _out(v, unit, op):
    """按单位出数：加减法只在两边都带 % 时保留 %，乘除法不带。"""
    return _fmt(v) + (unit if unit and op in ('+', '-') else '')


def _calc(a, b, op):
    """(Decimal, unit) × (Decimal, unit) → (Decimal, unit)。"""
    if op == '+':
        return a[0] + b[0], a[1] if a[1] == b[1] else ''
    if op == '-':
        return a[0] - b[0], a[1] if a[1] == b[1] else ''
    if op == '*':
        return a[0] * b[0], ''
    with localcontext() as ctx:
        ctx.prec = 28
        return a[0] / b[0], ''


def _table(data):
    """vals 里第一个二维表；三层（:3）取第一张。返回 (rows, 张数) """
    for item in (data.get('vals') or []):
        if isinstance(item, list) and item and isinstance(item[0], list):
            if item[0] and isinstance(item[0][0], list):
                return item[0], len(item)
            return item, 1
    return None, 0


def _kv(data):
    return data.get('kv') or {}


def _p(data, *names, **kw):
    kv = _kv(data)
    for n in names:
        if n in kv and str(kv[n]).strip() != '':
            return kv[n]
    return kw.get('default')


def _pos(data, names, default):
    """行号/列号：认 '2' '2.0' '第2行' 'row2'，非法回落默认值。返回 int 或 None。"""
    t = _clean(_p(data, *names, default=str(default)))
    for junk in ('第', '行', '列', 'row', 'col', 'r', 'c', 'R', 'C'):
        t = t.replace(junk, '')
    try:
        return int(float(t))
    except ValueError:
        return None


def _op(data):
    t = _clean(_p(data, '运算', 'op', '操作', default='+'))
    return _OPS.get(t)


def _cell(rows, r, c):
    """(行列表, 行号, 列号) → 单元格原字符串 或 错误说明。"""
    if r is None or c is None:
        return None, '行号/列号须为数字'
    if r < 1 or c < 1:
        return None, '行号/列号从 1 开始'
    if r > len(rows):
        return None, '表格只有 ' + str(len(rows)) + ' 行'
    row = rows[r - 1] if isinstance(rows[r - 1], list) else [rows[r - 1]]
    if c > len(row):
        return None, '第 ' + str(r) + ' 行只有 ' + str(len(row)) + ' 列'
    return row[c - 1], None


def _line(rows, r):
    if r is None:
        return None, '行号须为数字'
    if r < 1:
        return None, '行号从 1 开始'
    if r > len(rows):
        return None, '表格只有 ' + str(len(rows)) + ' 行'
    row = rows[r - 1]
    return (row if isinstance(row, list) else [row]), None


def _column(rows, c, skip_rows=()):
    if c is None:
        return None, '列号须为数字'
    if c < 1:
        return None, '列号从 1 开始'
    out = []
    for i, row in enumerate(rows):
        if i in skip_rows:
            continue
        cells = row if isinstance(row, list) else [row]
        if c <= len(cells):
            out.append(cells[c - 1])
    if not out:
        return None, '第 ' + str(c) + ' 列没有单元格'
    return out, None


def _sep(data):
    return str(_p(data, '分隔', 'sep', default='、'))


def cell(data):
    """单元格：取值，或与「数」/另一单元格（行2+列2）做四则。"""
    rows, _ = _table(data)
    if not rows:
        return _NO_TABLE
    r = _pos(data, ('行', 'row', 'r'), 1)
    c = _pos(data, ('列', 'col', 'c'), 1)
    raw, err = _cell(rows, r, c)
    if err:
        return err
    a = _num(raw)
    r2 = _p(data, '行2', 'row2', 'r2')
    c2 = _p(data, '列2', 'col2', 'c2')
    if r2 is not None or c2 is not None:
        other, err = _cell(rows, _pos(data, ('行2', 'row2', 'r2'), r), _pos(data, ('列2', 'col2', 'c2'), c))
        if err:
            return err
        b = _num(other)
        if b is None:
            return '第二个单元格不是数字：' + str(other)
    elif _p(data, '数', 'n', '值') is not None:
        b = _num(_p(data, '数', 'n', '值'))
        if b is None:
            return '操作数「数」不是数字：' + str(_p(data, '数', 'n', '值'))
    else:
        return str(raw)
    op = _op(data)
    if not op:
        return _BAD_OP
    if a is None:
        return '单元格不是数字：' + str(raw)
    if op == '/' and b[0] == 0:
        return '除数不能为 0'
    v, unit = _calc(a, b, op)
    return _out(v, unit, op)


def row(data):
    """整行逐元素运算：第「行」行 与「行2」/「数」做四则。不可解析的单元格原样保留。"""
    rows, _ = _table(data)
    if not rows:
        return _NO_TABLE
    r = _pos(data, ('行', 'row', 'r'), 1)
    base, err = _line(rows, r)
    if err:
        return err
    other = None
    r2 = _p(data, '行2', 'row2', 'r2')
    if r2 is not None:
        other, err = _line(rows, _pos(data, ('行2', 'row2', 'r2'), r))
        if err:
            return err
    elif _p(data, '数', 'n', '值') is not None:
        other = [_p(data, '数', 'n', '值')] * len(base)
    if other is None:
        return _sep(data).join(str(x) for x in base)
    op = _op(data)
    if not op:
        return _BAD_OP
    out = []
    for i, x in enumerate(base):
        a = _num(x)
        b = _num(other[i]) if i < len(other) else None
        if a is None or b is None:
            out.append(str(x))
            continue
        if op == '/' and b[0] == 0:
            out.append('除数为0')
            continue
        v, unit = _calc(a, b, op)
        out.append(_out(v, unit, op))
    return _sep(data).join(out)


def col(data):
    """整列逐元素运算：第「列」列 与「列2」/「数」做四则。不可解析的单元格原样保留。"""
    rows, _ = _table(data)
    if not rows:
        return _NO_TABLE
    c = _pos(data, ('列', 'col', 'c'), 1)
    base, err = _column(rows, c)
    if err:
        return err
    other = None
    c2 = _p(data, '列2', 'col2', 'c2')
    if c2 is not None:
        other, err = _column(rows, _pos(data, ('列2', 'col2', 'c2'), c))
        if err:
            return err
    elif _p(data, '数', 'n', '值') is not None:
        other = [_p(data, '数', 'n', '值')] * len(base)
    if other is None:
        return _sep(data).join(str(x) for x in base)
    op = _op(data)
    if not op:
        return _BAD_OP
    out = []
    for i, x in enumerate(base):
        a = _num(x)
        b = _num(other[i]) if i < len(other) else None
        if a is None or b is None:
            out.append(str(x))
            continue
        if op == '/' and b[0] == 0:
            out.append('除数为0')
            continue
        v, unit = _calc(a, b, op)
        out.append(_out(v, unit, op))
    return _sep(data).join(out)


def _agg(vals, op):
    """一串原字符串按 op 聚合。返回 (str, unit) 或说明文字。"""
    nums = [n for n in (_num(x) for x in vals) if n is not None]
    if not nums:
        return '这一行/列没有可计算的数字'
    if op == '+':
        v, unit = nums[0][0], nums[0][1]
        for x in nums[1:]:
            v, unit = _calc((v, unit), x, '+')
        return _out(v, unit, '+')
    if op == '*':
        v = Decimal(1)
        for x in nums:
            v *= x[0]
        return _fmt(v)
    if len(nums) < 2:
        return '至少需要两个数字才能做减法/除法'
    v, unit = nums[0]
    for x in nums[1:]:
        if op == '/' and x[0] == 0:
            return '除数不能为 0'
        v, unit = _calc((v, unit), x, op)
    return _out(v, unit, op)


def rowagg(data):
    """行内聚合：把第「行」行里的数字按「运算」合并成一个数（默认求和）。"""
    rows, _ = _table(data)
    if not rows:
        return _NO_TABLE
    r = _pos(data, ('行', 'row', 'r'), 1)
    base, err = _line(rows, r)
    if err:
        return err
    op = _op(data)
    if not op:
        return _BAD_OP
    return _agg(base, op)


def colagg(data):
    """列内聚合：把第「列」列里的数字按「运算」合并成一个数（默认求和）。"""
    rows, _ = _table(data)
    if not rows:
        return _NO_TABLE
    c = _pos(data, ('列', 'col', 'c'), 1)
    base, err = _column(rows, c)
    if err:
        return err
    op = _op(data)
    if not op:
        return _BAD_OP
    return _agg(base, op)


def run(data):
    return cell(data)
