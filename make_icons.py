# -*- coding: utf-8 -*-
"""生成 PWA 图标（橙色圆角底 + 白色爪印）
用法：python make_icons.py
"""
import os

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'static')

BRAND = (224, 123, 57, 255)
BRAND_D = (196, 97, 31, 255)
WHITE = (255, 255, 255, 255)


def paw(size, pad_ratio=0.0):
    S = size * 4                      # 超采样，边缘更干净
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = int(S * 0.22)                 # 圆角半径
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=BRAND)

    c = S // 2
    tr = int(S * 0.088)               # 脚趾半径
    toes = [(-0.170, -0.150), (-0.058, -0.215), (0.058, -0.215), (0.170, -0.150)]
    for dx, dy in toes:
        x, y = c + int(S * dx), c + int(S * dy)
        d.ellipse([x - tr, y - tr, x + tr, y + tr], fill=WHITE)

    # 掌垫：略宽的椭圆
    pw, ph = int(S * 0.36), int(S * 0.25)
    py = c + int(S * 0.10)
    d.ellipse([c - pw // 2, py - ph // 2, c + pw // 2, py + ph // 2], fill=WHITE)

    img = img.resize((size, size), Image.LANCZOS)

    if pad_ratio:
        inner = int(size * (1 - pad_ratio * 2))
        bg = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        bg.paste(img.resize((inner, inner), Image.LANCZOS),
                 (int(size * pad_ratio), int(size * pad_ratio)))
        img = bg
    return img


made = []
for size, name, pad in [(512, 'icon-512.png', 0.10),
                        (192, 'icon-192.png', 0.10),
                        (180, 'icon-180.png', 0.0),
                        (32, 'icon-32.png', 0.0)]:
    p = os.path.join(OUT, name)
    paw(size, pad).save(p, 'PNG')
    made.append((name, os.path.getsize(p)))

# Windows 快捷方式用的 ico（多尺寸打包）
ico = paw(256, 0.0)
ico_path = os.path.join(OUT, 'icon.ico')
ico.save(ico_path, 'ICO',
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
made.append(('icon.ico', os.path.getsize(ico_path)))

for n, s in made:
    print(f'  {n:16s} {s:>7} bytes')
print('图标生成完成')
