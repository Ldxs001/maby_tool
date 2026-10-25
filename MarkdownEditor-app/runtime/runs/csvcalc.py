# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
# run-name: csvcalc
# 数据形式：外部文件引用（v2.8：kv 里一个 .csv 路径，服务端已换成绝对路径）+ 形式4 键值对（参数）
# 数据点写法：@@ MDE_销售{表格 == MDEditor 使用指南.assets/示例销售数据.csv}
# 数据点写法：@@ MDE__销售b{表格 == MDEditor 使用指南.assets/示例销售数据.csv, 运算 == *, 数 == 1.1}
# 执行点写法：@@ MDE from csvcalc import table is 销售
# 执行点写法：@@ MDE from csvcalc import row is 销售c
# 执行点写法：@@ MDE from csvcalc import col is 销售d
# 执行点写法：@@ MDE from csvcalc import cell is 销售e
# 返回值：一律 Markdown 表格字符串（表头 + |---|---| + 数据行），预览区渲染成真表格；
#         出错返回一句中文说明，不抛异常
#
# 读法：只用标准库 csv。编码依次试 utf-8-sig / gbk / utf-8（Excel 导出的中文 csv 常是 gbk）。
# 找文件：先认「表格 / 文件 / 路径 / csv / file」这几个键，再认 kv 里第一个真实存在的 .csv；
#         相对路径按 run 的当前目录（= 本文档资产目录）解析。
#
# 参数（全部写在同池的键值对数据点里，键名中英通用）：
#   行名 / 行        行名按第 1 列文字定位（如 上海静安店）；行号 1-based，表头是第 1 行
#   列名 / 列        列名按表头文字定位（如 一月）；列号 1-based，第 1 列是行标签列
#   行2 / 列2 / 行名2 / 列名2   单元格运算的第二个操作数（不写默认同一个单元格）
#   运算 / op        + - * /（也认 ＋ － ＊ ／ × ÷ 与 加 减 乘 除）
#   数 / n           标量操作数，默认 1
#   小数 / digits    结果最多保留几位小数，默认 6（自动去尾零）
# 不给「运算」= 原样读出来（表格照原样返回），用于确认文件读对了
import csv
import io
import os
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP

_OPS = {
    '+': '+', '＋': '+', '加': '+',
    '-': '-', '－': '-', '—': '-', '减': '-',
    '*': '*', '＊': '*', '×': '*', 'x': '*', 'X': '*', '乘': '*',
    '/': '/', '／': '/', '÷': '/', '除': '/',
}
_FW = str.maketrans('０１２３４５６７８９．－＋％', '0123456789.-+%')
_FILE_KEYS = ('表格', '文件', '路径', '表', 'csv', 'file', 'path')


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
        unit, t = '%', t[:-1]
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


