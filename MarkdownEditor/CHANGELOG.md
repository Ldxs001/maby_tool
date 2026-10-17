# MarkdownEditor 更新日志

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。  
版本号遵循语义版本控制。

体例：只有版本号是标题（`## vX.Y.Z`）；段内分组与要点一律用加粗（`**修复**`／`**变更**`／  
`**新增**`／`**测试**`／`**说明**`），条目写成 `- **短语**：说明`；段与段之间用 `---` 分隔。

文风：每段只写**现象、根因、修法、验证**四件事。不出现第一／二人称叙事，不写与代码行为  
无关的产品定位论证，不用口语化措辞。技术结论直接陈述，不带情绪与元评价。

---

## v1.4.0（2026-10-17）

**修复**

- **表格幽灵列（多余单元格被切出）**：现象——打印导出与预览中，表格右侧多出一列孤立单元格，仅个别行有内容，且该行原单元格尾部残留 `\`、新列起首残留反引号；窄列被挤压成一字一行竖排。根因——前端表格解析器 `splitRow` 对行做裸 `split('|')`，不识别 GFM 转义：单元格内行内代码 `` `\|` `` 中的竖线被当作列分隔符，该行被多切出一格。修法——切分前将 `\|` 替换为占位符、切分后还原为字面竖线（GFM 规范：表格单元格内 `\|` 恒为字面竖线，行内代码内也不例外）；正文行列数对齐表头——超出的单元格合并进本行前一列（以 `|` 接回，内容不丢失），不足的补空单元格使列边框对齐。预览与打印导出共用同一解析器，一处修复两处生效。验证：`_test_table_split.py` 8/8 PASS（测试对象为从 markdown-editor.html 抽取的真实函数源码），浏览器实测同构 9 列表格导出 8 列严丝合缝、行内代码竖线原样保留。

**变更**

- **便携运行时内置 Pillow**：现象——超高长图切片功能依赖 Pillow，而内嵌便携运行时未携带，运行时切片静默退化为整图保留（fail-closed），功能在最终用户环境不可用。修法——官方 wheel（pillow-13.0.0-cp311-cp311-win_amd64）原样解包进 `python/Lib/site-packages/`；许可文本随包保留（wheel 自带合并 LICENSE 覆盖 HPND 核心与捆入 C 库全文），收录 `LICENSES/Pillow-LICENSE.txt` 并更新 `LICENSES/README.txt` 与 `docs/版权与开源组件声明.md`（HPND/MIT-CMU 允许任何目的免费再分发，无传染性，与 AGPL-3.0-or-later 不冲突）。验证：内嵌解释器 `import PIL` 13.0.0 正常，切片 E2E（E42-E47）全绿。

**测试**

- `_test_table_split.py` 新增 8 条全 PASS：`\|` 转义还原、裸竖线多切后合并回前一列（内容不丢）、格数不足补齐、对齐样式、正常表格不受影响。
- `_test_paged_e2e.py` 回归 47/47 PASS（含此前因运行时缺 Pillow 而失败的切片组 E42-E46）；`_test_smd.py` 回归 33/33 PASS。

---

## v1.3.0（2026-10-16）

**本次改动：打印导出排版治理（基础正文样式注入 + 版面缩放纪律 + 图片版面适配）与打印/分页双入口合并**

**新增**

- **打印导出基础正文样式**：现象——分页导出的表格无边框、代码块/引用块无样式。根因——`build_paged_html` 仅注入 @page/页码、katex、目录、排版设置四层 CSS，编辑器预览的基础 `.markdown-body` 样式从未进入导出（`.html` 导出自带基础样式块故无此病）。修法——新增 `PAGED_BASE_CSS` 镜像预览基础样式（表格细边框、表头底色、pre/code/blockquote/hr），以固定色值替代 CSS 变量（导出文档内变量未定义）；注入序在排版设置之前，设置面板 `!important` 规则（如三线表）覆盖关系不变。验证：E2E E2/E3/E18/E19。
- **超高长图切片续排**：现象——2000×5140 级长截图打印导出时，整图压一页只剩 ~95mm 窄条（宽高比物理约束），文字不可读。修法——渲染高超过版心的图由服务端在导出期用 PIL 竖切为小条带（渲染高 = 版心高/6，下限 20mm）满宽续排，如表格跨页一样流入页面剩余空间、接不下才推页（页面留白上限 = 一条带高）；切点吸附静默行——目标切点 ±8mm 窗口内取行亮度最平稳处（截图空白行/段间隙）下刀，不切断文字行、不重叠不遗漏；切片缓存键 = 内容 sha1 + 条带几何（strip_px），几何参数变更时旧切片不复用；切片为导出渲染期产物，写入 `_slice/` 由 `/static` 服务，源资产一个字节不动（SSOT）；PIL 缺失或读图失败原样保留整图（fail-closed）。验证：E2E E41-E47（切片落盘/条数/原引用替换/小图不切/幂等复用）+ 真实文章长图浏览器实测（11 条满宽续排、末条后正文正常接排）。
- **保存时清理无引用资产**：现象——sha1 去重修复前的历史旧包内残留无引用资产死重（实测一包重复收编同一张 1MB 图两份，正文只引用其一）。修法——`_smd` 双守门：`save_from_dir` 保存时对照 doc.md 引用集删除解包目录中未被引用的资产，且孤儿存在即强制全量重建（追加式包结构下增量保存清不掉旧 entry）；`pack_from_dir` 打包时过滤未被引用的文件（另存为/整理同口径）。引用识别口径 `assets/<文件名>` 与包内格式契约一致；删除失败保守留存不阻断保存。夹具同步：T1/T2/T8 旧契约（无引用资产入包）改为引用对齐，新增 T14（目录孤儿 + 包内孤儿一次清除、稳态增量退化）/T16（打包过滤守门）。验证：`_test_smd.py` 33/33 PASS + `_test_paged_e2e.py` 47/47 回归。
- **版面缩放纪律（借鉴 Cogito_Scribit STYLE_GUIDE 一章、十一章）**：现象——长 token 行与超宽单元格在打印态会触发 Chromium 整本 shrink-to-fit 或横向溢出。修法——print 态 `*{box-sizing:border-box}`；pre `white-space:pre-wrap + overflow-wrap:anywhere`（print 无滚动条，超宽行直接裁切）；td/th `word-break:keep-all + overflow-wrap:anywhere`（中文不拆词、超长串兜底断行）；表格 `width:100% + table-layout:auto` 允许跨页切分，`thead{display:table-header-group}` 跨页自动重复表头，`tr/li{break-inside:avoid}` 行不腰斩。验证：E2E E4-E7。
- **引用编号索引表列宽**：现象——表头为 `编号|引用|出处` 的索引表列宽随内容漂移。修法——导出时识别该表头自动加 `ref-table` 类，`table-layout:fixed` 固定列宽 8%/47%/45%（STYLE_GUIDE 1.2），普通表格不受影响。验证：E2E E11-E13。

**变更**

- **目录版式对齐书册规范（STRUCTURE_GUIDE 6.4 + STYLE_GUIDE 11.4）**：现象——目录条目为"标题+裸页码"行内拼接，无点线、页码不成列。修法——条目改 flex 基线行：标题文本 + 点线引导（dotted leader，`flex:1` 撑满）+ 页码右对齐列（`tabular-nums` 等宽数字），一级加粗、二三级缩进保持；页码由填充脚本按标题锚真实落页回填，全部条目页码右缘统一成列、点线与页码留 6px 间距不重叠。验证：E2E E33/E34 + 浏览器实测截图。
- **页码形态对齐书册规范（6.4）**：现象——页码为"第 X 页 / 共 Y 页"居中小字，不符书册惯例。修法——默认模板改纯数字 `{p}`；位置新增「外侧（奇右偶左）」并设为默认（`@bottom-right`/`@bottom-left` 双占位盒，填充脚本按显示页码奇偶选盒）；页码 9pt 灰阶；封面/目录无页码（目录页不编号沿用）；显式选择居中/顶部等位置仍被尊重。前端旧默认一次性迁移（仅当页码模板仍为旧默认串——整组设置从未手动改过——才升级，显式自定义不动）。验证：E2E E35/E36/E38 + 浏览器实测奇页右下「1」。
- **分页规则对齐书籍标准（6.2 逐条）**：现象——分页行为为编辑器自创组合，与书册规范不一致。修法——`h1{break-before:page}` 每篇独立起页；`h2,h3,h4{break-after:avoid}` 标题不落页末；`p{orphans:2;widows:2}` 段落防孤立行；`li{orphans:1;widows:1}`（单行 bullet 配 widows 2 会永久推页留白，6.2 判例）；`hr{break-inside:avoid;break-after:avoid}` 且不加 break-before（hr+h2 保护链整块推页留半页空白，2026-08-28 判例）；纵向结构（table/pre）允许内容单元间拆页——pre 此前误加 `break-inside:avoid` 已去除（长代码块整块搬页仍装不下会溢出裁切）；blockquote 不拆保持。验证：E2E E26-E31。
- **图片版面规则定版**：现象——图片仅有 max 约束、行内随文流。修法——img 改 `display:block` 块级居中（图版独立成行惯例）+ `break-inside:avoid` 图不腰斩 + 既有 max-width/max-height 版面约束（宽超按宽缩、高超按高缩）；渲染高不超版心的图整图原子一页（上页空间不足推页留白，不因剩余空间缩放——图版尺寸稳定纪律）；超过版心的长截图转入切片续排（见「超高长图切片」）。书族正文无光栅图判例（全部为文本标注图），本条按图版惯例与十一章内容盒纪律（内容不超 ICB）执行。验证：E2E E32。

**修复**

- **图片超出版面**：现象——分页导出中高图直接溢出纸面。根因——导出对 img 无任何尺寸约束。修法——img `max-width:100%` + `max-height=纸高−上下边距−2mm`（命名纸张映射表 A0–B5/Letter/Legal/Ledger，自定义纸取 ph，下限 20mm）；浏览器对 img 的 max 约束天然保持宽高比——宽超按宽缩、高超按高缩。验证：E2E E10/E16/E20 + 浏览器截图。
- **长图打印产出连续空白页、图不可见**：现象——2000×5140 长截图打印导出后图消失，图位之后连续多页整页空白。根因——图片占位预算算术缺陷：初版安全余量仅 1mm（A4 图高 246mm），叠加 img 自身 `.8em` 外边距与段落后实际占位 ≈253mm，超出 247mm 版心——图在任一页都放不下，Paged.js 反复推新页并把图溢出裁掉。修法——打印版 img `margin:0 auto`、`p:has(>img){margin:0}`（正文图均包裹在段内，段落外边距同样计入占位）、预算余量改 2mm（A4=245mm）。验证：浏览器实测原图导出（空白页消失）+ E2E E39/E40。
- **打印/分页双入口合并**：现象——「打印」与「分页」两按钮调用同一 `/api/export-paged`，产物完全相同，语义重复。根因——打印按钮历史上为 `window.print()`，因内嵌窗口阻塞改为生成分页 HTML 后与「分页」沦为平行入口。修法——合并为单「打印」按钮（原分页处理器 + 防重入），设置面板文案与诊断信标统一为「打印」，产物名保留「分页版 HTML」。验证：`btnPrint` 引用清零 + inline script `node --check` 通过。
- **目录计入页码**：现象——目录页被编为「第 1 页」，正文从第 2 页起，目录条目页码同步偏移，不符书册惯例。根因——页脚填充脚本按物理页序无脑 `i+1` 填充全部页面，目录条目页码用 Paged.js 原生 `target-counter`（同为物理页序），两处口径都含目录页。修法——页码全部改由填充脚本确定性自管：纯目录页（页内有 `.md-toc-wrap` 且无正文标题锚）不编页码；正文页码 = 物理页序 − 前置纯目录页数，总页数为正文页数；目录条目页码弃用 `target-counter`，由脚本按标题锚真实落页的显示页码回填 `<span class="md-toc-pg">`，与页脚口径严格一致；无目录时行为退化为原物理页序（向后兼容）。验证：E2E E21-E24 + 浏览器实测（目录页脚空白、正文首页「第 1 页 / 共 5 页」、条目 1/2/3/4 与落页一致）。

**测试**

- **`_test_paged_e2e.py` 扩至 47 条全 PASS**：真实服务全链路——基础样式注入、表头跨页重复、行不腰斩、单元格断行纪律、图片版面高度（A4=245.00mm / 自定义 210×140 边距20=98.00mm / Legal=303.60mm）、ref-table 识别与列宽、三线表覆盖顺序、目录规则与填充脚本、超高长图切片（切片落盘/条数/原引用替换/小图不切/幂等复用）、`_test_smd.py` 回归 28/28 PASS；Paged.js 浏览器实测（目录形态/外侧页码/长图续排/末页正文接排）。

---

## v1.2.0

**本次改动：自包含文档格式 `.smd`（正文+图片单文件 ZIP 容器）、增量保存两阶段提交、阈值自动整理、右键/双击关联与原生打开框支持、跨容器资产双向换算与收编三规则、内嵌桥薄化统一写盘入口**

**新增**

- **`.smd` 自包含文档格式**：现象——`.md + <文档名>.assets/` 成对目录在网盘同步、邮件发送、移动归档时易散。修法——`_smd.py` 实现 ZIP 容器（`doc.md` + `assets/` + `meta.json`），服务端三条路由（`GET /api/file` 读、`POST /api/file` 写、`POST /api/paste-image` 贴图）按后缀分支：读取时解包到 `runtime/tmp/<hash>/` 幂等工作目录并返回图片基址，前端 `fixLocalImages` 以该基址走现有 `/img` 代理；写入时正文落工作目录 `doc.md` 后增量回包。普通 `.md` 全链路行为不变。验证：`_test_smd.py` 17/17 通过（详见测试节）。
- **增量保存（两阶段提交）**：现象——大量图片时保存若整包重写需重压全部资源（8MB 图包为秒级~十秒级）。修法——顺序字节拷贝当前包到临时副本（旧 entry 不重新压缩，成本为顺序 IO），副本上仅追加变化的 entry（重名以后写为准，`warnings` 压掉 Duplicate name 设计依赖告警），fsync 后 `os.replace` 原子替换。实测：改字保存追加 2 entry、包大小 385→650 字节（对照全量重建为 MB 级 IO）；任意时刻断电原包完好，不存在半写状态。
- **阈值自动整理**：死空间以解包目录现状为准计算——包内 entry 不在当前 `assets/`（业务上已替换/删除）或同名不同大小均计死空间，占比 >30% 且文件 >5MB 时全量重建原子替换。实测：8MB 图被替换后首次保存即触发（dead≈96%），整理后旧图 entry 清除、包体积 8391499→8391602 字节（新图等大），后续保存恢复纯增量。
- **另存为格式选择器**：现象——`.smd` 与 `.md` 的选择依赖手输文件名后缀，易误存。修法——保存对话框新增格式下拉（`Markdown 文档（.md）` / `自包含文档（.smd）`），文件名输入框不再携带后缀，提交时统一剥离用户误填后缀并拼接所选格式；打开对话框时按当前文档格式预选。验证：`node --check` 通过；服务端按后缀识别逻辑不变，前端规范化后两种格式落点正确。
- **安全与关联**：解包前逐条校验 ZIP entry 名，拒绝绝对路径/盘符/`..` 穿越（实测构造恶意包被拒）；`install.cmd` 注册 `.smd` 关联（`MDViewer.smd` ProgID + shim 转发，纯 ASCII 断言 PASS）；原生打开框过滤器加 `*.smd`；浏览器兜底入口（拿不到完整路径）对 `.smd` 明确提示拒绝而非读成乱码。
- **跨容器资产双向换算**：现象——普通 `.md` 另存 `.smd`、`.smd` 改名另存 `.md` 时，磁盘契约 `<文档名>.assets/` 与包内契约 `assets/` 互不对认，图片必然断链。修法——服务端新增 `_rewrite_assets_ref` 助手（左边界断言防误伤）：打包时把 `<文档名>.assets/` 引用统一改写为 `assets/` 后进包；导出时反向改写并把图片落盘到目标目录；资产源三级解析（`base/assets` → 源文档同目录 `<文档名>.assets` → 手写图收编）。验证：单测 T10/T11 + 真实服务 E2E（另存→改名导出→图片数量一致）。
- **手写图保存时收编进容器**：现象——用户手写绝对路径引用（如 `C:/user/x.png`），`.smd` 打包时原样进包，包不自包含，换机碎图。修法——`md_assets.materialize_into` 核心抽取（落盘目录与引用前缀参数化），`.smd` 打包与增量保存前统一物化：真实存在的本地图收编进容器、引用改写为容器契约；不存在的原样保留破图可见（fail-closed）；网络图维持外链不收编。验证：T12 + E2E F2/F3。
- **保存回传正文同步编辑区**：现象——服务端收编/契约改写后编辑区仍显示旧引用，所见非所存。修法——`/api/file` 与 `/api/save-as` 响应回传新正文，前端 `applySavedContent` 三处共享（Ctrl+S／自动保存／另存为）。验证：E2E F1/U1/U4。

**修复**

- **另存 `.smd` 资产断链**：现象——普通 `.md` 另存 `.smd` 后包内零图片（用户实测复现）。根因——前端 `base=null`（普通文档会话无解包目录），后端资产源断链。修法——payload 携带 `src`（源文档路径），后端按三级解析回退到源文档同目录资产。验证：E2E E1/E2。
- **`.md` 重复收编膨胀**：现象——每按一次保存 `.assets` 多一张 `_1`/`_2` 重复图。根因——编辑区不同步导致每次保存重跑物化，同名冲突走 `_unique` 加号。修法——响应回传正文同步编辑区 + 物化内容寻址复用（sha1 同字节文件直接复用文件名，编辑区未同步的重复保存幂等零膨胀）。验证：T13 + E2E F1a/F1b。
- **包内正文换行符漂移**：现象——包内 `doc.md` 与响应正文字节不一致。根因——文本模式写盘 LF→CRLF，`save_from_dir` 按原始字节进包，且 `needs_compact` 尺寸比对误判死空间。修法——`doc.md` 写盘统一 `newline=""`。验证：E2E F3b。
- **内嵌窗口桥平行实现收编（桥薄化）**：现象——`md_app.pyw` 桥自写磁盘旧逻辑（`save_as`/`paste_image` 等六方法）：`.smd` 另存被强加 `.md` 后缀、粘贴图写到 `.smd` 旁挂错误目录、新契约全部漏网。根因——桥为历史平行实现，保存规则双处维护必然分叉。修法——桥瘦身为 `pick_save_path`（只弹原生对话框选路径），六条保存入口（Ctrl+S／自动保存／另存为×2／粘贴图×2）统一走服务端三条路由；死方法删除。验证：桥方法表断言 + E2E U1-U4。

**测试**

- **`_test_smd.py` 17→28 条全 PASS**：打包-解包正文/图片字节一致、增量追加与重名覆盖语义、保存后工作目录复用、断电残片不影响原包（sha256 不变）、路径穿越防御、外部修改触发重解包、阈值整理触发/体积回落/旧资源清除、无图文档打包、双向契约换算、手写图收编与 fail-closed、重复保存幂等零膨胀；真实服务 E2E 全绿（收编/换算/粘贴图落位/字节一致）。

**说明**

- 网络图片（http/https）不进包保持 URL 原样，与普通文档物化规则一致；`.smd` 保存时物化照常执行，但贴图已在工作目录、网络图维持外链，仅手写的外部本地图被收编进包。
- 数据互通：`.smd` 改后缀 `.zip` 即可解出 `doc.md`+`assets/`，无私有二进制格式；反向按结构打包亦可打开。
- 服务端 `MD_SERVER_VERSION` 36→39，已开启的旧实例经现有版本自愈机制换代后生效。
- ZIP 格式（PKWARE 公开规范，无专利）与 Python 标准库 `zipfile`（PSF）合规声明已写入 README 与版权文档。

---

## v1.1.0

**本次改动：图片链路三类渲染修复（空格路径／下划线改写／协商缓存）、按文件路径草稿保护、启动载入策略收敛、引用与列表缩进隔离、排版 H3 与 H4~H6 拆分、保存假失败根除、死代码清理、AGPL-3.0 授权落定、分发包补齐**

**新增**

- **按文件路径隔离的草稿保护**：现象——未落盘的编辑在刷新或重开后退回磁盘版本，且旧逻辑在载入后无条件把磁盘内容回写草稿存储，未保存修改不可恢复。修法——新增按路径隔离的草稿表（`md-editor-drafts-v1`），四个载入入口（URL 打开／「打开」按钮／最近文档／内置文档）统一走草稿感知载入：草稿与磁盘内容不一致时恢复草稿，并以非阻塞 toast 提供「用磁盘版本」动作按钮；手动保存、自动落盘、另存为成功后清除对应草稿。验证：真实浏览器 E2E 十二项（草稿恢复、放弃草稿、落盘清草稿、外部修改后刷新取新内容、全程原生弹窗监听为零）全部通过。
- **排版面板 H3 与 H4~H6 拆分**：现象——「H3~H6」单行一键覆盖四级标题（`TS_MAP` 的 `h3` 键映射 h3～h6），三级标题无法独立于四至六级设置字体字号对齐。修法——`TS_KEYS` 增加 `h4`，`TS_MAP` 的 `h3` 收窄为仅 h3，新增 `h4` 键覆盖 h4～h6，面板拆为「H3 标题」「H4~H6 标题」两行。验证：面板出现 `data-ts="h4"` 控件，规则按新键生成。
- **分发包补齐运行文件**：现象——分发包缺 `md_assets.py`、`md_app.pyw`、`docs/` 内置文档（《使用指南》《版权与开源组件声明》为 `/doc` 接口运行依赖），包内保存链路报错（见修复）、内嵌窗口模式失效、默认文档加载失败。修法——三者在 v1.1.0 分发包补齐（入库文件 221 → 226）；宣传类文件（介绍文章、宣传图、宣传视频）仍不入包。验证：release zip 实下载解包，逐项核对十三项全部通过。

---

**修复**

- **文件名含下划线的图片被改写为斜体标记**：现象——粘贴图片（文件名恒为 `20261015_181923_3419.png` 三段下划线）及一切含下划线的图片、链接路径，预览不生成 `<img>`／`<a>`，或 `src` 被改写为 `20261015<em>181923</em>3419.png` 后请求 404。根因——`parseInline` 先将图片／链接替换为 HTML 标签、后执行强调替换 `_([^_]+)_`，属性值内的下划线被当作强调语法。修法——图片／链接生成的开标签先进占位符（`\x00T` 词元），行内格式化仅作用于占位符之外的纯文本，末尾统一还原；链接只占位开标签，链接文字仍参与加粗与强调。验证：真实浏览器实测两张下划线图片 `src` 干净、链接 `href` 干净、链接内文字的强调照常渲染。
- **文件名含空格的图片语法整段不渲染**：现象——`![说明](MDEditor 使用指南.assets/内嵌示例图.png)` 之类带空格路径，预览裸露原始标记。根因——内联图片／链接正则的 URL 段为 `[^) ]+`，不允许空格。修法——URL 段改为 `([^)]+?)` 非贪婪匹配（兼容可选标题语法），图片与链接两条正则同步。验证：默认文档（使用指南）图片 `naturalWidth > 0` 实测加载成功。
- **保存报 500 `cannot access local variable 'added'`，实为假失败**：现象——分发包内保存报 500，但内容实际已写盘；界面报错、草稿不清除、自动落盘静默失效。根因——`md_assets.py` 缺失时懒导入将 `materialize_images` 置 `None`，`/api/file` 与 `/api/save-as` 的 `if materialize_images:` 为假跳过赋值，响应构造引用未绑定的 `added` 抛 `UnboundLocalError`；`write` 在该异常之前执行，数据无损失。修法——两处调用点前补 `added = []` 兜底（`MD_SERVER_VERSION` 35 → 36）。验证：py_compile 通过，包内复测无 500。
- **引用块跟随正文缩进**：现象——正文设置首行缩进后，引用块内段落一并缩进。根因——缩进规则选择器 `#preview p` 命中 blockquote 内的 `<p>`（松散列表 `li>p` 同理），而引用、列表设为「无」时不生成任何规则，正文规则随之泄漏。修法——引用、列表为「无」时生成中性化规则（`text-indent:0 !important`、`padding-left:0 !important`），引用与列表的缩进设置和正文彻底隔离。验证：生成的样式表含两条中性化规则，引用段不受正文缩进影响实测。
- **图片刷新后陈旧，须强制刷新才更新**：现象——磁盘图片已替换，普通刷新（F5）仍显示旧图，仅 Ctrl+F5 可见新图。根因——`/img` 响应 `Cache-Control: max-age=3600` 且 URL 稳定，浏览器将图片缓存一小时；文字内容走 `/api/file`（no-store）故仅图片陈旧。修法——改为协商缓存：响应携带 `ETag`（mtime-size）与 `Cache-Control: no-cache`，`If-None-Match` 命中返回 304 不重传，文件变更即 200 返回新图（服务端 v35）。验证：真实浏览器 F5 后六张配图全部带 `If-None-Match` 回源，未变更时 304。

