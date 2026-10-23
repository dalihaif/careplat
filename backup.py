# -*- coding: utf-8 -*-
"""照护管理平台 · 备份工具

备份内容 = SQLite 数据库（用 sqlite3 backup API，运行中备份也不会坏）+ uploads 照片视频目录。

用法：
  python backup.py                    # 备到 ./backups/backup_YYYYMMDD_HHMMSS/
  python backup.py D:\\backups        # 备到指定目录（本地盘或 NAS 共享盘符）
  python backup.py \\\\NAS\\share      # 备到 NAS 的 UNC 路径（飞牛 NAS 映射后可用）
  python backup.py --keep 14          # 只保留最近 14 份，老的自动删

也可直接双击「自动备份.bat」。
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import db as DB  # noqa: E402


def backup_db_to(src_path, dest_path):
    """用 sqlite3 在线备份 API，主库正在写也能备出一致的副本"""
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dest_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def backup(dest_root, keep=0):
    dest_root = os.path.abspath(dest_root)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(dest_root, f'backup_{stamp}')
    os.makedirs(dest, exist_ok=True)

    # 1) 数据库
    db_path = DB.DB_PATH
    if not os.path.exists(db_path):
        print(f'❌ 数据库不存在：{db_path}')
        return 1
    dst_db = os.path.join(dest, os.path.basename(db_path))
    backup_db_to(db_path, dst_db)
    print(f'✅ 数据库 → {dst_db}')

    # 2) 照片视频目录
    up = DB.UPLOAD_DIR
    if os.path.isdir(up):
        dst_up = os.path.join(dest, 'uploads')
        shutil.copytree(up, dst_up, ignore=shutil.ignore_patterns('*.tmp'))
        n = sum(len(files) for _, _, files in os.walk(dst_up))
        print(f'✅ 照片视频（{n} 个文件）→ {dst_up}')
    else:
        print('ℹ️ 没有上传目录，跳过照片')

    # 3) 保留策略
    if keep > 0:
        olds = sorted(
            d for d in os.listdir(dest_root)
            if d.startswith('backup_') and os.path.isdir(os.path.join(dest_root, d)))
        for d in olds[:-keep]:
            shutil.rmtree(os.path.join(dest_root, d), ignore_errors=True)
            print(f'🧹 清理旧备份 {d}')
    print(f'🎉 备份完成：{dest}')
    return 0


def main():
    ap = argparse.ArgumentParser(description='照护管理平台备份工具')
    ap.add_argument('dest', nargs='?', default=None, help='备份目标目录（默认 ./backups）')
    ap.add_argument('--keep', type=int, default=0, help='保留最近 N 份（0=不清理）')
    a = ap.parse_args()
    dest = a.dest or os.path.join(BASE, 'backups')
    return backup(dest, a.keep)


if __name__ == '__main__':
    sys.exit(main())