def _fmt(d, nd=6):
    """Decimal → 短字符串：去尾零、最多 nd 位小数、不留 -0。"""
    if d is None:
        return ''
    with localcontext() as ctx:
        ctx.prec = 28
        if d.as_tuple().exponent < -nd:
            d = d.quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    s = format(d.normalize(), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('', '-0') else s


def _calc(a, b, op):
    """(Decimal, unit) × (Decimal, unit) → (Decimal, unit)：加减只在两边单位相同时留 %。"""
    if op == '+':
        return a[0] + b[0], a[1] if a[1] == b[1] else ''
    if op == '-':
        return a[0] - b[0], a[1] if a[1] == b[1] else ''
    if op == '*':
        return a[0] * b[0], ''
    with localcontext() as ctx:
        ctx.prec = 28
        return a[0] / b[0], ''


def _kv(data):
    return data.get('kv') or {}


def _p(data, *names, **kw):
    kv = _kv(data)
    for n in names:
        if n in kv and str(kv[n]).strip() != '':
            return kv[n]
    return kw.get('default')


def _op(data):
    """→ (运算符, None) / (None, None)=没给（原样） / (None, 说明)=给了但不认识。"""
    t = _clean(_p(data, '运算', 'op', '操作'))
    if not t:
        return None, None
    o = _OPS.get(t)
    if not o:
        return None, '运算只认 + - * /（加 减 乘 除）：' + t
    return o, None


def _nd(data):
    """结果保留位数。"""
    t = _clean(_p(data, '小数', 'digits'))
    try:
        return min(max(int(float(t)), 0), 12)
    except (TypeError, ValueError):
        return 6


def _operand(data):
    """标量操作数 → ((Decimal, unit), None) / (None, None)=没给 / (None, 说明)。"""
    v = _p(data, '数', 'n', '值')
    if v is None:
        return None, None
    n = _num(v)
    if n is None:
        return None, '操作数「数」不是数字：' + str(v)
    return n, None


def _exists(p):
    try:
        return os.path.isfile(p)
    except (OSError, ValueError):
        return False


def _csv_path(data):
    """→ (绝对路径, None) 或 (None, 说明文字)。"""
    kv = _kv(data)
    for k in _FILE_KEYS:
        v = kv.get(k)
        if v is None or str(v).strip() == '':
            continue
        p = str(v).strip().strip('"')
        if _exists(p):
            return p if os.path.isabs(p) else os.path.abspath(p), None
        return None, ('找不到文件：' + p
                      + '（数据点里写 <文档名>.assets/文件名.csv，或把文件直接粘进文档）')
    for v in list(kv.values()) + list(data.get('vals') or []):
        if isinstance(v, str) and v.strip().lower().endswith('.csv') \
                and _exists(v.strip()):
            p = v.strip()
            return p if os.path.isabs(p) else os.path.abspath(p), None
    return None, ('没有找到 CSV：请在同池数据点里写 表格 == <文档名>.assets/文件名.csv，'
                  '或把 csv 直接粘进文档')


def _read_csv(path):
    """→ (rows, None) 或 (None, 说明文字)。rows 是等宽二维 str，首行为表头。"""
    raw = None
    for enc in ('utf-8-sig', 'gbk', 'utf-8'):
        try:
            with open(path, 'r', encoding=enc, newline='') as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
        except OSError as e:
            return None, '读不动文件：' + str(e)
    if raw is None:
        return None, '编码认不出来（试过 utf-8 与 gbk）'
    rows = [[(c or '').strip() for c in row] for row in csv.reader(io.StringIO(raw))]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return None, 'CSV 是空的'
    width = max(len(r) for r in rows)
    for r in rows:
        r.extend([''] * (width - len(r)))
    return rows, None


def _esc(s):
    """表格单元格转义：竖线写 \\|，换行压成空格。"""
    return str(s).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ').strip()


def _md(header, body):
    """Markdown 表格字符串：表头 + 分隔行 + 数据行。"""
    out = ['| ' + ' | '.join(_esc(x) for x in header) + ' |',
           '|' + '|'.join(['---'] * len(header)) + '|']
    for r in body:
        out.append('| ' + ' | '.join(_esc(x) for x in r) + ' |')
    return '\n'.join(out)


def _find_row(rows, data, sfx=''):
    """→ (行下标, None) 或 (None, 说明)。行名优先；行号 1-based，表头=第 1 行。"""
    name = _clean(_p(data, '行名' + sfx, 'rowname' + sfx, 'row_name' + sfx))
    if name:
        for i, r in enumerate(rows):
            if _clean(r[0]) == name:
                return i, None
        names = [_clean(r[0]) for r in rows[1:] if _clean(r[0])]
        return None, '没有这一行：' + name + '（可选：' + '、'.join(names) + '）'
    t = _clean(_p(data, '行' + sfx, 'row' + sfx, 'r' + sfx))
    if not t:
        return None, '请给「行名」或「行」'
    for junk in ('第', '行', 'row'):
        t = t.replace(junk, '')
    try:
        i = int(float(t)) - 1
    except ValueError:
        return None, '行号须为数字：' + t
    if i < 0 or i >= len(rows):
        return None, '没有第 ' + str(i + 1) + ' 行（共 ' + str(len(rows)) + ' 行）'
    return i, None


def _find_col(rows, data, sfx=''):
    """→ (列下标, None) 或 (None, 说明)。列名优先；列号 1-based，第 1 列=行标签列。"""
    head = rows[0]
    name = _clean(_p(data, '列名' + sfx, 'colname' + sfx, 'col_name' + sfx))
    if name:
        for i, h in enumerate(head):
            if _clean(h) == name:
                return i, None
        return None, '没有这一列：' + name + '（可选：' + '、'.join(head) + '）'
    t = _clean(_p(data, '列' + sfx, 'col' + sfx, 'c' + sfx))
    if not t:
        return None, '请给「列名」或「列」'
    for junk in ('第', '列', 'col'):
        t = t.replace(junk, '')
    try:
        i = int(float(t)) - 1
    except ValueError:
        return None, '列号须为数字：' + t
    if i < 0 or i >= len(head):
        return None, '没有第 ' + str(i + 1) + ' 列（共 ' + str(len(head)) + ' 列）'
    return i, None


def _apply(raw, b, op, nd):
    """一个单元格按 op 与操作数 b 计算。→ (显示值, 说明或 None)。"""
    a = _num(raw)
    if a is None:
        return str(raw), '不是数字'
    if op == '/' and b[0] == 0:
        return '除数为0', '除数为0'
    v, unit = _calc(a, b, op)
    return _fmt(v, nd) + (unit if unit and op in ('+', '-') else ''), None


def _load(data):
    """→ (rows, None) 或 (None, 说明)：找文件 + 读表，四个函数共用。"""
    p, err = _csv_path(data)
    if err:
        return None, err
    return _read_csv(p)


def table(data):
    """整表：每个数字单元格按「运算」与「数」计算，表头与行标签列原样返回。"""
    rows, err = _load(data)
    if err:
        return err
    op, err = _op(data)
    if err:
        return err
    if not op:
        return _md(rows[0], rows[1:])
    b, err = _operand(data)
    if err:
        return err
    b = b or (Decimal(1), '')
    nd = _nd(data)
    body = []
    for r in rows[1:]:
        line = [r[0]]
        for v in r[1:]:
            line.append(_apply(v, b, op, nd)[0])
        body.append(line)
    return _md(rows[0], body)


def row(data):
    """整行：选定数据行的每个数字列，出「列｜原值｜结果」对照表。"""
    rows, err = _load(data)
    if err:
        return err
    i, err = _find_row(rows, data)
    if err:
        return err
    if i == 0:
        return '第 1 行是表头，请选数据行'
    head, src = rows[0], rows[i]
    op, err = _op(data)
    if err:
        return err
    if not op:
        return _md(['列', '原值'], [[head[c], src[c]] for c in range(1, len(head))])
    b, err = _operand(data)
    if err:
        return err
    b = b or (Decimal(1), '')
    nd = _nd(data)
    body = []
    for c in range(1, len(head)):
        out, why = _apply(src[c], b, op, nd)
        body.append([head[c], src[c], out, why or ''])
    if any(x[3] for x in body):
        return _md(['列', '原值', '结果', '说明'], body)
    return _md(['列', '原值', '结果'], [x[:3] for x in body])


def col(data):
    """整列：选定列的每个数据行，出「行标签｜原值｜结果」对照表。"""
    rows, err = _load(data)
    if err:
        return err
    c, err = _find_col(rows, data)
    if err:
        return err
    if c == 0:
        return '第 1 列是行标签列，请选数字列'
    head = rows[0]
    op, err = _op(data)
    if err:
        return err
    if not op:
        return _md([head[0] or '行', '原值'], [[r[0], r[c]] for r in rows[1:]])
    b, err = _operand(data)
    if err:
        return err
    b = b or (Decimal(1), '')
    nd = _nd(data)
    body = []
    for r in rows[1:]:
        out, why = _apply(r[c], b, op, nd)
        body.append([r[0], r[c], out, why or ''])
    if any(x[3] for x in body):
        return _md([head[0] or '行', '原值', '结果', '说明'], body)
    return _md([head[0] or '行', '原值', '结果'], [x[:3] for x in body])


def cell(data):
    """单元格：取值，或与「数」/另一个单元格（行2 列2 行名2 列名2）做四则。"""
    rows, err = _load(data)
    if err:
        return err
    i, err = _find_row(rows, data)
    if err:
        return err
    c, err = _find_col(rows, data)
    if err:
        return err
    if i == 0 or c == 0:
        return '表头行 / 行标签列不参与单元格运算'
    raw = rows[i][c]
    me = [rows[i][0], rows[0][c]]
    op, err = _op(data)
    if err:
        return err
    if not op:
        return _md(['行', '列', '原值'], [me + [raw]])

    has2 = any(_p(data, k) is not None for k in
               ('行2', 'row2', 'r2', '行名2', 'rowname2', 'row_name2',
                '列2', 'col2', 'c2', '列名2', 'colname2', 'col_name2'))
    if has2:
        i2, err = _find_row(rows, data, '2') if any(
            _p(data, k) is not None for k in ('行2', 'row2', 'r2', '行名2',
                                              'rowname2', 'row_name2')) else (i, None)
        if err:
            return '第二个单元格：' + err
        c2, err = _find_col(rows, data, '2') if any(
            _p(data, k) is not None for k in ('列2', 'col2', 'c2', '列名2',
                                              'colname2', 'col_name2')) else (c, None)
        if err:
            return '第二个单元格：' + err
        b = _num(rows[i2][c2])
        if b is None:
            return '第二个单元格不是数字：' + rows[i2][c2]
        bshow = rows[i2][c2]
    else:
        b, err = _operand(data)
        if err:
            return err
        b = b or (Decimal(1), '')
        bshow = str(_p(data, '数', 'n', '值')) if _p(
            data, '数', 'n', '值') is not None else '1'

    nd = _nd(data)
    out, why = _apply(raw, b, op, nd)
    body = [me + [raw, bshow, out] + ([why] if why else [])]
    header = ['行', '列', '原值', '运算数', '结果'] + (['说明'] if why else [])
    return _md(header, body)


def run(data):
    return table(data)