---

**变更**

- **启动一律载入默认文档，旧全局缓存退役**：现象——启动显示陈旧的指南快照，图片位置与当前版本不符且全部 404。根因——初始化保留「全局缓存键 `md-editor-content-v1` 优先」的历史路径，陈旧快照遮蔽默认文档；该状态下无文件上下文，相对路径图片丢失基址（`/img` 按工具根目录兜底解析必然 404）。修法——启动一律走默认文档的草稿感知载入，旧键一次性清除；`scheduleSave` 的无文件分支同步退役，草稿存储收敛为按文件路径的单一来源。验证：种入旧值启动后显示真指南、旧键清除、图片加载成功；无旧值常规启动回归通过。
- **死代码清理**：`md_server.py` 的 `do_POST` 内 `/api/save-as`、`/api/paste-image` 路由各重复三次，后两次不可达，删除 112 行；`markdown-editor.html` 中 `katexCssText` 的重复 fetch 两处删除；`md_launch.pyw` 的 `if False else` 残留与孤立 `import io` 移除。验证：py_compile 通过，`grep` 路由计数归一。
- **授权落定为 GNU AGPL-3.0-or-later**：新增 `LICENSE`（GNU 官方全文）与全部源码 SPDX 头（Copyright 2026 wUwproject），《版权与开源组件声明》与 README 许可节同步改写；与随附第三方组件（KaTeX、Paged.js MIT，Python PSF）兼容，`LICENSES/` 目录保留。分发仓库同步设为公开。

