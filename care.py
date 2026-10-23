# -*- coding: utf-8 -*-
"""照护管理平台 · 业务逻辑与内置知识

参照狗狗管理平台的 biz.py / knowledge.py 合并而来：
- 任务时间表（翻身 / 进食 / 饮水 / 皮肤检查）+ 用药时间表 → 今日时间轴
- 预警：漏服、翻身超时、体征异常、复诊到期
- 统计：打卡率、近 N 天行为统计、照护周报
- 内置照护知识底表（压疮 / 用药 / 康复 / 饮食 / 体征）
"""
import json
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- 枚举与配置
PATIENT_STATUS = ('在照护', '康复出院', '转院', '去世', '其他')
STATUS_MANAGED = '在照护'
STATUS_CHIP = {'在照护': 'ok', '康复出院': 'brand', '转院': 'brand',
               '去世': 'danger', '其他': ''}
STATUS_TIP = {
    '在照护': '当前正在照护，正常排任务、打卡、提醒',
    '康复出院': '已康复出院 / 结束照护，档案保留不再提醒',
    '转院': '已转入其他医院 / 机构，档案保留不再提醒',
    '去世': '已离世，档案保留不再提醒',
    '其他': '其他情况（如短期离家、他人代管），不参与提醒',
}

CARE_LEVELS = ('自理', '半协助', '全协助', '卧床')
LEVEL_TIP = {
    '自理': '生活基本自理，只做用药和体征提醒',
    '半协助': '部分动作需要帮助（洗澡、做饭、外出），翻身类任务酌情安排',
    '全协助': '大部分日常需要协助，三餐 / 饮水 / 皮肤检查全排',
    '卧床': '长期卧床，翻身每 2 小时一次是硬任务，皮肤检查早晚各一次',
}

# 照护事件类型（type → 中文）
EVENT_TYPES = [
    ('turn', '翻身'), ('meal', '进食'), ('water', '饮水'), ('med', '服药'),
    ('rehab', '康复训练'), ('potty', '排泄'), ('skin', '皮肤检查'),
    ('bath', '洗澡擦浴'), ('handover', '交接班'), ('weight', '体重'),
    ('note', '备注'),
]
EVENT_LABEL = dict(EVENT_TYPES)

# 任务时间点模板（只对「全协助 / 卧床」全排；半协助排进食饮水；自理只排用药）
MEAL_TIMES = ['07:30', '11:30', '17:30']
WATER_TIMES = ['09:30', '15:00', '20:30']
TURN_TIMES = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']
SKIN_TIMES = ['08:30', '20:00']

# 体征参考区间（供标红提示，不构成诊断；以医生给的个体化目标为准）
VITAL_DEFS = [
    ('bp_high', '收缩压（高压）', 'mmHg', 60, 260, '如 120'),
    ('bp_low', '舒张压（低压）', 'mmHg', 40, 160, '如 80'),
    ('hr', '心率', '次/分', 35, 220, '如 76'),
    ('temp', '体温', '℃', 34.0, 43.0, '如 36.5'),
    ('spo2', '血氧', '%', 60, 100, '如 98'),
    ('sugar', '血糖', 'mmol/L', 1.5, 35.0, '如 6.1'),
    ('weight', '体重', 'kg', 2, 300, '如 62.5'),
]


def judge_vital(key, v):
    """返回 'ok' / 'warn' / 'danger'，仅供提醒，不是诊断"""
    if v is None:
        return 'ok'
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 'ok'
    if key == 'bp_high':
        return 'danger' if v >= 180 or v < 90 else ('warn' if v >= 140 else 'ok')
    if key == 'bp_low':
        return 'danger' if v >= 110 or v < 55 else ('warn' if v >= 90 else 'ok')
    if key == 'hr':
        return 'danger' if v > 120 or v < 50 else ('warn' if v > 100 or v < 60 else 'ok')
    if key == 'temp':
        return 'danger' if v >= 38.5 or v < 35.5 else ('warn' if v >= 37.3 else 'ok')
    if key == 'spo2':
        return 'danger' if v < 90 else ('warn' if v < 95 else 'ok')
    if key == 'sugar':
        return 'danger' if v < 3.9 or v > 16.7 else ('warn' if v > 10.0 else 'ok')
    return 'ok'


