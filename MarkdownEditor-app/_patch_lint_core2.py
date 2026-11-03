# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_patch_lint_core2.py -- lint 补丁二：同族嵌套零宽检测（D204）

_scanBeginBlock 把嵌套的同族 begin/end 对整对加 \\u200b 前缀（渲染=字面露出），
此前无任何诊断。本补丁在四个 _scanBeginBlock 调用点扫描结果中的零宽行，
命中即上报 warn。渲染输出零变化（只读检查）。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "markdown-editor.html")

EDITS = [
    # 辅助函数：挂在 _dgE 之后
    ("""  function _dgE(rel,code,msg,sev){
    if(_dg)_dg.push({line:_base+rel+1,code:code,msg:msg,sev:sev||'err'});
  }""",
     """  function _dgE(rel,code,msg,sev){
    if(_dg)_dg.push({line:_base+rel+1,code:code,msg:msg,sev:sev||'err'});
  }
  /* v2.22.0 同族嵌套检测：_scanBeginBlock 把嵌套的同族 begin/end 对整对加
     \\u200b 前缀（渲染=字面露出），此前静默。结果里有零宽行即报 warn。 */
  function _dgZw(inner){
    if(!_dg)return;
    for(var _zi=0;_zi<inner.length;_zi++){
      if(inner[_zi].charCodeAt(0)===0x200b){
        _dgE(i+1+_zi,'D204','同族嵌套：内层 begin/end 对被零宽处理（fill/full/page/color 不支持嵌套自身）','warn');
        return;
      }
    }
  }"""),

    # fill 调用点
    ("""      if(!fclosed){_dgE(i,'D203','fill 未闭合：到文末没有 @@ end fill，整块按普通文本渲染');_dgHit=true;}
      if(fclosed){""",
     """      if(!fclosed){_dgE(i,'D203','fill 未闭合：到文末没有 @@ end fill，整块按普通文本渲染');_dgHit=true;}
      _dgZw(finner);
      if(fclosed){"""),

    # color 调用点
    ("""      if(!cclosed){_dgE(i,'D212','color 未闭合：缺 @@ end color，内容照常渲染');_dgHit=true;}
      if(cval&&cclosed){""",
     """      if(!cclosed){_dgE(i,'D212','color 未闭合：缺 @@ end color，内容照常渲染');_dgHit=true;}
      _dgZw(cinner);
      if(cval&&cclosed){"""),

    # full 调用点
    ("""      var _ur=_scanBeginBlock(lines,i+1,['full']);
      var uinner=_ur.inner,uclosed=_ur.closed,uj=_ur.next;
      if(uclosed){""",
     """      var _ur=_scanBeginBlock(lines,i+1,['full']);
      var uinner=_ur.inner,uclosed=_ur.closed,uj=_ur.next;
      _dgZw(uinner);
      if(uclosed){"""),

    # page 调用点
    ("""        var _pgr=_scanBeginBlock(lines,i+1,['page']);
        var pginner=_pgr.inner,pgclosed=_pgr.closed,pgj=_pgr.next;
        if(pgclosed){""",
     """        var _pgr=_scanBeginBlock(lines,i+1,['page']);
        var pginner=_pgr.inner,pgclosed=_pgr.closed,pgj=_pgr.next;
        _dgZw(pginner);
        if(pgclosed){"""),
]


def main():
    s = io.open(P, encoding="utf-8").read()
    bad = []
    for n, (old, new) in enumerate(EDITS, 1):
        c = s.count(old)
        if c != 1:
            bad.append("R%d count=%d" % (n, c))
            continue
        s = s.replace(old, new)
    if bad:
        print("FAILED: " + "; ".join(bad))
        return 1
    io.open(P, "w", encoding="utf-8", newline="").write(s)
    s2 = io.open(P, encoding="utf-8").read()
    bad2 = []
    for n, (old, new) in enumerate(EDITS, 1):
        if s2.count(new) != 1:
            bad2.append("R%d new-count!=1" % n)
    if bad2:
        print("WRITE OK but VERIFY FAILED: " + "; ".join(bad2))
        return 1
    print("PATCH2 OK: %d 处替换落盘且回读校验通过" % len(EDITS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