## v1.0.6

**本次改动：生命周期自动化（关页面即停服务、闲置永不误停）；删除 WebView2 内核与全部内嵌遗留，项目 1.2GB → 58MB**

**新增**

- **页面关闭驱动的服务退出**：现象——浏览器关闭后服务常驻，须手动双击 `md_stop.cmd`。修法——前端在 `pagehide` 事件经 `navigator.sendBeacon('/api/bye')` 上报；服务端登记 `_BYE_AT`，由守护线程在 8 秒宽限期后确认（`MD_EXIT_GRACE` 可覆盖），期间任何新心跳（页面刷新即发）清零撤销。`runtime/settings.json` 的 `auto_stop:false` 可整体关闭。验证：闲置 12 秒服务存活、发送关闭通知后停止、关闭后 1.5 秒恢复心跳撤销成功三场景全绿，`runtime/lifecycle.log` 记录 `page closed -> stop service`。
- **撤销机制防刷新误杀**：刷新页面会先触发 `pagehide` 再加载新页面心跳，宽限期内恢复心跳即撤销退出，刷新不误停。

**变更**

- **废弃"空闲超时"判据**：此前一版按"连续 120 秒无心跳即退出"实现，切标签页、最小化、长时间编辑中途离开均属"闲置但未关闭"，会被误停。改为仅以页面卸载通知为判据，闲置永不退出；该设计缺陷在实机验证中确认后纠正。
- **删除 WebView2 内核与内嵌遗留**：删除 `runtime/WebView2/`（734.6MB）、`runtime/WebView2.zip`（346.8MB）、`runtime/userdata/` 及两份备份（共 68.1MB），释放 1149.5MB；随删 `runtime/unpack_runtime.py`、`md_clear_cache.cmd`、老式目录框脚本 `_pickdir.py`（删除前确认服务端 0 引用）。`docs/版权与开源组件声明.md` 同步删去 WebView2 Runtime / pywebview / pythonnet 三行及对应许可要点；`install.cmd` 去掉首次安装解压内核步骤，复核仍为纯 ASCII。
- **有意保留项**：`md_app.pyw`、`md_launch.pyw` 的内嵌判定分支与 pywebview/pythonnet 包保留——内核不存在时 `embedded_available()` 自然返回 False 自动走浏览器模式，留退路且不占空间。验证：清理后服务页面 200、内置文档 2 篇、常用目录 4 项、ping 正常。

