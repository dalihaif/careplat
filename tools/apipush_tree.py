# -*- coding: utf-8 -*-
"""
git push 被网络/代理掐断时的备用发布方案：直接调 GitHub Git Data API 提交整个改动集。

和 apipush.py 的区别：
  - apipush.py 一个文件一个提交（提交记录很碎）；
  - 本脚本走「建 blob → 建 tree → 建 commit → 移动分支指针」四步，
    无论多少文件，远端只产生 1 个干净提交。

用法（在仓库根目录执行，需先 `gh auth login` 登录过）：
    python tools/apipush_tree.py                       # 提交 HEAD 相对 HEAD~1 的改动
    python tools/apipush_tree.py HEAD~3                # 指定对比基准
    python tools/apipush_tree.py HEAD~1 "提交说明"
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

REPO = 'dalihaif/careplat'
BRANCH = 'main'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_REV = sys.argv[1] if len(sys.argv) > 1 else 'HEAD~1'
MSG = sys.argv[2] if len(sys.argv) > 2 else 'chore: 通过 GitHub API 同步站点改动'


def gh_token():
    """依次尝试：环境变量 GH_TOKEN / gh 登录态 / Windows 凭据管理器 / ~/.gh_tmp3。"""
    if os.environ.get('GH_TOKEN'):
        return os.environ['GH_TOKEN'].strip()
    try:
        t = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True)
        if t.returncode == 0 and t.stdout.strip():
            return t.stdout.strip()
    except FileNotFoundError:
        pass
    # git 的 credential helper（本机已存 GitHub 令牌）
    try:
        r = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                           capture_output=True, text=True,
                           env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'})
        for line in r.stdout.splitlines():
            if line.startswith('password=') and len(line) > 45:
                return line.split('=', 1)[1].strip()
    except Exception:
        pass
    f = os.path.join(os.path.expanduser('~'), '.gh_tmp3')
    if os.path.exists(f):
        return open(f).read().strip()
    raise SystemExit('取不到 GitHub 令牌：请设置 GH_TOKEN，或 gh auth login，或把令牌写入 ~/.gh_tmp3')


TOKEN = gh_token()
API = 'https://api.github.com'


def api(method, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'alumni-site-pusher')
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        raise SystemExit('API 失败 %s %s → %s %s' % (method, path, e.code, body[:400]))


def git(args):
    r = subprocess.run(['git'] + args, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit('git 命令失败：git ' + ' '.join(args) + '\n' + r.stderr)
    return r.stdout


# 1) 收集改动：A 新增 / M 修改 / D 删除
status = git(['diff', '--name-status', BASE_REV, 'HEAD'])
changes = []
for line in status.strip().splitlines():
    parts = line.split('\t')
    if len(parts) < 2:
        continue
    st, rel = parts[0].strip()[0], parts[-1].strip()
    changes.append((st, rel.replace(os.sep, '/')))
if not changes:
    raise SystemExit('没有需要提交的改动')
print('待提交 %d 个文件：' % len(changes))

# 2) 当前分支指针
ref = api('GET', '/repos/%s/git/ref/heads/%s' % (REPO, BRANCH))
base_commit = ref['object']['sha']
base_tree = api('GET', '/repos/%s/git/commits/%s' % (REPO, base_commit))['tree']['sha']
print('  远端当前提交：%s' % base_commit[:8])

# 3) 为每个新增/修改的文件建 blob
tree = []
for st, rel in changes:
    if st == 'D':
        tree.append({'path': rel, 'mode': '100644', 'type': 'blob', 'sha': None})
        print('  [删]', rel)
        continue
    p = os.path.join(ROOT, rel.replace('/', os.sep))
    if not os.path.exists(p):
        print('  [跳过·本地已不存在]', rel)
        continue
    b64 = base64.b64encode(open(p, 'rb').read()).decode()
    blob = api('POST', '/repos/%s/git/blobs' % REPO,
               {'content': b64, 'encoding': 'base64'})
    tree.append({'path': rel, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    print('  [写] %-32s %6.1f KB' % (rel, os.path.getsize(p) / 1024.0))

# 4) tree → commit → 移动分支
new_tree = api('POST', '/repos/%s/git/trees' % REPO,
               {'base_tree': base_tree, 'tree': tree})
new_commit = api('POST', '/repos/%s/git/commits' % REPO,
                 {'message': MSG, 'tree': new_tree['sha'], 'parents': [base_commit]})
api('POST', '/repos/%s/git/refs/heads/%s' % (REPO, BRANCH), {'sha': new_commit['sha']})

print('\n完成：%s  →  https://github.com/%s/commit/%s'
      % (MSG, REPO, new_commit['sha'][:8]))
print('Pages 地址：https://dalihaif.github.io/careplat/  （约 1 分钟后生效）')