VITAL_OK_TIP = '参考区间：高压<140 / 低压<90 / 心率 60-100 / 体温<37.3 / 血氧≥95 / 血糖 3.9-10.0（随机），异常请结合症状并咨询医生'

DISCLAIMER = ('本平台只做家庭照护的记录与提醒，所有用药、剂量、康复动作均请遵医嘱；'
              '体征参考区间来自通用科普资料，不构成诊断建议。'
              '出现高热、呼吸困难、意识改变等情况请立即就医或拨打 120。')


def parse_date(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def age_text(birth_year, on=None):
    if not birth_year:
        return None
    try:
        by = int(birth_year)
    except (TypeError, ValueError):
        return None
    y = (on or date.today()).year
    return f'{y - by} 岁'


def bed_days(start_date, on=None):
    d = parse_date(start_date)
    if not d:
        return None
    return ((on or date.today()) - d).days + 1


# ---------------------------------------------------------------- 事件读写
def events_of(conn, pid, day=None, limit=None):
    """某病人（可限某天）的全部照护事件，payload 解析成 data 字典"""
    sql = 'SELECT * FROM care_events WHERE patient_id=?'
    args = [pid]
    if day:
        sql += ' AND day=?'
        args.append(day)
    sql += ' ORDER BY day DESC, time DESC, id DESC'
    if limit:
        sql += f' LIMIT {int(limit)}'
    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        try:
            d['data'] = json.loads(d['payload']) if d['payload'] else {}
        except (ValueError, TypeError):
            d['data'] = {}
        out.append(d)
    return out


def event_data(e):
    try:
        return json.loads(e['payload']) if e['payload'] else {}
    except (ValueError, TypeError):
        return {}


# ---------------------------------------------------------------- 今日时间轴
def _sched_slots(conn, patient):
    """用药时间表 → 任务槽。返回 [{key,type,time,title,detail}]"""
    slots = []
    for m in conn.execute(
            'SELECT * FROM med_schedule WHERE patient_id=? AND active=1 ORDER BY id',
            (patient['id'],)).fetchall():
        times = [t.strip() for t in (m['times'] or '').split(',') if t.strip()]
        for t in times:
            slots.append({
                'key': f'med-{m["id"]}-{t}', 'type': 'med', 'time': t,
                'title': f'{m["med_name"]}（{m["dose"] or "?"}{m["form"] or ""}）',
                'detail': ' · '.join(x for x in [m['usage_txt'], m['purpose']] if x),
                'def_name': m['med_name'],
                'def_dose': (str(m['dose'] or '') + (m['form'] or '')).strip(),
            })
    return slots


def _fixed_slots(patient):
    """按照护等级生成的固定任务槽（进食 / 饮水 / 翻身 / 皮肤）"""
    level = patient['care_level'] or '全协助'
    slots = []
    if level in ('半协助', '全协助', '卧床'):
        for t in MEAL_TIMES:
            slots.append({'key': f'meal-{t}', 'type': 'meal', 'time': t,
                          'title': '进餐', 'detail': '记录吃了多少、怎么吃的'})
        for t in WATER_TIMES:
            slots.append({'key': f'water-{t}', 'type': 'water', 'time': t,
                          'title': '饮水', 'detail': '记录饮水量，防脱水'})
    if level == '卧床':
        for t in TURN_TIMES:
            slots.append({'key': f'turn-{t}', 'type': 'turn', 'time': t,
                          'title': '翻身', 'detail': '左右侧轮换，顺手看一眼皮肤'})
        for t in SKIN_TIMES:
            slots.append({'key': f'skin-{t}', 'type': 'skin', 'time': t,
                          'title': '皮肤检查', 'detail': '重点看骶尾、足跟、髋部有没有压红'})
    return slots


def today_timeline(conn, patient, day):
    """当天完整任务时间轴 + 完成统计。
    返回 (timeline, hit, total)。done 判断依据：care_events.payload.key 相同。
    """
    slots = _sched_slots(conn, patient) + _fixed_slots(patient)
    slots.sort(key=lambda s: s['time'])
    done_keys = set()
    for e in conn.execute(
            'SELECT payload FROM care_events WHERE patient_id=? AND day=?',
            (patient['id'], day)).fetchall():
        d = event_data(e)
        if d.get('key'):
            done_keys.add(d['key'])
    timeline = []
    hit = 0
    for s in slots:
        done = s['key'] in done_keys
        hit += done
        timeline.append({**s, 'done': done})
    return timeline, hit, len(slots)


# ---------------------------------------------------------------- 预警
def alerts_for(conn, patient):
    """首页/工作台的预警条：漏服药、翻身超时、体征异常、复诊到期"""
    if (patient.get('status') or STATUS_MANAGED) != STATUS_MANAGED:
        return []
    pid = patient['id']
    today = date.today().isoformat()
    now_hm = datetime.now().strftime('%H:%M')
    out = []

    # 1) 漏服药（时间点已过且当天没打）
    sched = _sched_slots(conn, patient)
    done_keys = set()
    for e in conn.execute(
            'SELECT payload FROM care_events WHERE patient_id=? AND day=?',
            (pid, today)).fetchall():
        d = event_data(e)
        if d.get('key'):
            done_keys.add(d['key'])
    missed = [s for s in sched if s['time'] <= now_hm and s['key'] not in done_keys]
    if missed:
        names = '、'.join(f'{s["title"]}({s["time"]})' for s in missed[:4])
        more = f' 等 {len(missed)} 项' if len(missed) > 4 else ''
        out.append({
            'level': 'danger', 'cat': 'missed', 'title': f'今天还有 {len(missed)} 项任务没打卡{more}',
            'detail': f'未完成：{names}',
            'action': '点「今日照护」补打卡；如果药确实漏了，先咨询医生怎么补，不要自行加倍',
        })

    # 2) 翻身超时（卧床 + 现在在白天时段）
    if (patient['care_level'] or '') == '卧床':
        if '07:00' <= now_hm <= '22:30':
            last = conn.execute(
                "SELECT day, time FROM care_events WHERE patient_id=? AND type='turn'"
                ' ORDER BY day DESC, time DESC LIMIT 1', (pid,)).fetchone()
            if last:
                dt = datetime.now() - datetime.fromisoformat(
                    f'{last["day"]}T{last["time"] or "00:00"}:00')
                mins = dt.total_seconds() / 60
                if mins > 120:
                    out.append({
                        'level': 'danger' if mins > 180 else 'warn', 'cat': 'missed',
                        'title': f'已 {int(mins)} 分钟没翻身',
                        'detail': f'上次翻身：{last["day"]} {last["time"]}',
                        'action': '卧床病人每 2 小时翻身一次，压疮拖不得',
                    })

    # 3) 体征异常（最近一条；没填时间的记录视为「刚测的」排最前）
    v = conn.execute('SELECT * FROM vitals WHERE patient_id=?'
                     " ORDER BY day DESC, IFNULL(time,'99:99') DESC, id DESC LIMIT 1",
                     (pid,)).fetchone()
    if v:
        bad = []
        for key, label, unit, lo, hi, _ph in VITAL_DEFS:
            val = v[key]
            st = judge_vital(key, val)
            if st != 'ok' and val is not None:
                bad.append(f'{label} {val:g}{unit}（{"偏高" if st == "warn" else "异常"}）'
                           if key in ('bp_high', 'bp_low', 'hr', 'temp')
                           else f'{label} {val:g}{unit}（{"偏低" if st == "warn" else "异常"}）')
        if bad:
            out.append({
                'level': 'danger', 'cat': 'vitals',
                'title': f'最近体征有 {len(bad)} 项异常',
                'detail': '；'.join(bad[:4]) + f'（{v["day"]} {v["time"] or ""} 测）',
                'action': '持续异常或伴不适，及时联系医生；这里是参考提示，不是诊断',
            })

    # 4) 复诊提醒
    for r in conn.execute(
            "SELECT kind, next_due, summary FROM medical_records"
            " WHERE patient_id=? AND next_due IS NOT NULL AND next_due>?",
            (pid, today)).fetchall():
        days = (parse_date(r['next_due']) - date.today()).days
        if days <= 7:
            out.append({
                'level': 'warn', 'cat': 'visit',
                'title': f'{r["next_due"]} 有{"复诊" if r["kind"] == "复诊" else r["kind"] or "安排"}'
                         f'（还有 {days} 天）',
                'detail': r['summary'] or '',
                'action': '提前挂好号、带上病历和正在吃的药',
            })
    return out


# ---------------------------------------------------------------- 统计
def range_stats(conn, patient, days=7):
    """近 N 天统计：任务完成率、服药率、翻身次数、进食饮水、康复"""
    pid = patient['id']
    end = date.today()
    start = end - timedelta(days=days - 1)
    days_list = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    evs = events_of(conn, pid, limit=100000)
    by_day = {}
    for e in evs:
        if start.isoformat() <= e['day'] <= end.isoformat():
            by_day.setdefault(e['day'], []).append(e)

    # 每天「计划任务数」按当天等级重算（等级改过也能对上）
    p = dict(patient)
    daily = []
    for d in days_list:
        _, hit, total = today_timeline_for(conn, p, d)
        ev = by_day.get(d, [])
        turns = sum(1 for e in ev if e['type'] == 'turn')
        meals = sum(1 for e in ev if e['type'] == 'meal')
        waters = sum(1 for e in ev if e['type'] == 'water')
        ml = sum((e['data'].get('ml') or 0) for e in ev if e['type'] == 'water')
        meds = sum(1 for e in ev if e['type'] == 'med')
        rehabs = sum(1 for e in ev if e['type'] == 'rehab')
        daily.append({'day': d, 'hit': hit, 'total': total,
                      'pct': round(hit / total * 100) if total else 0,
                      'turns': turns, 'meals': meals, 'waters': waters,
                      'ml': ml, 'meds': meds, 'rehabs': rehabs})

    hit = sum(d['hit'] for d in daily)
    total = sum(d['total'] for d in daily)
    return {
        'days': days, 'daily': daily, 'hit': hit, 'total': total,
        'pct': round(hit / total * 100) if total else 0,
        'turns': sum(d['turns'] for d in daily),
        'meals': sum(d['meals'] for d in daily),
        'ml': sum(d['ml'] for d in daily),
        'meds': sum(d['meds'] for d in daily),
        'rehabs': sum(d['rehabs'] for d in daily),
        'events': sum(len(by_day.get(d, [])) for d in days_list),
        'days_list': days_list,
    }


def today_timeline_for(conn, patient, day):
    """同 today_timeline，但支持任意日期（统计用）"""
    return today_timeline(conn, patient, day)


def verdict(stats):
    """给周报一句总评"""
    p = stats['pct']
    if p >= 90:
        return '优秀', '任务完成率很高，照护节奏稳定，继续保持。'
    if p >= 70:
        return '良好', '大部分任务完成了，看看漏掉的是哪几项，是时间不合适还是忘了。'
    if p >= 40:
        return '一般', '完成率偏低，建议把提醒时间调到护工顺手的时间点，或减少非必要任务。'
    return '需要关注', '大量任务没打卡，先确认是没做还是没记——记录本身也是照护的一部分。'


def next_week_plan(stats):
    """按统计结果给下周 3 条建议"""
    tips = []
    if (patient_level_needs_turn := stats.get('turns')) is not None and stats['total'] and \
            stats['hit'] / stats['total'] < 0.7:
        tips.append('完成率偏低：考虑减少任务点，先保证「用药 + 进食」两项不漏。')
    if stats['ml'] and stats['ml'] / max(len(stats['days_list']), 1) < 1200:
        tips.append('日均饮水偏低（<1200ml）：增加水杯出现频次，或把饮水和吃药绑定提醒。')
    if stats['rehabs'] == 0:
        tips.append('本周没有康复训练记录：从每天 10 分钟的轻量训练开始，动比不动强。')
    if not tips:
        tips.append('整体节奏不错：下周可以尝试把体征测量固定在每天同一时间，形成趋势。')
    return tips


# ---------------------------------------------------------------- 文本报告
def weekly_report(conn, patient, days=7):
    """纯文本周报：家属手机上一眼能看完，可直接复制/发邮件"""
    stats = range_stats(conn, patient, days)
    v, vd = care_verdict(stats)
    today = date.today().isoformat()
    lines = [
        f'【照护周报】{patient["name"]} · 近{days}天（截至 {today}）',
        f'综合评价：{v} —— {vd}',
        '',
        f'✔ 任务完成率：{stats["pct"]}%（{stats["hit"]}/{stats["total"]}）',
        f'💊 服药打卡：{stats["meds"]} 次',
        f'🍚 进餐记录：{stats["meals"]} 次',
        f'🔄 翻身：{stats["turns"]} 次',
        f'💪 康复训练：{stats["rehabs"]} 次',
        f'💧 日均饮水：{(stats["ml"] // max(stats["days"], 1))} ml',
    ]
    lv = conn.execute(
        'SELECT * FROM vitals WHERE patient_id=?'
        " ORDER BY day DESC, IFNULL(time,'99:99') DESC, id DESC LIMIT 1",
        (patient['id'],)).fetchone()
    if lv:
        bits = [f'{label} {lv[key]:g}{unit}'
                for key, label, unit, lo, hi, ph in VITAL_DEFS
                if lv[key] is not None]
        lines.append('')
        lines.append(f'🩺 最近体征（{lv["day"]} {lv["time"] or ""}）：' + '，'.join(bits))
    meds = conn.execute(
        'SELECT med_name, dose, form, times FROM med_schedule'
        ' WHERE patient_id=? AND active=1 ORDER BY id', (patient['id'],)).fetchall()
    if meds:
        lines.append('')
        lines.append('💊 在服药品：')
        for m in meds:
            lines.append(f'  · {m["med_name"]} {m["dose"] or ""}{m["form"] or ""}（{m["times"]}）')
    tips = next_week_plan(stats)
    lines.append('')
    lines.append('💡 下周建议：')
    for t in tips:
        lines.append(f'  · {t}')
    lines.append('')
    lines.append('—— 由照护管理平台自动生成，数据来自家庭照护日常记录')
    return '\n'.join(lines)


def visit_checklist(conn, patient):
    """复诊准备清单：下次复诊前的「要带的东西 + 要说的话」"""
    today = date.today().isoformat()
    rec = conn.execute(
        'SELECT * FROM medical_records WHERE patient_id=? AND next_due IS NOT NULL'
        ' AND next_due>=? ORDER BY next_due LIMIT 1',
        (patient['id'], today)).fetchone()
    due = rec['next_due'] if rec else '（尚未安排复诊，以下清单通用）'
    lines = [f'【复诊准备清单】{patient["name"]} · 复诊日期：{due}', '']
    lines.append('📋 证件与材料：')
    lines.append('  · 医保卡 / 就诊卡、身份证')
    if patient['hospital'] or patient['doctor']:
        lines.append(f'  · 就诊医院：{patient["hospital"] or "—"}'
                     f'{("（主治：" + patient["doctor"] + "）") if patient["doctor"] else ""}')
    lines.append('  · 以往病历 / 出院小结 / 检查报告')
    if patient['allergies']:
        lines.append(f'  ⚠️ 过敏史：{patient["allergies"]}（记得主动告诉医生）')
    meds = conn.execute(
        'SELECT med_name, dose, form, times, usage_txt FROM med_schedule'
        ' WHERE patient_id=? AND active=1 ORDER BY id', (patient['id'],)).fetchall()
    lines.append('')
    if meds:
        lines.append('💊 带上正在吃的药（或拍下药盒），告诉医生实际怎么吃的：')
        for m in meds:
            lines.append(f'  · {m["med_name"]} {m["dose"] or ""}{m["form"] or ""}（{m["times"]}）'
                         f'{m["usage_txt"] or ""}')
    else:
        lines.append('💊 在服药品：未登记（建议先在「用药管理」里补全）')
    lv = conn.execute(
        'SELECT * FROM vitals WHERE patient_id=?'
        " ORDER BY day DESC, IFNULL(time,'99:99') DESC, id DESC LIMIT 1",
        (patient['id'],)).fetchone()
    if lv:
        bits = [f'{label} {lv[key]:g}{unit}'
                for key, label, unit, lo, hi, ph in VITAL_DEFS if lv[key] is not None]
        lines.append('')
        lines.append(f'🩺 最近一次体征（{lv["day"]}）：' + '，'.join(bits))
        lines.append('  （体征趋势图可在平台导出截图给医生看）')
    lines.append('')
    lines.append('❓ 想问医生的问题（提前写下来，见了医生容易忘）：')
    lines.append('  · 1. ________________')
    lines.append('  · 2. ________________')
    lines.append('')
    lines.append('📱 就诊当天有情况随时联系家属：'
                 f'{patient["contact_name"] or "—"} {patient["contact_phone"] or ""}')
    return '\n'.join(lines)


def care_verdict(stats):
    return verdict(stats)


# ---------------------------------------------------------------- 内置知识底表
CARE_KNOWLEDGE = [
    ('压疮', '翻身频率', '长期卧床每 2 小时翻身一次，坐轮椅每 1 小时换一次重心；'
     '翻身时避免拖拽，要抬起来再挪。', '国家卫健委《压疮护理指导原则》相关共识'),
    ('压疮', '压疮高发部位', '骶尾部、足跟、髋部（股骨大转子）、肘部、后脑勺、肩胛；'
     '重点看骨突处有没有压红，压红 30 分钟不退就要警惕。', '通用护理科普'),
    ('压疮', '皮肤日常护理', '保持皮肤清洁干燥，出汗、尿便后及时清洗擦干；'
     '可用温和润肤霜，不要用力搓揉发红部位。', '通用护理科普'),
    ('压疮', '发现压疮怎么办', '一期（压红不退）加强翻身减压、保持干燥；'
     '出现破皮、水疱不要自行上药，拍照记录并联系医生或护士上门。', '通用护理科普'),
    ('用药', '服药打卡原则', '按医嘱时间点服药并打卡；漏服不要自行加倍补服，'
     '先咨询医生或药师。多种药同服前确认有无相互作用。', '《中国居民用药安全常识》科普'),
    ('用药', '药品保管', '避光、干燥、儿童够不到；需要冷藏的（如胰岛素）放冰箱冷藏室，'
     '不要冷冻；定期清理过期药。', '通用用药科普'),
    ('用药', '鼻饲给药', '鼻饲药物需研碎溶解后注入，给药前后各用温水冲管 20-30ml；'
     '缓释片、肠溶片不可研碎，请遵医嘱。', '临床鼻饲护理常规'),
    ('康复', '康复训练原则', '循序渐进、少量多次：从每天 10-15 分钟开始，'
     '以「第二天不加重疲劳酸痛」为度；训练中头晕、胸闷、疼痛立即停止。', '康复医学科普'),
    ('康复', '卧床防血栓', '卧床期间多做踝泵运动（脚背来回勾绷），'
     '每 1-2 小时一组、每组 20 次；能下地尽早下地，遵医嘱使用弹力袜。', '血管外科科普'),
    ('康复', '协助行走安全', '搀扶时站在患者患侧稍后方，让患者抓你的腰带或转移带；'
     '先坐床沿 30 秒再站起，防体位性低血压跌倒。', '通用照护科普'),
    ('饮食', '饮水目标', '无限水要求时每天 1500-1700ml，分次少量喝；'
     '心衰、肾衰等限水病人严格按医嘱执行。', '《中国居民膳食指南》'),
    ('饮食', '吞咽困难进食', '吃饭坐直或半坐位（床头摇高≥60°），小口慢咽；'
     '饭后保持坐位 30 分钟再躺下，防误吸；呛咳频繁要改糊状食物并咨询医生。', '老年照护科普'),
    ('饮食', '鼻饲护理要点', '每次鼻饲前回抽确认胃管在胃内并观察残留量；'
     '营养液温度 38-40℃，缓慢推注；鼻饲后 30 分钟内避免翻身叩背（防反流）。', '临床鼻饲护理常规'),
    ('体征', '测量时间建议', '血压每天固定时间测（如晨起服药前），测前静坐 5 分钟；'
     '体温、血氧有异常再加密测量，把「同时间可对比」放在第一位。', '通用监测科普'),
    ('排泄', '排尿排便观察', '关注次数、量、颜色和性状：尿少、尿色深提示饮水不足；'
     '黑便、血尿要及时就医；腹泻注意补水和清洁，防失禁性皮炎。', '通用护理科普'),
    ('心理', '照护者自我关照', '长期照护者自己也会耗竭：保证睡眠、定期换手休息，'
     '情绪崩溃不是矫情；感到持续疲惫易怒时，主动向家人或社区寻求支持。', 'WHO 照护者支持建议'),
]

REHAB_PROJECTS = ['关节活动（被动）', '踝泵运动', '抬腿练习', '坐位平衡',
                  '站立训练', '行走训练', '握力/上肢', '呼吸训练', '拍背排痰']

MEAL_METHODS = ['经口正常', '经口协助', '糊状/软食', '流食', '鼻饲']
MEAL_EATEN = ['全部吃完', '大半', '一半', '少量', '未进']
SKIN_FINDINGS = ['无异常', '压红（可退）', '压红（不退）', '破皮/水疱', '已有压疮（观察）']
TURN_SIDES = ['左侧卧', '右侧卧', '仰卧', '俯卧', '半坐卧']