---

## v1.0.5

**本次改动："打开"改后端原生文件框、"浏览"改 IFileOpenDialog 现代目录框，去掉老式回退与死代码，常用目录读注册表解析 OneDrive 重定向**

**新增**

- **`GET /api/open-file` 原生打开文件框**：现象——浏览器模式"打开"按钮走 `<input type="file">`，安全沙箱只给文件名不给路径，`change` 回调里 `addRecent(null, f.name)` 路径恒空，"保存"不可写回、`.assets` 无基址。修法——新增 `_pickfile.py`（纯 ctypes 调 `comdlg32.GetOpenFileNameW`，`hwndOwner=GetForegroundWindow()` 跟随浏览器窗口置前），服务端子进程+临时文件回传返回 `{ok,path}`；前端 `openFileNative()` 优先走该接口取完整路径后经 `/api/file` 载入并设 `currentFile`，接口失败自动退回 `<input type=file>`。验证：打开后保存立即可用、图片物化正常落入 `.assets`。
- **`_pickdir_modern.py` 现代目录选择框**：原"浏览…"为 XP 风格 `SHBrowseForFolder` 树状框。改为纯 ctypes 手写 COM vtable 调 `CLSID_FileOpenDialog`/`IID_IFileOpenDialog`，`FOS_PICKFOLDERS|FOS_FORCEFILESYSTEM|FOS_PATHMUSTEXIST`，`Show(GetForegroundWindow())` 置前。验证：`CoCreateInstance`/`GetOptions`/`SetOptions` 全部 `hr=0`（current=0x1808）。

**修复**

- **取消后弹第二个老式框**：现象——现代框点"取消"后又弹出老式树状框。根因——"三态返回+不可用回退"设计中，取消信号未成功写回即触发回退。修法——去掉回退逻辑，`_pick_dir_subprocess()` 只调现代框，取消与不可用均返回空串并写 `runtime/pickdir.log` 诊断。
- **`/api/browse-dir` 四份重复定义**：仅 1 份可用（走 modern），另 3 份分别调用已不存在的 `_pick_dir_win()` 与嵌入式 Python 根本没有的 tkinter，全部删除。
- **常用目录指向 C 盘空壳**：现象——"另存为"快捷按钮的桌面/文档指向无效路径。根因——`expanduser("~")` 拼接，真实桌面在 OneDrive 重定向路径。修法——`/api/common-dirs` 改读注册表 `HKCU\...\User Shell Folders`（Desktop/Personal/Downloads GUID）并展开环境变量。实测：`desktop=D:\...\OneDrive\Desktop`、`docs=D:\...\OneDrive\文档`、`downloads=D:\Users\...\Downloads`。

