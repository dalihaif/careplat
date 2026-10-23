# -*- coding: utf-8 -*-
"""灌演示数据到独立演示库（不碰真实数据）

用法：
  CAREPLAT_DB=.../data/demo/demo.db python seed_demo.py
默认写到 data/demo/demo.db（相对项目目录）。
"""
import os
import random
import sys
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
if not os.environ.get('CAREPLAT_DB'):
    os.environ['CAREPLAT_DB'] = os.path.join(BASE, 'data', 'demo', 'demo.db')

import db as DB
import app as A

TODAY = date.today()


def d_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def main():
    conn = DB.connect()
    DB.init_db(conn)
    A.seed_knowledge(conn)
    if conn.execute('SELECT COUNT(*) c FROM patients').fetchone()['c']:
        print('演示库已有数据，先跑 reset.py 或换个库文件')
        return

    # ---------------- 病人 ----------------
    patients = [
        dict(name='张淑芬', sex='女', birth_year=1948, care_level='卧床',
             diagnosis='脑梗死后遗症（右侧偏瘫）', allergies='青霉素过敏',
             condition_desc='长期卧床，右侧肢体不能动，鼻饲进食，交流可。',
             doctor='王建国', doctor_phone='13900001111', hospital='州人民医院神经内科',
             contact_name='李建军', contact_phone='13800002222', contact_relation='儿子',
             weight_current=52.0, start_date=d_ago(120),
             note='夜里有时躁动，注意床挡'),
        dict(name='刘国强', sex='男', birth_year=1955, care_level='半协助',
             diagnosis='左股骨颈骨折术后', allergies='',
             condition_desc='术后 3 周，助行器可短距离行走，防跌倒是重点。',
             doctor='赵敏', doctor_phone='13900003333', hospital='州人民医院骨科',
             contact_name='刘芳', contact_phone='13800004444', contact_relation='女儿',
             weight_current=68.5, start_date=d_ago(24), note=''),
        dict(name='陈玉英', sex='女', birth_year=1952, care_level='自理',
             diagnosis='高血压 2 级、2 型糖尿病', allergies='磺胺类过敏',
             condition_desc='生活自理，重点管好吃药和血压血糖。',
             doctor='孙丽', doctor_phone='13900005555', hospital='社区服务中心',
             contact_name='陈伟', contact_phone='13800006666', contact_relation='儿子',
             weight_current=61.2, start_date=d_ago(200), note=''),
    ]
    pids = []
    for p in patients:
        p['created_at'] = datetime.now().isoformat(timespec='seconds')
        p['status'] = '在照护'
        p['status_changed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        p['active'] = 1
        cols = ', '.join(p)
        ph = ', '.join('?' for _ in p)
        cur = conn.execute(f'INSERT INTO patients ({cols}) VALUES ({ph})', list(p.values()))
        pids.append(cur.lastrowid)
    conn.commit()

    # ---------------- 用药时间表 ----------------
    meds = [
        (pids[0], '阿司匹林', '100mg', '片', '08:00', '早餐后', '抗血小板', '', 1),
        (pids[0], '氨氯地平', '5mg', '片', '08:00,20:00', '', '降压', '', 1),
        (pids[0], '肠内营养粉', '200ml', '袋', '07:30,11:30,17:30', '鼻饲，38-40℃', '营养支持', '缓推', 1),
        (pids[1], '利伐沙班', '10mg', '片', '09:00', '', '抗凝（防血栓）', '', 1),
        (pids[1], '碳酸钙D3', '1片', '片', '20:00', '晚餐后', '补钙', '', 1),
        (pids[2], '氨氯地平', '5mg', '片', '07:00', '晨起', '降压', '', 1),
        (pids[2], '二甲双胍', '0.5g', '片', '07:30,18:00', '餐中', '降糖', '', 1),
    ]
    for pid, name, dose, form, times, usage, purpose, note, active in meds:
        conn.execute(
            'INSERT INTO med_schedule (patient_id, med_name, dose, form, times, usage_txt,'
            ' purpose, note, active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (pid, name, dose, form, times, usage, purpose, note, active,
             datetime.now().isoformat(timespec='seconds')))
    conn.commit()

    # ---------------- 近 30 天体征 ----------------
    rnd = random.Random(42)
    vitals = []
    for pid, base in ((pids[0], (132, 82, 78, 36.5, 97, 6.2)),
                      (pids[1], (128, 78, 74, 36.6, 98, 5.8)),
                      (pids[2], (138, 86, 76, 36.4, 98, 7.4))):
        for i in range(29, -1, -1):
            if rnd.random() < 0.25:
                continue
            day = d_ago(i)
            hi, lo, hr, tp, sp, sg = base
            bp_h = hi + rnd.randint(-8, 12)
            bp_l = lo + rnd.randint(-5, 8)
            temp = round(tp + rnd.uniform(-0.2, 0.5), 1)
            spo2 = max(90, sp + rnd.randint(-2, 1))
            sugar = round(sg + rnd.uniform(-1.2, 1.6), 1)
            weight = round(base[0] * 0 + (61.2 if pid == pids[2] else 52.0 if pid == pids[0] else 68.5) - (29 - i) * 0.01, 1)
            if pid == pids[2] and i in (10, 3):     # 给陈玉英安排两次高血压
                bp_h, bp_l = 158 + rnd.randint(0, 6), 95 + rnd.randint(0, 5)
            if pid == pids[0] and i == 1:           # 张淑芬昨天低热
                temp = 37.8
            vitals.append((pid, day, '08:00', bp_h, bp_l, hr + rnd.randint(-6, 6),
                           temp, spo2, sugar, weight, '晨起测'))
    for v in vitals:
        conn.execute(
            'INSERT INTO vitals (patient_id, day, time, bp_high, bp_low, hr, temp, spo2,'
            ' sugar, weight, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (*v, datetime.now().isoformat(timespec='seconds')))
    conn.commit()

    # ---------------- 近 7 天照护事件 ----------------
    evs = []
    for pid, level in ((pids[0], '卧床'), (pids[1], '半协助'), (pids[2], '自理')):
        for i in range(6, -1, -1):
            day = d_ago(i)
            if level == '卧床':
                for t in ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']:
                    if i == 0 and t >= '14:00':
                        continue    # 今天下午的留给用户自己打卡
                    side = rnd.choice(['左侧卧', '右侧卧', '仰卧'])
                    evs.append((pid, day, t, 'turn', {'side': side, 'key': f'turn-{t}'},
                                '皮肤无异常' if rnd.random() < .8 else '骶尾微红', '护工-王姐'))
                for t in ['07:30', '11:30', '17:30']:
                    if i == 0 and t >= '17:30':
                        continue
                    evs.append((pid, day, t, 'meal',
                                {'food': '营养液 200ml', 'method': '鼻饲', 'eaten': '全部吃完',
                                 'key': f'meal-{t}'}, '', '护工-王姐'))
                for t in ['08:00', '20:00']:
                    if i == 0 and t >= '20:00':
                        continue
                    evs.append((pid, day, t, 'skin',
                                {'finding': '无异常', 'site': '骶尾/足跟', 'key': f'skin-{t}'}, '', '护工-王姐'))
            elif level == '半协助':
                for t in ['07:30', '11:30', '17:30']:
                    if i == 0 and t >= '11:30':
                        continue
                    evs.append((pid, day, t, 'meal',
                                {'food': '软饭+蒸蛋', 'method': '经口协助', 'eaten': '大半',
                                 'key': f'meal-{t}'}, '', '家属-刘芳'))
                evs.append((pid, day, '10:00', 'rehab',
                            {'project': '行走训练', 'minutes': 15, 'success': 2, 'total': 3}, '助行器走走廊两个来回', '家属-刘芳'))
            else:
                if i % 2 == 0 or i == 0:
                    evs.append((pid, day, '08:10', 'med',
                                {'name': '氨氯地平 5mg', 'dose': '1片', 'key': ''}, '', None))
    for pid, day, t, typ, data, note, by in evs:
        conn.execute(
            'INSERT INTO care_events (patient_id, day, time, type, payload, note, by, created_at)'
            ' VALUES (?,?,?,?,?,?,?,?)',
            (pid, day, t, typ, A.json.dumps(data, ensure_ascii=False), note, by,
             datetime.now().isoformat(timespec='seconds')))
    conn.commit()

    # ---------------- 日记（带示例图） ----------------
    try:
        from PIL import Image, ImageDraw
        media_root = os.path.join(DB.UPLOAD_DIR)
        for pid, name, texts in (
                (pids[0], '张淑芬', [('今天精神不错', '鼻饲顺利，下午做了关节活动。'),
                                  ('换了个新气垫床', '翻身频率照旧，皮肤状态稳定。')]),
                (pids[1], '刘国强', [('第一次扶助行器走完走廊', '比昨天多走了 5 米，护膝没问题。')])):
            for idx, (title, content) in enumerate(texts):
                day = d_ago(idx + 1)
                now = datetime.now().strftime('%Y-%m-%d %H:%M')
                cur = conn.execute(
                    'INSERT INTO patient_diary (patient_id, day, title, mood, place, content,'
                    ' created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)',
                    (pid, day, title, '恢复中', '家中', content, now, now))
                did = cur.lastrowid
                sub = os.path.join('diary', str(pid), day.replace('-', '')[:6])
                folder = os.path.join(media_root, sub)
                os.makedirs(folder, exist_ok=True)
                hexname = os.urandom(8).hex()
                fname = f'{hexname}.png'
                fpath = os.path.join(folder, fname)
                im = Image.new('RGB', (640, 400), (235, 245, 242))
                dr = ImageDraw.Draw(im)
                dr.text((40, 40), f'{name} · {title}', fill=(15, 118, 110))
                dr.text((40, 90), content[:20], fill=(60, 80, 76))
                im.save(fpath)
                size = os.path.getsize(fpath)
                conn.execute(
                    'INSERT INTO diary_media (diary_id, patient_id, kind, path, thumb, orig_name,'
                    ' mime, size, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                    (did, pid, 'image', os.path.join(sub, fname).replace('\\', '/'), '',
                     '示例照片.png', 'image/png', size, now))
    except ImportError:
        print('（没装 Pillow，跳过示例图）')
    conn.commit()

    # ---------------- 医疗档案 ----------------
    med_recs = [
        (pids[0], '住院', d_ago(122), None, '州人民医院', '王建国',
         '脑梗死，住院 14 天，遗留右侧偏瘫。医嘱：鼻饲、抗血小板、康复科随诊。', ''),
        (pids[0], '复诊', d_ago(30), d_ago(-60), '州人民医院康复科', '王建国',
         '恢复稳定，继续家庭康复训练。', '带好血压记录'),
        (pids[1], '手术', d_ago(26), None, '州人民医院', '赵敏',
         '左股骨颈骨折，人工髋关节置换术，顺利。', ''),
        (pids[1], '复诊', d_ago(10), d_ago(-18), '州人民医院骨科', '赵敏',
         'X 线示位置良好，逐步负重。', ''),
        (pids[2], '门诊', d_ago(45), None, '社区服务中心', '孙丽',
         '血压血糖控制一般，调整用药。', ''),
    ]
    for r in med_recs:
        conn.execute(
            'INSERT INTO medical_records (patient_id, kind, happen_date, next_due, hospital,'
            ' doctor, summary, note, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (*r, datetime.now().isoformat(timespec='seconds')))
    conn.commit()

    # ---------------- 记账 ----------------
    exps = [
        (pids[0], d_ago(30), '护工工资', '住家护工 10 月工资', 4500, 26, '天', '', '微信', ''),
        (pids[0], d_ago(28), '耗材', '成人纸尿裤 M 码', 89, 2, '包', '京东', '微信', ''),
        (pids[0], d_ago(25), '康复器材', '防压疮气垫床', 780, 1, '张', '医疗器械店', '支付宝', ''),
        (pids[0], d_ago(20), '营养品', '肠内营养粉', 168, 3, '罐', '药店', '微信', ''),
        (pids[1], d_ago(24), '复诊就医', '术后复查挂号+X光', 260, 1, '次', '州人民医院', '微信', ''),
        (pids[1], d_ago(22), '康复器材', '助行器', 210, 1, '台', '药房', '现金', ''),
        (pids[1], d_ago(15), '药品', '利伐沙班', 236, 1, '盒', '药店', '微信', ''),
        (pids[2], d_ago(40), '药品', '二甲双胍', 24, 2, '盒', '社区医院', '现金', ''),
        (pids[2], d_ago(10), '复诊就医', '测血压血糖', 35, 1, '次', '社区中心', '微信', ''),
    ]
    for e in exps:
        conn.execute(
            'INSERT INTO patient_expense (patient_id, day, category, item, amount, qty, unit,'
            ' shop, pay_method, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (*e, datetime.now().isoformat(timespec='seconds')))
    conn.commit()

    n = conn.execute('SELECT COUNT(*) c FROM patients').fetchone()['c']
    print(f'演示数据已灌入：{n} 位病人（{os.environ["CAREPLAT_DB"]}）')
    print('启动演示：CAREPLAT_DB=该库 CAREPLAT_PORT=5811 python app.py')
    conn.close()


if __name__ == '__main__':
    sys.exit(main())
