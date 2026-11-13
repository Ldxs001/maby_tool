"""DEV → PUB 同步：按 PUB 的 git 索引逐个比对，只拷内容不同的文件。

只碰 PUB 索引里有的路径（PUB 独有的历史文档不动）；反向缺文件只报告不删。
用法：python _sync_to_pub.py
"""
import hashlib
import os
import shutil
import subprocess
import sys

DEV = r"C:\Users\sm001\WorkBuddy\MarkdownEditor-app"
PUB = r"C:\Users\sm001\WorkBuddy\maby_tool"
SUB = "MarkdownEditor-app"


def h(p):
    m = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            m.update(b)
    return m.hexdigest()


out = subprocess.run(["git", "-C", PUB, "-c", "core.quotepath=false", "ls-files", SUB],
                     capture_output=True, text=True, encoding="utf-8")
files = [x for x in out.stdout.splitlines() if x.strip()]
print("tracked", len(files))

copied, same, missing, failed = [], [], [], []
for rel in files:
    src = os.path.join(DEV, rel[len(SUB) + 1:].replace("/", os.sep))
    dst = os.path.join(PUB, rel.replace("/", os.sep))
    if not os.path.exists(src):
        missing.append(rel)
        continue
    try:
        if os.path.getsize(src) == os.path.getsize(dst) and h(src) == h(dst):
            same.append(rel)
            continue
    except OSError:
        pass
    try:
        if os.path.exists(dst):
            os.chmod(dst, 0o666)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    except Exception as e:
        failed.append("%s: %s" % (rel, e))

print("copied", len(copied))
for c in copied:
    print("  +", c)
print("same", len(same))
print("missing in DEV", len(missing))
for m in missing:
    print("  -", m)
print("failed", len(failed))
for f in failed:
    print("  !", f)
if failed:
    sys.exit(1)