---

## v1.0.4

**本次改动：引入内嵌窗口模式（pywebview+WebView2）并经卡死排查后按决策放弃，还原浏览器模式、移除系统托盘；页面 23 处原生 alert 全部替换为 toast；新增启动旧窗口清理与卡死看门狗**

**新增**

- **`md_app.pyw` 内嵌窗口入口**：pywebview 6.2.1 + pythonnet 开原生窗口指向本地服务，自带 WebView2 内核优先（`WEBVIEW2_BROWSER_EXECUTABLE_FOLDER`）、系统 Runtime 兜底；暴露 py API（pick_folder/save_file/paste_image 等），窗口尺寸记忆 `runtime/window.json`。前端双模式：`pywebviewready` 置 `HAS_PY`，浏览目录/另存/贴图"有桥走 py 直连、无桥走 HTTP"。`install.cmd` 首次安装自动解压内核（实测 347MB→737MB 仅 3.9 秒）。端到端实测：内嵌窗口出现、自带内核加载、页面回调桥 OK。许可核验：pywebview BSD-3、WebView2 Runtime 微软免费可分发（原样+声明两条件）、Chrome EULA 禁再分发故不采用。
- **卡死自动取证看门狗**：`md_app.pyw` 加 `_install_hang_watchdog()`——后台线程每 2 秒心跳，实际延迟 >1.5s 即把 `sys._current_frames()` 全线程调用栈写入 `runtime/hang.log`（仅异常时写）。实测心跳日志正常、未卡时为空。项目首次具备"用户现场卡死事后定位到代码行"的能力。
- **`kill_stale_apps()` 启动清理**：现象——启动器每次新开窗口却从不关旧 `md_app` 窗口，桌面叠多个旧版本窗口。修法——按命令行含 `md_app.pyw` 精确匹配后 taskkill（不误伤其它 pythonw 脚本），main 入口最先调用；`kill_stale_services()` 收紧为只杀命令行含 `md_server.py` 的进程；新增 `kill_port_holder()` 按端口兜底。效果：每次打开必然是最新代码。
- **`GET /api/open-external` 外部浏览器打开**：分页/打印原用 `window.open`/`window.print()`，在 WebView2 嵌入窗口内会阻塞界面。统一改为服务端 `threading.Thread(webbrowser.open)` 交系统默认浏览器（白名单仅 `/` 相对路径与 `http://127.0.0.1:PORT/`），打印语义=生成分页 HTML 后浏览器 Ctrl+P。
- **`GET /api/log` 与 `uiBeacon()` 探针**：分页/打印/导出按钮点击上报 `runtime/ui.log`；分页流程埋分步打点 + `AbortController` 45 秒超时 + 防重入。

**修复**

- **页面卡死真根因为原生 `alert()` 同步阻塞**：现象——分页按钮点击后窗口"未响应"，服务端导出正常完成（540KB、mtime 与点击时刻吻合），`SendMessageTimeoutW(WM_NULL)` 探测窗口确认为真未响应。根因——页面 23 处原生 `alert()` 同步阻塞 JS 主线程，且此前测试用例 `j.ok` 恒为 true、从不触发失败分支。修法——全部替换为自绘 `showToast()`（右上角浮层、失败类标红、3~6 秒自动消失），`alert(` 存量归零。
- **"改了没生效"的系统化对策**：多轮修改未达用户侧，后以"清空 `ui.log` 后观察新埋点"实证用户窗口运行的是旧版页面。配套：`Cache-Control: no-store`（页面本身无缓存，根因是旧窗口未关）+ `kill_stale_apps()` + `userdata/` 重命名移除并干净重建（实测 53.8MB 运行数据）。
- **"滚动卡死"与 GPU 精简内核排除**：补回误删的 `dxcompiler.dll`（20.5MB）与 `onnxruntime.dll`（11.1MB）；内核完整性核查仅缺 3 个 `.sig` 与 Installer 目录；`settings.json` 新增 `disable_gpu` 软件渲染逃生开关。自动化压测（复用 md_app Api 注入 js_api 桥 + 逐按钮 click + 注入 onerror 捕获）：全部按钮 click 1~8ms、JS 错误为空。

**变更**

- **放弃内嵌窗口，还原浏览器模式**：卡点定位在 pywebview WinForms 宿主层——Python 心跳无阻塞记录、页面探针未收到任何输入事件、Windows 事件日志无崩溃、内核完整、软件渲染无效、合成输入（含真实滚轮/按键消息）无法复现。按决策 `settings.json` 设 `embed_window: false`，内嵌代码全部保留仅由开关控制。实测：进程只剩 `md_server` 一个，浏览器自动打开，服务 v27。
- **移除系统托盘**：托盘（`md_server.py` 内纯 ctypes `Shell_NotifyIconW`，窗口类 `MDViewerTrayWnd`）的最小化/新建/退出菜单动作实测不可靠，移除 `build_tray()` 调用改纯常驻；托盘类保留不删。验证：重启后 `FindWindowW('MDViewerTrayWnd')` 返回 0，退出方式为 `md_stop.cmd`（按命令行匹配 `md_server.py`，纯 ASCII）。

---

## v1.0.3

**本次改动：图片物化随文档落盘（base64/blob 引用/本机路径统一进 `<文档名>.assets/`）、内置文档实体化、保存按钮门禁、保存默认名取一级标题、`.assets` 改为有图才建**

**新增**

- **`md_assets.py` 图片物化**：`materialize_images(doc_path, content)` 把 Markdown 内 base64 data URI、WorkBuddy blob 引用、本机绝对路径/file:/// 三类图片统一写入 `<文档名>.assets/`（文件名取 alt 文本、非法字符清洗、重名加序号），引用改写为相对路径；http(s)/锚点/已是相对路径保持不动，任何异常原样返回不破坏文档。挂载于 `/api/save-as`、`/api/file` 写盘前与 `md_app` 保存桥。实测：`assets: ['图A.png','图B.png']`、引用改写 `![图A](终测.assets/图A.png)`。
- **内置文档实体化**：内置指南与版权声明由 JS 内存常量改为工具目录实体文件 `docs/*.md`（版权文档用 `materialize_images` 生成，同步验证物化链），新增 `GET /docs-list` 与 `GET /doc?file=`；打开内置文档即设 `currentFile` 为其实体路径，点保存直接落盘。实测：`/doc` 返回真实路径、保存回写原路径、预览取图 200。
- **`GET /api/paste-image` 剪贴板贴图**：剪贴板图存入 `<文档名>.assets/<时间戳>.png` 并返回与存放位置一致的相对路径引用（v1.0.1 首版实现，本版统一引用风格去掉多余 `./` 前缀）。

**修复**

- **`save-as` 路由 500 `name '_LAST_DOC_DIR' is not defined`**：根因——批量补丁脚本中一个替换断言失败导致整个脚本未落盘，前序改动亦未生效，后续补丁引用了从未定义的变量。对策确立：脚本式改动分步提交、每步独立写盘并核验。
- **嵌入式 Python 导入同目录模块失败**：embedded 发行版 `sys.path` 不含脚本目录，`from md_assets import ...` 抛 `ModuleNotFoundError` 被 `try/except` 静默吞掉，表现为"代码改了没生效"。修法——import 本地模块前显式 `sys.path.insert(0, HERE)`，并在 `md_server` 加 `runtime/md_assets.err` 错误落盘，杜绝静默失败。

**变更**

