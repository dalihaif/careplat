# -*- coding: utf-8 -*-
"""照护管理平台 · 公网访问（Cloudflare 快速隧道）

一条命令做三件事：
  1. 检查本地服务（5810）是否在跑，没跑就自己拉起来
  2. 用 cloudflared 开一条 Cloudflare 隧道，拿到 https://xxx.trycloudflare.com
  3. 把公网地址 + 访问密码写进 data/公网地址.txt，并打印到屏幕

注意：快速隧道的域名**每次启动都会变**，重启后请重新看屏幕上的地址。
隧道断线会自动重连（最多 20 次）。
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
PORT = os.environ.get('CAREPLAT_PORT', '5810')
CF = os.path.join(BASE, 'tools', 'cloudflared.exe')
LOG = os.path.join(DATA, 'tunnel.log')
PWD_FILE = os.path.join(DATA, '访问密码.txt')
URL_RE = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')


def say(msg=''):
    print(msg, flush=True)


def service_ok():
    try:
        req = urllib.request.Request('http://127.0.0.1:%s/api/health' % PORT)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def start_service():
    py = sys.executable
    bat = os.path.join(BASE, '启动服务.bat')
    say('  本地服务没在跑，正在拉起……')
    if os.name == 'nt':
        # 新窗口跑服务，关掉这个窗口也不影响平台
        subprocess.Popen(['cmd', '/c', 'start', '照护管理平台 · 服务', py, os.path.join(BASE, 'app.py')],
                         cwd=BASE)
    else:
        subprocess.Popen([py, os.path.join(BASE, 'app.py')], cwd=BASE)
    for _ in range(30):
        time.sleep(1)
        if service_ok():
            return True
    return False


def read_pwd():
    try:
        with open(PWD_FILE, encoding='utf-8') as f:
            m = re.search(r'访问密码：(\S+)', f.read())
            return m.group(1) if m else '（见 data/访问密码.txt）'
    except OSError:
        return '（还没生成，先启动一次服务）'


def ensure_cloudflared():
    """tools/ 里没有 cloudflared.exe 就自动下（直连慢，走国内镜像）"""
    if os.path.exists(CF):
        return True
    os.makedirs(os.path.dirname(CF), exist_ok=True)
    urls = [
        'https://gh-proxy.com/https://github.com/cloudflare/cloudflared/releases'
        '/latest/download/cloudflared-windows-amd64.exe',
        'https://github.com/cloudflare/cloudflared/releases'
        '/latest/download/cloudflared-windows-amd64.exe',
    ]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for u in urls:
        try:
            say('  下载 cloudflared（约 53MB，走镜像）……')
            with opener.open(u, timeout=60) as r, open(CF + '.part', 'wb') as f:
                total = int(r.headers.get('Content-Length') or 0)
                got = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        say('    %d%%  %.1f/%.1f MB' % (got * 100 // total, got / 1048576, total / 1048576))
            if os.path.getsize(CF + '.part') > 10 * 1048576:
                os.replace(CF + '.part', CF)
                say('  ✅ cloudflared 就绪')
                return True
            os.remove(CF + '.part')
        except Exception as e:
            say('  下载失败：%s' % e)
    return False


def run_tunnel():
    os.makedirs(DATA, exist_ok=True)
    if not ensure_cloudflared():
        say('❌ 拿不到 cloudflared.exe：请手动下载后放到 tools/ 目录')
        return 1
    logf = open(LOG, 'w', encoding='utf-8', buffering=1)
    proc = subprocess.Popen([CF, 'tunnel', '--url', 'http://127.0.0.1:%s' % PORT,
                             '--no-autoupdate'],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=BASE, text=True, encoding='utf-8', errors='replace',
                            bufsize=1)
    url = None
    t0 = time.time()
    say('')
    say('  正在连接 Cloudflare……（第一次约 5～15 秒）')
    for line in proc.stdout:
        logf.write(line)
        if not url:
            m = URL_RE.search(line)
            if m:
                url = m.group(0)
                pwd = read_pwd()
                say('')
                say('  ' + '=' * 62)
                say('   🌍 公网地址（手机 4G 也能开）：')
                say('      ' + url)
                say('   🔑 访问密码：' + pwd)
                say('  ' + '-' * 62)
                say('   · 域名每次重启都会变，变了重新看这里')
                say('   · 电脑要开着、这个窗口不能关，关了公网就断')
                say('   · 想停：按 Ctrl+C（不影响本地局域网访问）')
                say('  ' + '=' * 62)
                say('')
                try:
                    with open(os.path.join(DATA, '公网地址.txt'), 'w', encoding='utf-8') as f:
                        f.write('照护管理平台 · 公网访问\n\n'
                                '公网地址：%s\n访问密码：%s\n生成时间：%s\n\n'
                                '· 本地址只在本次运行有效，重启后重新生成\n'
                                '· 电脑关机 / 关闭「公网访问」窗口 → 公网立刻断开\n'
                                '· 本地局域网访问不受影响：http://<本机IP>:%s\n'
                                % (url, pwd, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), PORT))
                except OSError:
                    pass
        elif 'ERR' in line and ('failed' in line or 'error' in line.lower()):
            say('  ⚠️ ' + line.strip()[:160])
    code = proc.wait()
    logf.close()
    if url and time.time() - t0 > 5:
        say('  ⚠️ 隧道断开了（网络波动？），正在自动重连……')
    return code


def main():
    say('')
    say('=' * 64)
    say('  照护管理平台 · 公网访问')
    say('=' * 64)
    if not service_ok():
        if not start_service():
            say('  ❌ 本地服务没能启动，先单独跑一下「启动服务.bat」看看报什么错')
            return 1
    say('  ✅ 本地服务正常（127.0.0.1:%s）' % PORT)
    tries = 0
    while tries < 20:
        tries += 1
        run_tunnel()
        if tries < 20:
            time.sleep(3)
    say('  隧道连续 20 次没起来，检查网络（Cloudflare 需要能出网）。')
    return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say('\n  已停止公网访问（本地局域网仍在）。')