- **保存按钮门禁**：无路径时「保存」禁用（`sb.disabled=!currentFile` + opacity .45 + 状态栏"未另存为"），弹窗只属于「另存为」；物化只在落盘时发生，未保存文档贴图被拦并提示先保存。
- **保存默认文件名取文档第一个一级标题**：`docTitleForSave()` 正则取 `# xxx`、剔除非法字符、限 60 字、无标题退回"未命名.md"。
- **`.assets` 改为按需创建**：删除 `/api/file`、`/api/save-as` 及 `md_app` 共 6 处无条件建目录调用与 `_ensure_assets_dir`，目录仅由物化逻辑与贴图接口在真有图片时创建。实测四场景：无图保存仅 `['无图.md']`、有图保存成对出现、已存文档贴图补建目录、无图内置文档无 `.assets`。

---

## v1.0.2

**本次改动：目录/文件对话框全链路 ctypes 化（嵌入式 Python 无 tkinter 的根治）、Win32 启动画面、"每次打开都重启服务"的版本单一来源根治（热启动 2s+ → 0.15s）、托盘图标与双开修复**

**新增**

- **纯 ctypes 目录/文件对话框**：现象——"浏览"目录弹窗在服务线程与子进程两版 tkinter 实现下均弹不出。根因——便携嵌入式 Python 根本不含 tkinter（`import tkinter` 即 `No module named`），与线程无关。修法——`_pickdir.py` 纯 ctypes 调 `shell32.SHBrowseForFolderW`（`restype=c_void_p` 防 64 位指针截断、子进程 `CoInitializeEx(STA)`、路径经临时文件回传）。另修保存弹窗按钮样式（独立 `.sv-btn`，原蹭工具栏样式字大框小）。
- **Win32 启动画面 `_splash.py`**：纯 ctypes/GDI 绘制（图标 `LoadImageW`+`DrawIconEx`、圆角 `SetWindowRgn`、淡入淡出 `SetLayeredWindowAttributes`），splash 自起线程轮询 `/api/version`，版本就绪后 0.45 秒触发淡出，启动器 `WM_CLOSE` 兜底。关键实现约束：全部句柄/指针参数显式 `argtypes`，否则 64 位句柄按 int 截断（定时器失效、文字画不出）。
- **托盘图标加载与窗口管理**：托盘图标改 `LoadImageW` 从 `md-editor.ico` 加载 16×16（失败降级默认）；左键单击 toggle 编辑器窗口（`EnumWindows` 匹配标题，最小化恢复/前台最小化/后台前置），右键菜单（新建/退出），退出先对所有编辑器窗口 `PostMessageW(WM_CLOSE)` 再删图标停服务。

**修复**

- **每次打开都杀服务重启（重大）**：现象——热启动也要 2 秒+，且页面常是旧版。根因——`md_launch.pyw` 的 `VERSION` 常量自初始值 2 起从未同步，而 `md_server` 已演进至 11，`server_version()==VERSION` 永假触发自愈重启。修法——`md_launch` 直接 `from md_server import MD_SERVER_VERSION as VERSION`，版本单一来源。实测：冷启动 2.11 秒（含启动画面全程）、热启动 0.15 秒。
- **启动一次开两个编辑器**：根因——`/open` 路由"先开浏览器再回响应"，浏览器冷启动超过启动器 5 秒超时，兜底逻辑又开一次。修法——`/open` 先回响应再 `threading.Timer(0.25)` 异步开浏览器（实测响应 0.010s），兜底收紧为仅 `URLError`，超时 5→8 秒。实测：冷启动 1.83 秒、热启动 0.17 秒。

**变更**

- **启动器轮询参数**：按使用反馈恢复 0.25 秒轮询与 0.6 秒等待（此前为提速改 0.1s，感知差异由浏览器冷启动主导，服务冷启动实测仅 0.51 秒）。

---

## v1.0.1

**本次改动：文档工程三件套（新建/另存为/粘贴图片），保存弹框从嵌套容器迁移至 body 级并修复禁用出口，目录浏览从 tkinter 迁至子进程方案**

**新增**

- **「新建」与另存为链路**：工具栏「新建」+Ctrl+N（内存文档）；保存模态框（文件名+目录+浏览）；`POST /api/save-as` 落盘；自动保存分流（有路径直写原文件，内存文档到点弹一次保存框）。`MD_SERVER_VERSION` 2→3。
- **`POST /api/paste-image`**：剪贴板图片落盘 `<文档名>.assets/` 并返回相对路径引用（实测 2993B 落盘）。
- **独立「另存为」按钮**：总是弹框、回填当前文件名与上次目录。
- **`GET /api/browse-dir` 目录浏览**：首版经 tkinter `askdirectory`（服务线程内，后于 v1.0.2 根治为 ctypes 方案）。

**修复**

- **保存弹框常显且 hidden 失效**：根因——`#svOverlay` 的 inline `display:flex` 特异性压过 `[hidden]` 属性的 UA 样式。修法——`#svOverlay[hidden]{display:none !important;}`。
- **点保存无反应、点排版时保存框跟着冒出**：根因——svOverlay 整块被插进排版面板内部，成为 tsOverlay 子元素，祖先隐藏时整个子树不渲染。修法——迁移至 body 级与 ts/fm 面板平级。验证：点保存 `getBoundingClientRect` 1280×720 真实遮罩、排版面板 hidden 状态不再联动、填名保存文件落盘。
- **保存按钮被两个加载出口禁用**：内置文档与冷启动默认文档两处均 `disabled=true`，内存文档无法另存为。修法——两处改启用，"另存为"语义与「保存」解耦。
- **路由锚点错插 `do_POST`**：GET 路由被插进 POST 分支致 404（`/api/browse-dir`），移回 `do_GET`。铁律沉淀：`md_server` 加 GET 路由锚 `/api/version` 后，POST 路由锚 `/api/export-html`，混用必 404。

---

## v1.0.0

**本次改动：首个正式版——目录清理、独立桌面快捷方式、双平台建仓（Gitee/GitHub）与 git-sync 注册**

**变更**

- **目录清理**：删除调试产物（`.playwright-cli/`、`_patch17*`、`_s0.js`、`.mdinstall.bak`、两个误建空目录、`icon-preview.png`）；`document.paged.html` 保留作导出样例。
- **`desktop-shortcut.cmd`**：独立桌面快捷方式脚本（目标 `MarkdownEditor.exe` + 图标），不装右键关联也能像传统应用双击使用；`_mklnk.ps1` 同步重写（快捷方式目标从 pythonw+pyw 改为 exe+图标）。
- **双平台建仓与发布注册**：Gitee `wUwproject/maby_tool` + GitHub `Ldxs001/maby_tool` 双 remote（gitee https / origin ssh 443）；仓库根 `MarkdownEditor/` 子目录 217 文件与源一致，`git status` 干净；git-sync `config.json` + `manifest` 注册（source_path/repo_path/version 1.0.0），双端 push 通过。exe 重编译单独 commit。

---

## v0.10.0

**本次改动：服务版本自愈与打开方式治理（file:// 自检指引）、最近文件管理、图片体系（/img 代理+相对路径+静态兜底）、分页页数稳定判定**

**新增**

- **后端版本自愈**：现象——旧 pythonw 后端常驻导致公式占位符裸露、图片碎图标（`md_launch` 见端口占用即复用旧服务）。修法——`md_server` 加 `MD_SERVER_VERSION` 与 `/api/version` 路由、`/` 页面 `Cache-Control: no-store`；`md_launch` 端口占用时校验版本：匹配复用、不符则 `taskkill /FI "PID ne <self>"` 清旧+自起+轮询 `/api/version` 确认（15 秒），失败兜底开页面。实测：假旧服务（无 version 路由）→ 自愈到新版、katex/img/editor 全 200、pythonw 收敛 1 个。
- **file:// 双击直开自检**：主 IIFE 首行检测 `location.protocol==='file:'` → fetch `/api/version` 探测服务，在线自动跳转 `http://127.0.0.1:18765/`，离线渲染指引页并阻断编辑器初始化。
- **最近文件管理**：工具栏「文件」面板——内置文档区 + MRU 列表（最多 12 条，文件名+完整路径+时间，当前文件高亮），右键/关联打开自动记路径可重载切换；状态栏当前文件指示 + `document.title` 同步。
- **图片体系**：新增 `GET /img?path=` 代理（扩展名白名单 jpg/jpeg/png/webp/gif/svg/bmp），前端 `fixLocalImages()` 把本机绝对路径/file:/// 与无协议相对路径（base=当前文档目录）统一转代理；服务端加根级静态兜底（未匹配 GET 路由→白名单扩展名→工具目录下文件，防穿越）；导出时图片路径还原为 file:/// 绝对路径。实测：网络图与本地图双图 `naturalWidth` 加载成功。
- **分页页数稳定判定**：现象——页码"第 1 页/共 2 页"与实际页数不一致。根因——MutationObserver 在分页逐步进行时就填充且 dataset 防重不更新。修法——连续 4 次 250ms 页数稳定才 disconnect 并一次性填全。实测：多页页码逐页一致。

**修复**

- **tsFill 三重 bug**：①`fillSel(s,vals,labels)` 参数传反致字体下拉显示 CSS 串而非友好名；②对齐选项误填进字体下拉而 `data-algn` 下拉从未填充；③无重复填充防护。重写后实测：字体首项"(默认)"、对齐 5 项、无泄漏。
- **双「应用」按钮**：PAGE_HTML 自带 `ts-foot` 与插入的 `ts-foot` 叠加，去重。
- **base64 示例图替换网络商标图**：网络示例图改 PIL 生成 240×150 base64 内嵌图（1732 字符 data URI，离线零图源依赖）；同时修 `fixLocalImages` 把 `data:` URI 误当相对路径转代理致 404。

---

## v0.9.0

**本次改动：长文分块增量渲染（6 万字全量渲染 25.5 秒冻结主线程 → 编辑单字只重渲所在块 4.5 秒）、公式排版行、/api/fonts 注册表字体枚举（775 个）、公式块级对齐真因修复、文档合规收尾**

**新增**

- **分块增量渲染**：`splitBlocks`（fence 感知 H1/H2 切块）+ 块 hash（djb2）比对 + `.pblk` 容器逐块异步渲染（setTimeout 分片）+ 防抖自适应（>3 万字 600ms）。实测：6 万字（80 公式/40 表格）首渲 15.2 秒分片不冻结、编辑单字只重渲所在块 4.5 秒（5.7 倍）；十万字可正确渲染、输入流畅。
- **排版面板「公式」行**：字号→`.katex{font-size}`（实测 20pt→26.67px 生效）、对齐→`.katex-display`（仅块级，行内公式跟随所在段落）；KaTeX 字体固定不给字体选项。
- **`GET /api/fonts`**：py 侧 winreg 枚举注册表字体（HKLM+HKCU，去 `(TrueType)` 后缀、`&` 拆分家族）775 个，面板打开自动填充「本机字体」组，取代需授权弹窗的 `queryLocalFonts`（该按钮后续删除）。

**修复**

- **公式对齐不生效**：根因——`katex.min.css` 自带 `.katex-display>.katex{display:block;text-align:center}`，内层强制居中盖掉外层容器设置。修法——math 对齐规则补内层选择器 `#preview .katex-display>.katex`。实测：outer/inner computed 均 right、公式右缘与容器右缘重合。
- **面板左侧边距不齐**：页面/页码/目录三区（v0.6.0 加入）被锚在 `.ts-body` 容器外的 `ts-foot` 前，未吃到内边距（左右缘 375px vs 391px）。修法——三区移回 `.ts-body` 闭合前，复测 6 个分隔线全部对齐。

**变更**

- **合规盘点**：KaTeX(MIT)/Paged.js(MIT)/Python(PSF)/KaTeX 字体(SIL OFL 1.1) 均允许随软件捆绑分发，条件为保留许可文本，`LICENSES/` 四文件齐备；示例图 base64 内嵌无第三方素材；默认字体为系统字体非分发物。
- **`README.md`**：中文全量说明（首次安装、正确打开方式、文件清单三分类、功能速览、卸载、许可）。

---

## v0.8.0

**本次改动：分页与 HTML 导出组装从 JS 全部移至 Python（`/api/export-paged`、`/api/export-html`），前端只 POST，根除 JS 字符串拼接类错误**

**变更**

- **`build_paged_html()` 全权组装**：TOC 构建（h1-h3 加 id、插入位置 top/afterh1、独占页）、`@page` CSS（纸张/边距/页码 margin box 占位）、KaTeX CSS 内嵌（字体路径转 `/static/katex/fonts/`）、Paged.js polyfill 内嵌、页码填充脚本。前端删除 `buildPagedHtml`/`PAGED_JS`/`katexCssText` 预取（瘦身约 10KB）。实测：531KB、3 页、页码一致、14pt→18.67px 生效、TOC 2 条。
- **`build_standalone_html()`**：`.html` 导出组装移 py（图片路径还原/katex css/tsCss 全 py 侧），前端只剩 POST。实现约束：含字面 `%` 的模板禁用 `%` 格式化（CSS `100%` 触发 `unsupported format character`），改用 `__TOKEN__` replace。
- **切换载入改同步 `render()`**：`loadBuiltin`/`loadDefault`/`loadFile` 同步渲染，消除 120ms 防抖窗口的"点了没反应"体感。

**修复**

- **内置文档载入变字符串 "undefined"**：根因——`BUILTIN_DOCS` 定义在 `var SAMPLE=` 之前，var 提升致初始化时为 undefined。修法——移到 SAMPLE 赋值后。

---

## v0.7.0

**本次改动：Paged.js 分页导出全链路（纸张/页边距/页码/目录），六级连环问题实测定位修复**

**新增**

- **分页导出**：面板新增页面（A0~B3/Letter/自定义 mm+四向边距）、页码（开关/位置 5 档/模板/字号）、目录（开关/文首或第一个一级标题下/独占页）三区；「分页」按钮 → `buildPagedHtml()` → `POST /api/export`（文件名白名单 `^[A-Za-z0-9._-]+\.html$`）→ `window.open` 打开成品。
- **页码与目录实现**：margin box 占位 + 导出 HTML 内嵌 MutationObserver 分页后直填 DOM（Paged.js 0.4.3 下 margin box content 渲染损坏的降级方案）；目录条目 `target-counter` 页码引用。终态实测：3 页、页码逐页一致、TOC 4 条带页码、公式与缩进全对。

**修复**

- 分页导出六级问题逐一定位修复：①blob: URL 非层级地址致 Paged.js 目录锚抛 `Failed to construct 'URL'` → 写盘走 http；②`@bottom-center` margin box 必须嵌在 `@page{}` 内；③margin box content 渲染损坏 → 占位+JS 直填（见上）；④KaTeX MathML `<math>` 被 Paged.js 解析器剥离 → `output:'html'`；⑤占位符 NUL 字符被 innerHTML 解析丢弃 → 换 PUA 字符 U+E000/U+E001；⑥`restoreMath` 在 276KB katex.js 未下载完时竞态放弃 → 轮询等待后整体重渲染。

---

## v0.6.0

**本次改动：排版面板 v2~v4——按元素字体+字号+对齐+缩进（正文/引用/列表三行独立）、本机字体接入，tsCfg 键升 v2/v3 自动迁移**

**新增**

- **面板 v2**：每元素字体+字号(pt) 双控件；段落缩进三态（无/首行缩进/悬挂）+ 字符数（em=字号×字符数）；表头/首列独立 checkbox+取色器；存储键 `md-editor-typeset-v2`。
- **面板 v3 按元素缩进**：缩进区拆为正文/引用块/列表三行各自 mode+chars；引用缩进作用于 `blockquote p`（border-left 不动），li 悬挂时 marker 不动文字右移；v2 全局 indent 自动迁移至 p。
- **面板 v4 对齐**：每元素行加对齐下拉（默认/左/居中/右/两端），`applyTypeset` 生成 `text-align` 规则。
- **本机字体**：`window.queryLocalFonts()`（Local Font Access API，127.0.0.1 属安全上下文）按 family 去重排序进全部字体下拉，localStorage 缓存免重扫，API 不可用/拒绝时静默回退内置列表。

---

## v0.5.0

**本次改动：编辑器五项功能升级——自动落盘、KaTeX 公式本地化、排版面板（模态框）、三线表与悬挂缩进、导出 HTML 公式离线可见**

**新增**

- **自动落盘**：缓存层文案改「已存入缓存」；自动落盘设置 0~60 分钟（0=仅手动），到点且 dirty 且有当前文件时 POST 写回原文件，状态栏显示落盘时间。
- **KaTeX 0.16.21 本地部署**：dist 含 fonts/contrib 共 6MB（MIT 可随仓库分发）；服务端 `/static/` 路由（normpath 防穿越）；渲染管线内核零改动——`extractMath` 按 ``` 围栏分段提取行内/块级公式存占位符，`restoreMath` 用 TreeWalker 恢复并 `katex.render`。
- **排版面板 v1**：模态框面板，正文/H1/H2/H3~H6/引用/列表/表格/代码各一字体下拉（宋黑雅楷仿等线 Arial Georgia Times Courier），生成 `#ts-style` 动态 CSS（预览+导出共用）。
- **三线表开关与悬挂缩进开关**：三线表（去竖线三条横线）+ 表头/首列底色高亮；悬挂缩进 `p{padding-left:2em;text-indent:-2em}`。
- **导出 HTML 公式离线**：改用 preview 渲染后 DOM，内嵌 `katex.min.css` 全文 + ts-style 动态样式，字体断链时 MathML 布局退化可用。实测：面板隐显、公式渲染、本地图片代理、静态资源全 200、穿越 403。

**修复**

- **排版面板"关不掉"**：根因——`#tsOverlay{display:flex}` 特异性压过 hidden 属性的 UA `display:none`。修法——`#tsOverlay[hidden]{display:none !important;}`。

---

## v0.4.0

**本次改动：csc shim 可执行文件根治"打开方式显示 Python"，纯程序化生成多尺寸图标并接入关联三处与 exe 内嵌**

**新增**

- **`MarkdownEditor.cs` → `MarkdownEditor.exe` shim**：现象——`.md` 右键/打开方式列表显示 "Python"（Win11 选择器对无 FriendlyTypeName 的 ProgID 显示 command 里 exe 的 FileDescription；command 直连 pythonw.exe 则 FriendlyTypeName 也治不了，ASSOCSTR_FRIENDLYAPPNAME 解析链实证）。修法——install.cmd 自动用系统自带 csc（Framework64 v4.0.30319）编译 shim（AssemblyDescription="Markdown Editor"），功能为转发 .md 路径给便携 pythonw；右键 verb/双击关联/兜底 ProgID 三处 command 全部改指 shim，并注册 `Applications\MarkdownEditor.exe`。用户实测选择器显示 "Markdown Editor"。
- **程序化图标 `gen_icon.py`**：PIL 纯程序化生成 `md-editor.ico`（256~16 七尺寸）——点阵拼 "MD"、青→紫→粉色相渐变圆角色块、深色圆角底，零字体零素材。接入三处 `DefaultIcon` + csc `/win32icon` 内嵌。

---

## v0.3.0

**本次改动：安装链路治理——Win11 右键菜单、cmd 纯 ASCII 铁律、UserChoice Deny ACE 突破、孤儿 ProgID 修补、OpenWithList 清理**

**修复**

- **右键菜单"没出现"（两层）**：①Win11 新右键菜单隐藏传统 shell 项——install.cmd 默认启用旧版菜单（`HKCU\...\CLSID\{86ca1aa0-...}\InprocServer32` 空值），传 `nolegacy` 才不启用；②command 值引号嵌套被 reg 剥引号致命令损坏——改为 `%PYW% %HERE%\md_launch.pyw "%%1"`（路径无空格仅 %1 加引号）。
- **cmd 脚本编码事故（终极方案纯 ASCII）**：UTF-8 无 BOM 的 .cmd 按 GBK 逐字节读取，中文尾字节与语法字符配对成乱码致引号/括号失配、脚本崩溃——先试 GBK 转码仍乱码（与磁盘真实状态脱节），终态三个 .cmd 全部重写纯 ASCII（英文提示），字节级验证 max byte ≤ 126，任何代码页下字节相同。铁律：交付双击运行的 .cmd/.bat 一律纯 ASCII，中文提示需求改由 Python/PowerShell 实现。
- **UserChoice 删除被 ACL 拦截（多层定位）**：`FileExts\.md\UserChoice` 有显式 `SetValue|Deny` ACE（Windows 防关联劫持），reg.exe 静默失败；`RegDeleteKeyW` P/Invoke 亦失败。修法——改 .NET `Registry.CurrentUser.DeleteSubKey`（权限检查在父键）成功；并以双保险在 `HKCU\Classes` 补建孤儿 ProgID "Markdown Document" 实体（该键原指向不存在的 ProgID）。终态：UserChoice cleared、双击归位。
- **「打开方式」列表残留 pythonw**：OpenWithList 历史 pythonw 条目删除+MRUList 重写，Classes 与 FileExts 两层 `OpenWithProgids` 注册 `MDViewer.md`。实测重跑后列表与图标归位。

---

## v0.2.0

**本次改动：打包嵌入式 Python 摆脱系统依赖，托盘由 pystray 重写为纯 ctypes 零第三方**

**变更**

- **便携 Python**：`python-3.11.9-embed-amd64` 解压至工具 `python/`（34 项约 11MB），`install.cmd` 启动项改指 `%~dp0python\pythonw.exe`，目标机无需安装 Python。`md_launch.pyw` 本就以 `sys.executable`+脚本目录定位，无需改动。
- **托盘零第三方**：pystray 重写为纯 ctypes `Shell_NotifyIcon`，失败自动降级常驻不崩。兼容修补：该 embed 分发 `ctypes.wintypes` 缺 `LRESULT`/`UINT_PTR` 显式定义（Win64 宽度）；`LoadIconW` 资源 ID 须 cast `c_wchar_p`（MAKEINTRESOURCE 约定）。

**验证**

- `python/python.exe` 下 py_compile 通过；HTTP GET `/`、`/api/file` 读写/404 全 PASS；`md_launch.pyw` 端到端拉起后端 PASS；托盘初始化无报错。

---

## v0.1.0

**本次改动：项目起点——零依赖单文件 Markdown 编辑器 + 本地服务化 + .md 关联安装器**

**新增**

- **`markdown-editor.html`**：单文件编辑器，解析内核为纯手写正则（`parseInline`/`parseList`/`parseTable`/`parseMarkdown`），不引 marked.js/markdown-it。
- **`md_server.py`**：标准库 http.server 后端，`/api/file` 路由读写本地文件（绕开 `file://` 禁止 JS 读盘的限制），前端加 `?file=` 注入适配层（解析内核零改动，仅 UI 段新增保存按钮）；可选 pystray 托盘（缺失降级常驻）。
- **安装器**：`install.cmd`/`uninstall.cmd`（HKCU 注册 .md 右键菜单+默认关联+快捷方式，无需管理员可逆）、`md_launch.pyw`（Explorer 传路径，启动/复用后端开浏览器）、`md_stop.cmd`、`_mklnk.ps1`。

**验证**

- py_compile 通过；HTTP 路由/读/写/404 冒烟全 PASS；后端启动+端口探测链路验证通过。已知限制如实记录：Win11 新版右键菜单第三方项可能仅在"显示更多选项"（legacy 开关应对）；install.cmd 会改 .md 双击关联（卸载还原）。

---
