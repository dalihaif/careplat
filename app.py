# -*- coding: utf-8 -*-
"""照护管理平台 · Flask 应用（架构借鉴狗狗管理平台）"""
import csv
import io
import json
import mimetypes
import os
import socket
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import quote

from flask import (Flask, Response, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)

import care
import db as DB

app = Flask(__name__)
app.config['SECRET_KEY'] = 'careplat-local-key'
app.config['JSON_AS_ASCII'] = False
# 上传上限：单个请求 300MB（够放一段手机短视频）
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024
app.teardown_appcontext(DB.close_db)

# ---------------------------------------------------------------- 作者 / 版本
APP_NAME = '照护管理平台'
APP_VERSION = 'v1.0'
APP_SINCE = '2026-10-24'
AUTHOR = {
    'name': '李海峰',
    'phone': '13988531240',
    'email': 'dalihaif@qq.com',
    'org': '大理大学第一附属医院',
    'github': 'dalihaif',
    'github_url': 'https://github.com/dalihaif',
    'city': '云南 · 大理',
    'slogan': '技术改变工作，设计美化生活',
    'intro': '档案管理从业者，在医院工作让我见过太多「照护全靠脑子记」的家庭。'
             '这个平台把翻身、喂药、体征、康复、花销这些琐碎都落到一处，'
             '护工记、家属看，谁也不用靠记性。',
}

PATIENT_STATUS = care.PATIENT_STATUS
STATUS_CHIP = care.STATUS_CHIP
STATUS_TIP = care.STATUS_TIP
CARE_LEVELS = care.CARE_LEVELS
LEVEL_TIP = care.LEVEL_TIP

# ---------------------------------------------------------------- 日记 & 记账配置
DIARY_MOODS = [('平稳', '🙂'), ('精神好', '😊'), ('疲惫', '😣'), ('不适', '🤒'),
               ('疼痛', '😖'), ('情绪低', '😔'), ('恢复中', '💪')]
DIARY_MOOD_EMOJI = dict(DIARY_MOODS)

# 记账分类（照护场景）
EXPENSE_CATS = [
    ('护工工资', '住家 / 白班 / 夜班护工费用'),
    ('药品', '处方药、非处方药、外用药'),
    ('耗材', '尿垫、纸尿裤、纱布、导管、鼻饲器具'),
    ('营养品', '蛋白粉、肠内营养液、保健品'),
    ('复诊就医', '挂号、检查、住院、救护车'),
    ('康复器材', '助行器、轮椅、气垫床、弹力袜'),
    ('陪护交通', '打车、接送、往返医院'),
    ('餐饮', '病人餐食、送餐'),
    ('其他', '以上之外'),
]
EXPENSE_CAT_TIP = dict(EXPENSE_CATS)
PAY_METHODS = ['微信', '支付宝', '现金', '银行卡', '其他']

# 允许上传的媒体类型（离线白名单）
IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}
VIDEO_EXT = {'mp4', 'webm', 'mov', 'm4v', 'ogg', 'avi'}
MAX_MEDIA_PER_UPLOAD = 20
THUMB_SIZE = (640, 640)

MIME_MAP = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif',
    'webp': 'image/webp', 'bmp': 'image/bmp',
    'mp4': 'video/mp4', 'webm': 'video/webm', 'mov': 'video/quicktime',
    'm4v': 'video/x-m4v', 'ogg': 'video/ogg', 'avi': 'video/x-msvideo',
}


def media_kind(ext):
    ext = (ext or '').lower()
    if ext in IMAGE_EXT:
        return 'image'
    if ext in VIDEO_EXT:
        return 'video'
    return None


def human_size(n):
    n = n or 0
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024.0


def save_media(fs, patient_id):
    """把上传的单个文件落盘，返回可直接入库的字典；不合法返回 None。

    文件名用 uuid，原始名单独存 —— secure_filename 会把中文吃光。
    """
    ext = (fs.filename or '').rsplit('.', 1)[-1].lower() if '.' in (fs.filename or '') else ''
    kind = media_kind(ext)
    if not kind:
        return None
    month = date.today().strftime('%Y%m')
    sub = os.path.join('diary', str(patient_id), month)
    folder = os.path.join(DB.UPLOAD_DIR, sub)
    os.makedirs(folder, exist_ok=True)

    name = uuid.uuid4().hex
    fname = f'{name}.{ext}'
    fpath = os.path.join(folder, fname)
    fs.save(fpath)
    size = os.path.getsize(fpath)

    rel = os.path.join(sub, fname).replace('\\', '/')
    thumb_rel = ''
    if kind == 'image':
        thumb_rel = _make_thumb(fpath, folder, name)
    return {
        'kind': kind,
        'path': rel,
        'thumb': thumb_rel,
        'orig_name': fs.filename,
        'mime': MIME_MAP.get(ext) or mimetypes.guess_type(fname)[0] or 'application/octet-stream',
        'size': size,
    }


def _make_thumb(src, folder, name):
    """给图片生成缩略图，失败就返回空（列表改用原图，不阻塞上传）"""
    try:
        from PIL import Image
    except ImportError:
        return ''
    try:
        im = Image.open(src)
        im = im.convert('RGB') if im.mode in ('P', 'RGBA', 'LA') else im
        im.thumbnail(THUMB_SIZE)
        tp = os.path.join(folder, f'{name}_thumb.jpg')
        im.save(tp, 'JPEG', quality=82, optimize=True)
        rel = os.path.relpath(tp, DB.UPLOAD_DIR).replace('\\', '/')
        return rel
    except Exception:
        return ''


def delete_media_file(conn, mid):
    """删一条媒体：先删磁盘文件，再删库记录"""
    row = conn.execute('SELECT * FROM diary_media WHERE id=?', (mid,)).fetchone()
    if not row:
        return False
    for p in (row['path'], row['thumb']):
        if not p:
            continue
        fp = os.path.join(DB.UPLOAD_DIR, p)
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except OSError:
            pass
    conn.execute('DELETE FROM diary_media WHERE id=?', (mid,))
    return dict(row)


def delete_diary_dir(patient_id, day):
    """日记删掉后，顺手清掉那天该病人的月目录（若已空）"""
    month = (day or '').replace('-', '')[:6]
    folder = os.path.join(DB.UPLOAD_DIR, 'diary', str(patient_id), month)
    try:
        if os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
    except OSError:
        pass


def load_diary_meta(conn, patient_id=None):
    """取某病人（或全部）的日记月份分布，用于筛选下拉"""
    where, args = '', []
    if patient_id:
        where, args = ' WHERE patient_id=?', [patient_id]
    return [dict(r) for r in conn.execute(
        "SELECT substr(day,1,7) m, COUNT(*) c FROM patient_diary" + where +
        " GROUP BY m ORDER BY m DESC", args).fetchall()]


def diary_media_map(conn, ids):
    """批量取媒体，避免 N+1"""
    if not ids:
        return {}
    q = ','.join('?' for _ in ids)
    out = {}
    for r in conn.execute(
            f'SELECT * FROM diary_media WHERE diary_id IN ({q}) ORDER BY id', ids).fetchall():
        out.setdefault(r['diary_id'], []).append(dict(r))
    return out


def expense_summary(conn, pid, day=None):
    """消费统计：本月 / 今年 / 总计 / 分类分布 / 近 12 月走势"""
    day = day or date.today()
    month_s = day.strftime('%Y-%m')
    year_s = day.strftime('%Y')
    total = conn.execute(
        'SELECT IFNULL(SUM(amount),0) s, COUNT(*) c FROM patient_expense WHERE patient_id=?',
        (pid,)).fetchone()
    cur_month = conn.execute(
        "SELECT IFNULL(SUM(amount),0) s FROM patient_expense WHERE patient_id=? AND substr(day,1,7)=?",
        (pid, month_s)).fetchone()['s']
    cur_year = conn.execute(
        "SELECT IFNULL(SUM(amount),0) s FROM patient_expense WHERE patient_id=? AND substr(day,1,4)=?",
        (pid, year_s)).fetchone()['s']
    by_cat = [dict(r) for r in conn.execute(
        'SELECT category, SUM(amount) s, COUNT(*) c FROM patient_expense WHERE patient_id=?'
        ' GROUP BY category ORDER BY s DESC', (pid,)).fetchall()]
    months = []
    for i in range(11, -1, -1):
        y, m = day.year, day.month - i
        while m <= 0:
            m += 12
            y -= 1
        key = f'{y:04d}-{m:02d}'
        months.append({'m': key, 's': 0})
    mrow = {x['m']: x for x in months}
    for r in conn.execute(
            "SELECT substr(day,1,7) m, SUM(amount) s FROM patient_expense WHERE patient_id=?"
            " GROUP BY m", (pid,)).fetchall():
        if r['m'] in mrow:
            mrow[r['m']]['s'] = round(r['s'] or 0, 2)
    return {
        'total': round(total['s'] or 0, 2), 'count': total['c'],
        'month': round(cur_month or 0, 2), 'year': round(cur_year or 0, 2),
        'by_cat': by_cat, 'months': months, 'month_key': month_s,
    }


def apply_status(conn, pid, new_status, note='', at=None):
    """改状态：状态真的变了才写日志，返回 True/False。"""
    row = conn.execute('SELECT status FROM patients WHERE id=?', (pid,)).fetchone()
    if not row:
        return False
    old = row['status'] or care.STATUS_MANAGED
    if new_status == old:
        return False
    at = at or datetime.now().strftime('%Y-%m-%d %H:%M')
    conn.execute(
        'UPDATE patients SET status=?, status_changed_at=?, active=? WHERE id=?',
        (new_status, at, 1 if new_status == care.STATUS_MANAGED else 0, pid))
    conn.execute(
        'INSERT INTO patient_status_log (patient_id, old_status, new_status, note, changed_at)'
        ' VALUES (?,?,?,?,?)',
        (pid, old, new_status, (note or '').strip(), at))
    return True


def load_status_log(conn, pid, limit=30):
    return [dict(r) for r in conn.execute(
        'SELECT * FROM patient_status_log WHERE patient_id=? ORDER BY changed_at DESC, id DESC LIMIT ?',
        (pid, limit)).fetchall()]


# ---------------------------------------------------------------- 初始化
def ensure_init():
    conn = DB.connect()
    DB.init_db(conn)
    seed_knowledge(conn)
    conn.close()


def seed_knowledge(conn):
    """首次运行时把内置照护知识灌入 knowledge 表"""
    n = conn.execute('SELECT COUNT(*) c FROM knowledge').fetchone()['c']
    if n:
        return
    now = date.today().isoformat()
    rows = [(cat, topic, conclusion, source, '', '通用', now)
            for cat, topic, conclusion, source in care.CARE_KNOWLEDGE]
    conn.executemany(
        'INSERT INTO knowledge (category, topic, conclusion, source, url, age_range, fetched_at)'
        ' VALUES (?,?,?,?,?,?,?)', rows)
    conn.commit()


# ---------------------------------------------------------------- 模板全局
@app.context_processor
def inject_globals():
    conn = DB.get_db()
    patients = conn.execute(
        "SELECT * FROM patients WHERE IFNULL(status,'在照护')=? ORDER BY id",
        (care.STATUS_MANAGED,)).fetchall()
    return {
        'all_patients': [dict(p) for p in patients],
        'today': date.today().isoformat(),
        'DISCLAIMER': care.DISCLAIMER,
        'AUTHOR': AUTHOR,
        'APP_NAME': APP_NAME,
        'APP_VERSION': APP_VERSION,
        'APP_SINCE': APP_SINCE,
        'PATIENT_STATUS': PATIENT_STATUS,
        'STATUS_CHIP': STATUS_CHIP,
        'STATUS_TIP': STATUS_TIP,
        'CARE_LEVELS': CARE_LEVELS,
        'LEVEL_TIP': LEVEL_TIP,
        'EVENT_LABEL': care.EVENT_LABEL,
        'EVENT_TYPES': care.EVENT_TYPES,
        'DIARY_MOODS': DIARY_MOODS,
        'DIARY_MOOD_EMOJI': DIARY_MOOD_EMOJI,
        'EXPENSE_CATS': EXPENSE_CATS,
        'EXPENSE_CAT_TIP': EXPENSE_CAT_TIP,
        'PAY_METHODS': PAY_METHODS,
        'VITAL_DEFS': care.VITAL_DEFS,
        'VITAL_OK_TIP': care.VITAL_OK_TIP,
        'human_size': human_size,
        'pstatus': lambda p: (p.get('status') if hasattr(p, 'get') else p['status']) or care.STATUS_MANAGED,
    }


# ---------------------------------------------------------------- 首页
@app.route('/')
def index():
    conn = DB.get_db()
    patients = [dict(p) for p in conn.execute(
        "SELECT * FROM patients WHERE IFNULL(status,'在照护')=? ORDER BY id",
        (care.STATUS_MANAGED,)).fetchall()]
    others = [dict(p) for p in conn.execute(
        "SELECT * FROM patients WHERE IFNULL(status,'在照护')<>? ORDER BY status_changed_at DESC, id",
        (care.STATUS_MANAGED,)).fetchall()]

    cards = []
    for p in patients:
        timeline, hit, total = care.today_timeline(conn, p, date.today().isoformat())
        alerts = care.alerts_for(conn, p)
        cards.append({
            'patient': p,
            'age': care.age_text(p['birth_year']),
            'level': p['care_level'] or '全协助',
            'hit': hit, 'total': total,
            'pct': round(hit / total * 100) if total else 0,
            'alerts': alerts,
            'danger': sum(1 for a in alerts if a['level'] == 'danger'),
            'warn': sum(1 for a in alerts if a['level'] == 'warn'),
        })

    global_alerts = []
    for c in cards:
        for a in c['alerts']:
            global_alerts.append({'patient': c['patient']['name'],
                                  'patient_id': c['patient']['id'], **a})
    global_alerts.sort(key=lambda x: 0 if x['level'] == 'danger' else 1)

    return render_template('index.html', cards=cards, alerts=global_alerts, others=others)


# ---------------------------------------------------------------- 档案
@app.route('/patients')
def patients():
    conn = DB.get_db()
    sel = (request.args.get('status') or '').strip()
    sql = 'SELECT * FROM patients'
    args = []
    if sel in PATIENT_STATUS:
        sql += " WHERE IFNULL(status,'在照护')=?"
        args.append(sel)
    sql += " ORDER BY (IFNULL(status,'在照护')=?) DESC, status_changed_at DESC, id"
    args.append(care.STATUS_MANAGED)

    counts = {s: 0 for s in PATIENT_STATUS}
    for r in conn.execute(
            "SELECT IFNULL(status,'在照护') s, COUNT(*) c FROM patients GROUP BY s").fetchall():
        counts[r['s']] = counts.get(r['s'], 0) + r['c']

    log_map = {}
    for r in conn.execute(
            'SELECT patient_id, old_status, new_status, note, changed_at FROM patient_status_log'
            ' WHERE id IN (SELECT MAX(id) FROM patient_status_log GROUP BY patient_id)').fetchall():
        log_map[r['patient_id']] = dict(r)

    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        d['age'] = care.age_text(d['birth_year'])
        d['status'] = d.get('status') or care.STATUS_MANAGED
        d['last_log'] = log_map.get(d['id'])
        out.append(d)
    return render_template('patients.html', patients=out, sel=sel, counts=counts,
                           total=sum(counts.values()))


@app.route('/patients/new', methods=['GET', 'POST'])
def patient_new():
    if request.method == 'POST':
        return save_patient(None)
    return render_template('patient_form.html', patient=None)


@app.route('/patients/<int:pid>/edit', methods=['GET', 'POST'])
def patient_edit(pid):
    conn = DB.get_db()
    row = conn.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    if not row:
        flash('病人不存在', 'danger')
        return redirect(url_for('patients'))
    if request.method == 'POST':
        return save_patient(pid)
    return render_template('patient_form.html', patient=dict(row))


PATIENT_FIELDS = ['name', 'sex', 'care_level', 'diagnosis', 'condition_desc', 'allergies',
                  'doctor', 'doctor_phone', 'hospital', 'contact_name', 'contact_phone',
                  'contact_relation', 'weight_current', 'start_date', 'note']


def save_patient(pid):
    conn = DB.get_db()
    f = request.form
    vals = {}
    for k in PATIENT_FIELDS:
        v = (f.get(k) or '').strip()
        if k == 'weight_current':
            vals[k] = float(v) if v else None
        else:
            vals[k] = v or None
    if not vals.get('name'):
        flash('姓名必填', 'danger')
        return redirect(request.url)
    if f.get('birth_year'):
        try:
            by = int(f['birth_year'])
            if 1900 <= by <= date.today().year:
                vals['birth_year'] = by
        except ValueError:
            pass

    if vals.get('weight_current'):
        vals['weight_updated_at'] = date.today().isoformat()

    new_status = (f.get('status') or '').strip()
    if new_status not in PATIENT_STATUS:
        new_status = care.STATUS_MANAGED
    status_note = (f.get('status_note') or '').strip()

    if pid:
        sets = ', '.join(f'{k}=?' for k in vals)
        conn.execute(f'UPDATE patients SET {sets} WHERE id=?',
                     list(vals.values()) + [pid])
        if apply_status(conn, pid, new_status, status_note):
            flash(f'档案已保存，状态已改为「{new_status}」', 'success')
        else:
            flash('档案已保存', 'success')
    else:
        vals['created_at'] = datetime.now().isoformat(timespec='seconds')
        vals['status'] = new_status
        vals['status_changed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        vals['active'] = 1 if new_status == care.STATUS_MANAGED else 0
        cols = ', '.join(vals)
        ph = ', '.join('?' for _ in vals)
        cur = conn.execute(f'INSERT INTO patients ({cols}) VALUES ({ph})',
                           list(vals.values()))
        pid = cur.lastrowid
        if new_status != care.STATUS_MANAGED:
            conn.execute(
                'INSERT INTO patient_status_log (patient_id, old_status, new_status, note, changed_at)'
                ' VALUES (?,?,?,?,?)',
                (pid, '（建档）', new_status, status_note,
                 datetime.now().strftime('%Y-%m-%d %H:%M')))
        if vals.get('weight_current'):
            conn.execute(
                'INSERT INTO care_events (patient_id, day, time, type, payload, created_at)'
                ' VALUES (?,?,?,?,?,?)',
                (pid, date.today().isoformat(), datetime.now().strftime('%H:%M'),
                 'weight', json.dumps({'kg': vals['weight_current']}, ensure_ascii=False),
                 datetime.now().isoformat(timespec='seconds')))
        flash('档案已保存，可以开始排照护任务了', 'success')
    conn.commit()
    return redirect(url_for('patient_today', pid=pid))


@app.route('/api/patient/status', methods=['POST'])
def api_patient_status():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        pid = int(j.get('patient_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 patient_id'}), 400
    if not conn.execute('SELECT 1 FROM patients WHERE id=?', (pid,)).fetchone():
        return jsonify({'ok': False, 'error': '病人不存在'}), 404
    st = (j.get('status') or '').strip()
    if st not in PATIENT_STATUS:
        return jsonify({'ok': False, 'error': '状态不合法'}), 400
    changed = apply_status(conn, pid, st, (j.get('note') or '').strip())
    conn.commit()
    d = conn.execute('SELECT status, status_changed_at FROM patients WHERE id=?',
                     (pid,)).fetchone()
    return jsonify({'ok': True, 'changed': changed, 'status': d['status'],
                    'changed_at': d['status_changed_at']})


# ---------------------------------------------------------------- 照护工作台
def load_patient(pid):
    conn = DB.get_db()
    row = conn.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    return conn, (dict(row) if row else None)


@app.route('/patient/<int:pid>')
def patient_home(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    return redirect(url_for('patient_today', pid=pid))


@app.route('/patient/<int:pid>/today')
def patient_today(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    day = request.args.get('day') or date.today().isoformat()
    d = care.parse_date(day) or date.today()
    timeline, hit, total = care.today_timeline(conn, patient, day)
    evs = list(reversed(care.events_of(conn, pid, day)))
    alerts = care.alerts_for(conn, patient)
    meds = conn.execute(
        'SELECT * FROM med_schedule WHERE patient_id=? AND active=1 ORDER BY id',
        (pid,)).fetchall()
    return render_template(
        'patient_today.html', patient=patient, day=day, timeline=timeline,
        hit=hit, total=total, events=evs, alerts=alerts,
        level=patient['care_level'] or '全协助',
        level_tip=care.LEVEL_TIP.get(patient['care_level'] or '全协助', ''),
        age=care.age_text(patient['birth_year'], d),
        bed_days=care.bed_days(patient['start_date'], d),
        meds=[dict(m) for m in meds],
        is_today=(day == date.today().isoformat()))


# ---------------------------------------------------------------- 打卡 API
def _resync_weight(conn, pid):
    """以最新一条体重为准回写 patients 表（care_events.weight 与 vitals.weight 都算）"""
    v = conn.execute(
        'SELECT day, weight FROM vitals WHERE patient_id=? AND weight IS NOT NULL'
        ' ORDER BY day DESC, time DESC, id DESC LIMIT 1', (pid,)).fetchone()
    e = conn.execute(
        "SELECT day, payload FROM care_events WHERE patient_id=? AND type='weight'"
        ' AND payload IS NOT NULL ORDER BY day DESC, time DESC LIMIT 1', (pid,)).fetchone()

    kg, day = None, None
    def _of(row):
        if not row:
            return None, None
        try:
            k = (json.loads(row['payload']) or {}).get('kg') if 'payload' in row.keys() else row['weight']
        except (ValueError, TypeError):
            k = None
        return k, row['day']
    k2, d2 = _of(v)
    k1, d1 = _of(e)
    for k, d in ((k2, d2), (k1, d1)):
        if k:
            kg, day = k, d
            break
    conn.execute('UPDATE patients SET weight_current=?, weight_updated_at=? WHERE id=?',
                 (kg, day, pid))


@app.route('/api/checkin', methods=['POST'])
def api_checkin():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        pid = int(j.get('patient_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 patient_id'}), 400
    typ = j.get('type')
    time_s = j.get('time') or datetime.now().strftime('%H:%M')
    day = j.get('day') or date.today().isoformat()
    data = j.get('data') or {}
    if isinstance(data, str):
        data = json.loads(data)
    note = j.get('note') or ''
    by = (j.get('by') or '').strip() or None

    conn.execute(
        'INSERT INTO care_events (patient_id, day, time, type, payload, note, by, created_at)'
        ' VALUES (?,?,?,?,?,?,?,?)',
        (pid, day, time_s, typ, json.dumps(data, ensure_ascii=False), note, by,
         datetime.now().isoformat(timespec='seconds')))
    if typ == 'weight':
        _resync_weight(conn, pid)
    conn.commit()

    patient = dict(conn.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone())
    alerts = care.alerts_for(conn, patient)
    maybe_notify(patient, alerts)
    return jsonify({'ok': True, 'alerts': alerts})


@app.route('/api/event/update', methods=['POST'])
def api_event_update():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        eid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT * FROM care_events WHERE id=?', (eid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '记录不存在'}), 404

    typ = j.get('type') or row['type']
    day = j.get('day') or row['day']
    time_s = j.get('time') or row['time']
    note = row['note'] if j.get('note') is None else j.get('note')
    by = row['by'] if j.get('by') is None else (j.get('by') or None)

    data = j.get('data')
    if data is None:
        payload = row['payload']
    else:
        if isinstance(data, str):
            data = json.loads(data)
        payload = json.dumps(data, ensure_ascii=False)

    conn.execute(
        'UPDATE care_events SET day=?, time=?, type=?, payload=?, note=?, by=? WHERE id=?',
        (day, time_s, typ, payload, note, by, eid))
    if typ == 'weight' or row['type'] == 'weight':
        _resync_weight(conn, row['patient_id'])
    conn.commit()
    return jsonify({'ok': True})


@app.route('/api/event/delete', methods=['POST'])
def api_event_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        eid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT patient_id, type FROM care_events WHERE id=?',
                       (eid,)).fetchone()
    conn.execute('DELETE FROM care_events WHERE id=?', (eid,))
    if row and row['type'] == 'weight':
        _resync_weight(conn, row['patient_id'])
    conn.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 用药管理
@app.route('/patient/<int:pid>/meds')
def patient_meds(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    day = date.today().isoformat()
    timeline, hit, total = care.today_timeline(conn, patient, day)
    sched = [dict(m) for m in conn.execute(
        'SELECT * FROM med_schedule WHERE patient_id=? ORDER BY active DESC, id',
        (pid,)).fetchall()]
    today_meds = [t for t in timeline if t['type'] == 'med']
    logs = [e for e in care.events_of(conn, pid) if e['type'] == 'med'][:60]
    return render_template('patient_meds.html', patient=patient, sched=sched,
                           today_meds=today_meds, logs=logs, day=day,
                           hit=sum(1 for t in today_meds if t['done']),
                           total=len(today_meds),
                           alerts=care.alerts_for(conn, patient))


def _sched_vals(j):
    name = (j.get('med_name') or '').strip()
    if not name:
        return None, '药名必填'
    times_raw = (j.get('times') or '').strip()
    times = [t.strip() for t in times_raw.replace('，', ',').split(',') if t.strip()]
    times = sorted(set(times))
    if not times:
        return None, '至少填一个服药时间点'
    for t in times:
        parts = t.split(':')
        ok = (len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit()
              and int(parts[0]) <= 23 and int(parts[1]) <= 59)
        if not ok:
            return None, f'时间格式不对：{t}（用 08:00 这种）'
    return {
        'med_name': name,
        'dose': (j.get('dose') or '').strip() or None,
        'form': (j.get('form') or '').strip() or None,
        'times': ','.join(times),
        'usage_txt': (j.get('usage_txt') or '').strip() or None,
        'purpose': (j.get('purpose') or '').strip() or None,
        'note': (j.get('note') or '').strip() or None,
    }, None


@app.route('/api/med/schedule', methods=['POST'])
def api_med_schedule():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        pid = int(j.get('patient_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 patient_id'}), 400
    if not conn.execute('SELECT 1 FROM patients WHERE id=?', (pid,)).fetchone():
        return jsonify({'ok': False, 'error': '病人不存在'}), 404
    v, err = _sched_vals(j)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    conn.execute(
        'INSERT INTO med_schedule (patient_id, med_name, dose, form, times, usage_txt,'
        ' purpose, note, active, created_at) VALUES (?,?,?,?,?,?,?,?,1,?)',
        (pid, v['med_name'], v['dose'], v['form'], v['times'], v['usage_txt'],
         v['purpose'], v['note'], datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    return jsonify({'ok': True})


@app.route('/api/med/schedule/update', methods=['POST'])
def api_med_schedule_update():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        sid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 id'}), 400
    row = conn.execute('SELECT * FROM med_schedule WHERE id=?', (sid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '不存在'}), 404
    v, err = _sched_vals(j)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    conn.execute(
        'UPDATE med_schedule SET med_name=?, dose=?, form=?, times=?, usage_txt=?,'
        ' purpose=?, note=? WHERE id=?',
        (v['med_name'], v['dose'], v['form'], v['times'], v['usage_txt'],
         v['purpose'], v['note'], sid))
    conn.commit()
    return jsonify({'ok': True})


@app.route('/api/med/schedule/toggle', methods=['POST'])
def api_med_schedule_toggle():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        sid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 id'}), 400
    row = conn.execute('SELECT active FROM med_schedule WHERE id=?', (sid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '不存在'}), 404
    conn.execute('UPDATE med_schedule SET active=? WHERE id=?', (0 if row['active'] else 1, sid))
    conn.commit()
    return jsonify({'ok': True, 'active': 0 if row['active'] else 1})


@app.route('/api/med/schedule/delete', methods=['POST'])
def api_med_schedule_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        sid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 id'}), 400
    conn.execute('DELETE FROM med_schedule WHERE id=?', (sid,))
    conn.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 体征记录
@app.route('/patient/<int:pid>/vitals')
def patient_vitals(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    rows = [dict(r) for r in conn.execute(
        'SELECT * FROM vitals WHERE patient_id=? ORDER BY day DESC, time DESC, id DESC LIMIT 200',
        (pid,)).fetchall()]
    for r in rows:
        r['marks'] = [(key, label, unit, care.judge_vital(key, r[key]))
                      for key, label, unit, lo, hi, ph in care.VITAL_DEFS
                      if r[key] is not None]

    # 图表数据：近 30 天，血压 / 体温 / 血氧
    chart_rows = [dict(r) for r in conn.execute(
        'SELECT * FROM vitals WHERE patient_id=? AND day>=? ORDER BY day, time, id',
        (pid, (date.today() - timedelta(days=29)).isoformat())).fetchall()]
    def series(keys):
        out = []
        for r in chart_rows:
            for k in keys:
                if r.get(k) is not None:
                    label = f'{r["day"]} {r["time"] or ""}'.strip()
                    out.append({'t': label, 'v': r[k], 'k': k})
                    break
        return out
    bp = [[f'{r["day"]} {r["time"] or ""}'.strip(), r['bp_high'], r['bp_low']]
          for r in chart_rows if r.get('bp_high') is not None or r.get('bp_low') is not None]
    temps = [[f'{r["day"]} {r["time"] or ""}'.strip(), r['temp']]
             for r in chart_rows if r.get('temp') is not None]
    spo2s = [[f'{r["day"]} {r["time"] or ""}'.strip(), r['spo2']]
             for r in chart_rows if r.get('spo2') is not None]

    latest = conn.execute(
        'SELECT * FROM vitals WHERE patient_id=?'
        " ORDER BY day DESC, IFNULL(time,'99:99') DESC, id DESC LIMIT 1",
        (pid,)).fetchone()
    return render_template(
        'patient_vitals.html', patient=patient, rows=rows, latest=latest,
        bp_json=json.dumps(bp, ensure_ascii=False),
        temp_json=json.dumps(temps, ensure_ascii=False),
        spo2_json=json.dumps(spo2s, ensure_ascii=False),
        judge=care.judge_vital, VITAL_DEFS=care.VITAL_DEFS,
        alerts=care.alerts_for(conn, patient))


def _vitals_vals(j):
    day = (j.get('day') or date.today().isoformat()).strip()
    if not care.parse_date(day):
        return None, '日期格式不对'
    vals = {'day': day, 'time': (j.get('time') or '').strip() or None,
            'note': (j.get('note') or '').strip() or None}
    for key, _label, _unit, lo, hi, _ph in care.VITAL_DEFS:
        raw = j.get(key)
        if raw in (None, ''):
            vals[key] = None
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None, f'{_label}要填数字'
        if not (lo <= v <= hi):
            return None, f'{_label}超出合理范围（{lo}-{hi}），检查一下是不是填错了'
        vals[key] = v
    if all(vals.get(k) is None for k, *_ in care.VITAL_DEFS):
        return None, '至少填一项体征'
    return vals, None


@app.route('/api/vitals', methods=['POST'])
def api_vitals_add():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        pid = int(j.get('patient_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 patient_id'}), 400
    if not conn.execute('SELECT 1 FROM patients WHERE id=?', (pid,)).fetchone():
        return jsonify({'ok': False, 'error': '病人不存在'}), 404
    v, err = _vitals_vals(j)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    conn.execute(
        'INSERT INTO vitals (patient_id, day, time, bp_high, bp_low, hr, temp, spo2,'
        ' sugar, weight, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (pid, v['day'], v['time'], v['bp_high'], v['bp_low'], v['hr'], v['temp'],
         v['spo2'], v['sugar'], v['weight'], v['note'],
         datetime.now().isoformat(timespec='seconds')))
    if v['weight']:
        _resync_weight(conn, pid)
    conn.commit()
    patient = dict(conn.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone())
    alerts = care.alerts_for(conn, patient)
    maybe_notify(patient, alerts)
    return jsonify({'ok': True, 'alerts': alerts})


@app.route('/api/vitals/delete', methods=['POST'])
def api_vitals_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        vid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 id'}), 400
    row = conn.execute('SELECT patient_id FROM vitals WHERE id=?', (vid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '不存在'}), 404
    conn.execute('DELETE FROM vitals WHERE id=?', (vid,))
    conn.commit()
    _resync_weight(conn, row['patient_id'])
    conn.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 康复训练
@app.route('/patient/<int:pid>/rehab')
def patient_rehab(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    evs = [e for e in care.events_of(conn, pid) if e['type'] == 'rehab']
    by_proj = {}
    for e in evs:
        p = e['data'].get('project') or '未命名'
        g = by_proj.setdefault(p, [0, 0, 0])
        g[0] += e['data'].get('success', 0)
        g[1] += e['data'].get('total', 0)
        g[2] += 1
    proj_rows = [{'name': k, 'rate': round(v[0] / v[1] * 100) if v[1] else 0,
                  'sessions': v[2], 'success': v[0], 'total': v[1]}
                 for k, v in by_proj.items()]
    proj_rows.sort(key=lambda x: x['name'])
    stats = care.range_stats(conn, patient, 14)
    return render_template(
        'patient_rehab.html', patient=patient, stats=stats,
        logs=sorted(evs, key=lambda x: (x['day'], x['time'] or ''), reverse=True)[:60],
        proj_rows=proj_rows, projects=care.REHAB_PROJECTS,
        alerts=care.alerts_for(conn, patient))


# ---------------------------------------------------------------- 照护记录
@app.route('/patient/<int:pid>/records')
def patient_records(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    typ = (request.args.get('type') or '').strip()
    d1 = (request.args.get('from') or '').strip()
    d2 = (request.args.get('to') or '').strip()
    kw = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except ValueError:
        page = 1
    per = 50

    counts = {t: 0 for t, _ in care.EVENT_TYPES}
    for r in conn.execute(
            'SELECT type, COUNT(*) c FROM care_events WHERE patient_id=? GROUP BY type',
            (pid,)).fetchall():
        counts[r['type']] = r['c']

    where = ' WHERE patient_id=?'
    args = [pid]
    if typ:
        where += ' AND type=?'
        args.append(typ)
    if d1:
        where += ' AND day>=?'
        args.append(d1)
    if d2:
        where += ' AND day<=?'
        args.append(d2)
    if kw:
        where += ' AND (IFNULL(note,"") LIKE ? OR IFNULL(payload,"") LIKE ? OR IFNULL(by,"") LIKE ?)'
        args += [f'%{kw}%'] * 3

    matched = conn.execute('SELECT COUNT(*) c FROM care_events' + where, args).fetchone()['c']
    pages = max(1, (matched + per - 1) // per)
    page = min(page, pages)

    rows = conn.execute(
        'SELECT * FROM care_events' + where +
        ' ORDER BY day DESC, time DESC, id DESC LIMIT ? OFFSET ?',
        args + [per, (page - 1) * per]).fetchall()
    events = []
    for r in rows:
        d = dict(r)
        try:
            d['data'] = json.loads(d['payload']) if d['payload'] else {}
        except (ValueError, TypeError):
            d['data'] = {}
        events.append(d)

    return render_template(
        'patient_records.html', patient=patient, events=events, counts=counts,
        total=sum(counts.values()), matched=matched,
        typ=typ, d1=d1, d2=d2, kw=kw, page=page, pages=pages,
        alerts=care.alerts_for(conn, patient))


# ---------------------------------------------------------------- 照护日记
DIARY_PER = 20


@app.route('/patient/<int:pid>/diary')
def patient_diary(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    mon = (request.args.get('month') or '').strip()
    kw = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except ValueError:
        page = 1

    where, args = ' WHERE patient_id=?', [pid]
    if mon:
        where += " AND substr(day,1,7)=?"
        args.append(mon)
    if kw:
        where += ' AND (IFNULL(title,"") LIKE ? OR IFNULL(content,"") LIKE ?' \
                 ' OR IFNULL(place,"") LIKE ?)'
        args += [f'%{kw}%'] * 3

    matched = conn.execute('SELECT COUNT(*) c FROM patient_diary' + where, args).fetchone()['c']
    pages = max(1, (matched + DIARY_PER - 1) // DIARY_PER)
    page = min(page, max(1, pages))
    rows = conn.execute(
        'SELECT * FROM patient_diary' + where +
        ' ORDER BY day DESC, id DESC LIMIT ? OFFSET ?',
        args + [DIARY_PER, (page - 1) * DIARY_PER]).fetchall()
    entries = [dict(r) for r in rows]
    mm = diary_media_map(conn, [e['id'] for e in entries])
    for e in entries:
        e['media'] = mm.get(e['id'], [])

    stats = conn.execute('SELECT COUNT(*) c FROM patient_diary WHERE patient_id=?',
                         (pid,)).fetchone()['c']
    media_n = conn.execute(
        'SELECT COUNT(*) c, SUM(kind="image") i, SUM(kind="video") v'
        ' FROM diary_media WHERE patient_id=?', (pid,)).fetchone()
    return render_template(
        'patient_diary.html', patient=patient, entries=entries, matched=matched,
        page=page, pages=pages, mon=mon, kw=kw,
        months=load_diary_meta(conn, pid), stats=stats,
        img_n=media_n['i'] or 0, vid_n=media_n['v'] or 0,
        alerts=care.alerts_for(conn, patient))


@app.route('/patient/<int:pid>/diary/new', methods=['POST'])
def diary_new(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    f = request.form
    day = (f.get('day') or date.today().isoformat()).strip()
    title = (f.get('title') or '').strip()
    content = (f.get('content') or '').strip()
    files = [x for x in request.files.getlist('files') if x and x.filename]
    if not title and not content and not files:
        flash('至少写点什么，或者传张照片', 'danger')
        return redirect(url_for('patient_diary', pid=pid))

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    cur = conn.execute(
        'INSERT INTO patient_diary (patient_id, day, title, mood, place, content,'
        ' created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)',
        (pid, day, title or None, (f.get('mood') or '').strip() or None,
         (f.get('place') or '').strip() or None, content or None, now, now))
    eid = cur.lastrowid

    saved = skipped = 0
    for fs in files[:MAX_MEDIA_PER_UPLOAD]:
        info = save_media(fs, pid)
        if not info:
            skipped += 1
            continue
        conn.execute(
            'INSERT INTO diary_media (diary_id, patient_id, kind, path, thumb, orig_name,'
            ' mime, size, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (eid, pid, info['kind'], info['path'], info['thumb'], info['orig_name'],
             info['mime'], info['size'], now))
        saved += 1
    conn.commit()

    msg = '日记已保存'
    if saved:
        msg += f'，附 {saved} 个文件'
    if skipped:
        msg += f'（{skipped} 个格式不支持已跳过）'
    flash(msg, 'success')
    return redirect(url_for('patient_diary', pid=pid, month=day[:7]))


@app.route('/api/diary/update', methods=['POST'])
def api_diary_update():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        eid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少日记 id'}), 400
    row = conn.execute('SELECT id FROM patient_diary WHERE id=?', (eid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '日记不存在'}), 404
    conn.execute(
        'UPDATE patient_diary SET day=?, title=?, mood=?, place=?, content=?, updated_at=?'
        ' WHERE id=?',
        ((j.get('day') or date.today().isoformat()).strip(),
         (j.get('title') or '').strip() or None,
         (j.get('mood') or '').strip() or None,
         (j.get('place') or '').strip() or None,
         (j.get('content') or '').strip() or None,
         datetime.now().strftime('%Y-%m-%d %H:%M'), eid))
    conn.commit()
    return jsonify({'ok': True})


@app.route('/patient/<int:pid>/diary/<int:eid>/delete', methods=['POST'])
def diary_delete(pid, eid):
    conn = DB.get_db()
    row = conn.execute('SELECT * FROM patient_diary WHERE id=? AND patient_id=?',
                       (eid, pid)).fetchone()
    if row:
        for m in conn.execute('SELECT id FROM diary_media WHERE diary_id=?',
                              (eid,)).fetchall():
            delete_media_file(conn, m['id'])
        conn.execute('DELETE FROM patient_diary WHERE id=?', (eid,))
        delete_diary_dir(pid, row['day'])
        conn.commit()
        flash('日记已删除', 'success')
    else:
        flash('日记不存在', 'danger')
    return redirect(url_for('patient_diary', pid=pid))


@app.route('/api/diary/media/delete', methods=['POST'])
def api_diary_media_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        mid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少媒体 id'}), 400
    got = delete_media_file(conn, mid)
    if not got:
        return jsonify({'ok': False, 'error': '媒体不存在'}), 404
    conn.commit()
    return jsonify({'ok': True})


@app.route('/media/<path:relpath>')
def media_file(relpath):
    return send_from_directory(DB.UPLOAD_DIR, relpath)


@app.errorhandler(413)
def too_large(e):
    flash('上传太大（单次请求上限 300MB），请压缩视频或分批上传', 'danger')
    return redirect(request.referrer or url_for('index')), 303


# ---------------------------------------------------------------- 记账
EXPENSE_PER = 30


@app.route('/patient/<int:pid>/expense')
def patient_expense(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    cat = (request.args.get('category') or '').strip()
    d1 = (request.args.get('from') or '').strip()
    d2 = (request.args.get('to') or '').strip()
    kw = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except ValueError:
        page = 1

    where, args = ' WHERE patient_id=?', [pid]
    if cat:
        where += ' AND category=?'
        args.append(cat)
    if d1:
        where += ' AND day>=?'
        args.append(d1)
    if d2:
        where += ' AND day<=?'
        args.append(d2)
    if kw:
        where += ' AND (IFNULL(item,"") LIKE ? OR IFNULL(shop,"") LIKE ?' \
                 ' OR IFNULL(note,"") LIKE ?)'
        args += [f'%{kw}%'] * 3

    matched = conn.execute('SELECT COUNT(*) c FROM patient_expense' + where, args).fetchone()['c']
    pages = max(1, (matched + EXPENSE_PER - 1) // EXPENSE_PER)
    page = min(page, max(1, pages))
    rows = conn.execute(
        'SELECT * FROM patient_expense' + where +
        ' ORDER BY day DESC, id DESC LIMIT ? OFFSET ?',
        args + [EXPENSE_PER, (page - 1) * EXPENSE_PER]).fetchall()
    fsum = conn.execute(
        'SELECT IFNULL(SUM(amount),0) s FROM patient_expense' + where, args).fetchone()['s']

    return render_template(
        'patient_expense.html', patient=patient, rows=[dict(r) for r in rows],
        matched=matched, page=page, pages=pages,
        cat=cat, d1=d1, d2=d2, kw=kw, fsum=round(fsum or 0, 2),
        summary=expense_summary(conn, pid),
        alerts=care.alerts_for(conn, patient))


def _expense_vals(j):
    day = (j.get('day') or date.today().isoformat()).strip()
    if not care.parse_date(day):
        return None, '日期格式不对（用 2026-10-24 这种）'
    cat = (j.get('category') or '').strip()
    if cat not in EXPENSE_CAT_TIP:
        return None, '请选择消费分类'
    try:
        amount = round(float(j.get('amount')), 2)
    except (TypeError, ValueError):
        return None, '金额要填数字'
    if amount <= 0:
        return None, '金额要大于 0'

    def fnum(k):
        v = j.get(k)
        if v in (None, ''):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        'day': day, 'category': cat,
        'item': (j.get('item') or '').strip() or None,
        'amount': amount, 'qty': fnum('qty'),
        'unit': (j.get('unit') or '').strip() or None,
        'shop': (j.get('shop') or '').strip() or None,
        'pay_method': (j.get('pay_method') or '').strip() or None,
        'note': (j.get('note') or '').strip() or None,
    }, None


def _expense_patient_id(conn, j):
    try:
        pid = int(j.get('patient_id'))
    except (TypeError, ValueError):
        return None
    if not conn.execute('SELECT 1 FROM patients WHERE id=?', (pid,)).fetchone():
        return None
    return pid


@app.route('/api/expense', methods=['POST'])
def api_expense_add():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    pid = _expense_patient_id(conn, j)
    if pid is None:
        return jsonify({'ok': False, 'error': '病人不存在'}), 404
    v, err = _expense_vals(j)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    conn.execute(
        'INSERT INTO patient_expense (patient_id, day, category, item, amount, qty, unit,'
        ' shop, pay_method, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (pid, v['day'], v['category'], v['item'], v['amount'], v['qty'], v['unit'],
         v['shop'], v['pay_method'], v['note'],
         datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    return jsonify({'ok': True, 'summary': expense_summary(conn, pid)})


@app.route('/api/expense/update', methods=['POST'])
def api_expense_update():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        rid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT patient_id FROM patient_expense WHERE id=?',
                       (rid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '记录不存在'}), 404
    v, err = _expense_vals(j)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    conn.execute(
        'UPDATE patient_expense SET day=?, category=?, item=?, amount=?, qty=?, unit=?,'
        ' shop=?, pay_method=?, note=? WHERE id=?',
        (v['day'], v['category'], v['item'], v['amount'], v['qty'], v['unit'],
         v['shop'], v['pay_method'], v['note'], rid))
    conn.commit()
    return jsonify({'ok': True, 'summary': expense_summary(conn, row['patient_id'])})


@app.route('/api/expense/delete', methods=['POST'])
def api_expense_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        rid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT patient_id FROM patient_expense WHERE id=?',
                       (rid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '记录不存在'}), 404
    conn.execute('DELETE FROM patient_expense WHERE id=?', (rid,))
    conn.commit()
    return jsonify({'ok': True, 'summary': expense_summary(conn, row['patient_id'])})


@app.route('/patient/<int:pid>/expense.csv')
def patient_expense_csv(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    rows = conn.execute(
        'SELECT * FROM patient_expense WHERE patient_id=? ORDER BY day, id',
        (pid,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['日期', '分类', '项目', '金额', '数量', '单位', '商家/单位', '支付方式', '备注'])
    total = 0.0
    for r in rows:
        total += r['amount'] or 0
        w.writerow([r['day'], r['category'], r['item'] or '', f'{r["amount"]:.2f}',
                    r['qty'] if r['qty'] is not None else '', r['unit'] or '',
                    r['shop'] or '', r['pay_method'] or '', r['note'] or ''])
    w.writerow([])
    w.writerow(['合计', '', '', f'{total:.2f}', '', '', '', '', f'{len(rows)} 笔'])
    data = '\ufeff' + buf.getvalue()
    fn = f'{patient["name"]}_照护费用_{date.today().isoformat()}.csv'
    disp = ("attachment; filename=expense.csv; filename*=UTF-8''"
            + quote(fn, safe=''))
    return Response(data, mimetype='text/csv', headers={'Content-Disposition': disp})


# ---------------------------------------------------------------- 医疗档案
@app.route('/patient/<int:pid>/medical')
def patient_medical(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    rows = [dict(r) for r in conn.execute(
        'SELECT * FROM medical_records WHERE patient_id=? ORDER BY happen_date DESC',
        (pid,)).fetchall()]
    return render_template('patient_medical.html', patient=patient, rows=rows,
                           checklist=care.visit_checklist(conn, patient),
                           alerts=care.alerts_for(conn, patient))


MED_KINDS = ['门诊', '住院', '检查', '手术', '复诊']


@app.route('/api/medical_record', methods=['POST'])
def api_medical_record():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        pid = int(j.get('patient_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 patient_id'}), 400
    if not conn.execute('SELECT 1 FROM patients WHERE id=?', (pid,)).fetchone():
        return jsonify({'ok': False, 'error': '病人不存在'}), 404
    kind = (j.get('kind') or '门诊').strip()
    if kind not in MED_KINDS:
        kind = '门诊'
    conn.execute(
        'INSERT INTO medical_records (patient_id, kind, happen_date, next_due, hospital,'
        ' doctor, summary, note, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
        (pid, kind, (j.get('happen_date') or date.today().isoformat()).strip(),
         (j.get('next_due') or '').strip() or None,
         (j.get('hospital') or '').strip() or None,
         (j.get('doctor') or '').strip() or None,
         (j.get('summary') or '').strip() or None,
         (j.get('note') or '').strip() or None,
         datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    return jsonify({'ok': True})


@app.route('/api/medical_record/update', methods=['POST'])
def api_medical_record_update():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        rid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT id FROM medical_records WHERE id=?', (rid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '记录不存在'}), 404
    kind = (j.get('kind') or '门诊').strip()
    if kind not in MED_KINDS:
        kind = '门诊'
    conn.execute(
        'UPDATE medical_records SET kind=?, happen_date=?, next_due=?, hospital=?,'
        ' doctor=?, summary=?, note=? WHERE id=?',
        (kind, (j.get('happen_date') or '').strip() or None,
         (j.get('next_due') or '').strip() or None,
         (j.get('hospital') or '').strip() or None,
         (j.get('doctor') or '').strip() or None,
         (j.get('summary') or '').strip() or None,
         (j.get('note') or '').strip() or None, rid))
    conn.commit()
    return jsonify({'ok': True})


@app.route('/api/medical_record/delete', methods=['POST'])
def api_medical_record_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        rid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    conn.execute('DELETE FROM medical_records WHERE id=?', (rid,))
    conn.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------- 周报
@app.route('/patient/<int:pid>/weekly')
def patient_weekly(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    days = int(request.args.get('days', 7))
    days = days if days in (7, 14, 30) else 7
    stats = care.range_stats(conn, patient, days)
    v, vd = care.verdict(stats)
    report = care.weekly_report(conn, patient, days)
    return render_template(
        'patient_weekly.html', patient=patient, stats=stats, verdict=v,
        verdict_desc=vd, tips=care.next_week_plan(stats),
        report=report, cur_days=days,
        stats_json=json.dumps(
            {'days': [d['day'] for d in stats['daily']],
             'pct': [d['pct'] for d in stats['daily']],
             'ml': [d['ml'] for d in stats['daily']]}, ensure_ascii=False),
        alerts=care.alerts_for(conn, patient))


@app.route('/patient/<int:pid>/weekly.txt')
def patient_weekly_txt(pid):
    """纯文本周报：可直接复制 / 发邮件"""
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    days = int(request.args.get('days', 7))
    days = days if days in (7, 14, 30) else 7
    txt = care.weekly_report(conn, patient, days)
    fn = f'{patient["name"]}_照护周报_{date.today().isoformat()}.txt'
    disp = ("attachment; filename=weekly.txt; filename*=UTF-8''"
            + quote(fn, safe=''))
    return Response(txt, mimetype='text/plain', headers={'Content-Disposition': disp})


# ---------------------------------------------------------------- 档案详情
@app.route('/patient/<int:pid>/profile')
def patient_profile(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    recent_diary = [dict(r) for r in conn.execute(
        'SELECT * FROM patient_diary WHERE patient_id=? ORDER BY day DESC, id DESC LIMIT 3',
        (pid,)).fetchall()]
    dm = diary_media_map(conn, [e['id'] for e in recent_diary])
    for e in recent_diary:
        e['media'] = dm.get(e['id'], [])
    return render_template(
        'patient_profile.html', patient=patient,
        judge=care.judge_vital,
        age=care.age_text(patient['birth_year']),
        bed_days=care.bed_days(patient['start_date']),
        status_log=load_status_log(conn, pid, 30),
        recent_diary=recent_diary,
        diary_n=conn.execute('SELECT COUNT(*) c FROM patient_diary WHERE patient_id=?',
                             (pid,)).fetchone()['c'],
        expense=expense_summary(conn, pid),
        med_n=conn.execute('SELECT COUNT(*) c FROM med_schedule WHERE patient_id=? AND active=1',
                           (pid,)).fetchone()['c'],
        records=[dict(r) for r in conn.execute(
            'SELECT * FROM medical_records WHERE patient_id=? ORDER BY happen_date DESC LIMIT 5',
            (pid,)).fetchall()],
        latest_vitals=conn.execute(
            'SELECT * FROM vitals WHERE patient_id=? ORDER BY day DESC, time DESC, id DESC LIMIT 1',
            (pid,)).fetchone(),
        alerts=care.alerts_for(conn, patient))


# ---------------------------------------------------------------- 知识库
@app.route('/knowledge')
def knowledge_page():
    conn = DB.get_db()
    q = (request.args.get('q') or '').strip()
    cat = request.args.get('cat') or ''
    sql = 'SELECT * FROM knowledge WHERE 1=1'
    args = []
    if q:
        sql += ' AND (topic LIKE ? OR conclusion LIKE ? OR source LIKE ?)'
        args += [f'%{q}%'] * 3
    if cat:
        sql += ' AND category=?'
        args.append(cat)
    rows = conn.execute(sql + ' ORDER BY category, id', args).fetchall()
    cats = [r['category'] for r in conn.execute(
        'SELECT DISTINCT category FROM knowledge ORDER BY category').fetchall()]
    return render_template('knowledge.html', rows=[dict(r) for r in rows],
                           q=q, cat=cat, cats=cats,
                           knowledge=care.CARE_KNOWLEDGE, level_tip=care.LEVEL_TIP)


# ---------------------------------------------------------------- 邮件通知
import smtplib
import threading
from email.header import Header
from email.mime.text import MIMEText

NOTIFY_KEYS = ['notify_enabled', 'notify_email', 'smtp_host', 'smtp_port',
               'smtp_ssl', 'smtp_user', 'smtp_pass',
               'notify_missed', 'notify_vitals', 'notify_visit']
NOTIFY_CATS = [('notify_missed', '任务漏打卡 / 翻身超时'),
               ('notify_vitals', '体征异常'),
               ('notify_visit', '复诊提醒')]


def get_setting(conn, k, default=''):
    row = conn.execute('SELECT v FROM settings WHERE k=?', (k,)).fetchone()
    return row['v'] if row and row['v'] is not None else default


def set_setting(conn, k, v):
    conn.execute(
        'INSERT INTO settings (k, v) VALUES (?,?)'
        ' ON CONFLICT(k) DO UPDATE SET v=excluded.v', (k, v))


def _smtp_send(cfg, subject, body):
    """按配置发邮件，抛异常说明失败原因"""
    host = (cfg.get('smtp_host') or '').strip()
    port = int(cfg.get('smtp_port') or 465)
    user = (cfg.get('smtp_user') or '').strip()
    to = [x.strip() for x in (cfg.get('notify_email') or '').split(',') if x.strip()]
    mode = (cfg.get('smtp_ssl') or 'ssl').strip()
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = user or 'careplat'
    msg['To'] = ', '.join(to)
    if mode == 'ssl':
        s = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        s = smtplib.SMTP(host, port, timeout=20)
        if mode == 'starttls':
            s.starttls()
    try:
        if user:
            s.login(user, cfg.get('smtp_pass') or '')
        s.sendmail(user or 'careplat@localhost', to, msg.as_string())
    finally:
        try:
            s.quit()
        except Exception:
            pass


def _notify_one(conn, patient, alert):
    """发一条预警（含去重 + 落发送日志）。返回 'sent' / 'dup' / 'off' / 'error'"""
    cfg = {k: get_setting(conn, k) for k in NOTIFY_KEYS}
    if cfg['notify_enabled'] != '1' or not cfg['notify_email'] or not cfg['smtp_host']:
        return 'off'
    cat = alert.get('cat') or ''
    if cat == 'visit' and cfg['notify_visit'] != '1':
        return 'off'
    if cat in ('missed', 'turn') and cfg['notify_missed'] != '1':
        return 'off'
    if cat == 'vitals' and cfg['notify_vitals'] != '1':
        return 'off'

    today = date.today().isoformat()
    key = cat or (alert['title'][:20])
    cur = conn.execute(
        'INSERT OR IGNORE INTO notify_log (patient_id, day, key, title, sent_at)'
        ' VALUES (?,?,?,?,?)',
        (patient['id'], today, key, alert['title'],
         datetime.now().isoformat(timespec='seconds')))
    if cur.rowcount == 0:
        return 'dup'          # 今天这条已经发过
    conn.commit()

    body = (f'{APP_NAME} 预警通知\n\n'
            f'病人：{patient["name"]}\n'
            f'时间：{today}\n\n'
            f'❗ {alert["title"]}\n'
            f'{alert.get("detail") or ""}\n\n'
            f'👉 {alert.get("action") or ""}\n\n'
            f'—— 打开平台查看：http://127.0.0.1:{os.environ.get("CAREPLAT_PORT", 5810)}\n'
            f'本邮件由照护管理平台自动发送，请勿回复')
    try:
        _smtp_send(cfg, f'【照护提醒】{patient["name"]}：{alert["title"][:30]}', body)
        conn.execute('UPDATE notify_log SET ok=1 WHERE patient_id=? AND day=? AND key=?',
                     (patient['id'], today, key))
        conn.commit()
        return 'sent'
    except Exception as e:
        conn.execute('UPDATE notify_log SET ok=0, error=? WHERE patient_id=? AND day=? AND key=?',
                     (str(e)[:300], patient['id'], today, key))
        conn.commit()
        return 'error'


def maybe_notify(patient, alerts):
    """请求线程里快速把该发的预警丢给后台线程发送，不阻塞页面"""
    if not alerts:
        return
    threading.Thread(target=_notify_worker, args=(dict(patient), alerts),
                     daemon=True).start()


def _notify_worker(patient, alerts):
    try:
        conn = DB.connect()
        for a in alerts:
            _notify_one(conn, patient, a)
        conn.close()
    except Exception:
        pass


def _notify_loop():
    """后台每 10 分钟扫一遍全部在照护病人的预警（护工不开网页也能收到漏药提醒）"""
    while True:
        try:
            conn = DB.connect()
            rows = conn.execute(
                "SELECT * FROM patients WHERE IFNULL(status,'在照护')=?",
                (care.STATUS_MANAGED,)).fetchall()
            for r in rows:
                p = dict(r)
                _notify_worker(p, care.alerts_for(conn, p))
            conn.close()
        except Exception:
            pass
        time.sleep(600)


def start_notify_loop():
    threading.Thread(target=_notify_loop, daemon=True).start()


# ---------------------------------------------------------------- 通知设置
@app.route('/settings')
def settings_page():
    conn = DB.get_db()
    cfg = {k: get_setting(conn, k) for k in NOTIFY_KEYS}
    logs = [dict(r) for r in conn.execute(
        'SELECT n.*, p.name FROM notify_log n LEFT JOIN patients p ON p.id=n.patient_id'
        ' ORDER BY n.sent_at DESC LIMIT 30').fetchall()]
    return render_template('settings.html', cfg=cfg, logs=logs,
                           cats=NOTIFY_CATS, sent=APP_NAME)


@app.route('/api/settings', methods=['POST'])
def api_settings_save():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    saved = []
    for k in NOTIFY_KEYS:
        if k in j:
            v = str(j.get(k) or '').strip()
            if k == 'smtp_pass' and v == '********':
                continue          # 前端回显占位符，不覆盖真密码
            set_setting(conn, k, v)
            saved.append(k)
    conn.commit()
    return jsonify({'ok': True, 'saved': saved})


@app.route('/api/settings/test', methods=['POST'])
def api_settings_test():
    conn = DB.get_db()
    cfg = {k: get_setting(conn, k) for k in NOTIFY_KEYS}
    if not cfg['notify_email'] or not cfg['smtp_host']:
        return jsonify({'ok': False, 'error': '先填收件邮箱和 SMTP 服务器并保存'}), 400
    try:
        _smtp_send(cfg, f'【{APP_NAME}】测试邮件', '收到这封邮件说明通知配置成功。\n\n'
                   '之后漏打卡、体征异常、复诊提醒会发到这个邮箱。')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:300]}), 400


# ---------------------------------------------------------------- 床头卡
@app.route('/patient/<int:pid>/bedcard')
def patient_bedcard(pid):
    conn, patient = load_patient(pid)
    if not patient:
        return redirect(url_for('patients'))
    meds = [dict(m) for m in conn.execute(
        'SELECT * FROM med_schedule WHERE patient_id=? AND active=1 ORDER BY id',
        (pid,)).fetchall()]
    tasks = care._fixed_slots(patient)
    task_summary = {}
    for s in tasks:
        task_summary.setdefault(s['type'], []).append(s['time'])
    return render_template('bedcard.html', patient=patient, meds=meds,
                           task_summary=task_summary,
                           age=care.age_text(patient['birth_year']),
                           bed_days=care.bed_days(patient['start_date']),
                           today=date.today().isoformat())


# ---------------------------------------------------------------- 关于
@app.route('/about')
def about_page():
    conn = DB.get_db()

    def one(sql, args=()):
        return conn.execute(sql, args).fetchone()[0]

    stat = {
        'patients': one('SELECT COUNT(*) FROM patients'),
        'managed': one("SELECT COUNT(*) FROM patients WHERE IFNULL(status,'在照护')=?",
                       (care.STATUS_MANAGED,)),
        'events': one('SELECT COUNT(*) FROM care_events'),
        'meds': one('SELECT COUNT(*) FROM med_schedule WHERE active=1'),
        'vitals': one('SELECT COUNT(*) FROM vitals'),
        'diary': one('SELECT COUNT(*) FROM patient_diary'),
        'media': one('SELECT COUNT(*) FROM diary_media'),
        'expense': one('SELECT COUNT(*) FROM patient_expense'),
        'spent': one('SELECT IFNULL(SUM(amount),0) FROM patient_expense'),
        'knowledge': one('SELECT COUNT(*) FROM knowledge'),
    }
    return render_template('about.html', stat=stat, since=APP_SINCE)


# ---------------------------------------------------------------- PWA
@app.route('/manifest.webmanifest')
def pwa_manifest():
    data = {
        'name': APP_NAME,
        'short_name': '照护',
        'description': '病人档案、照护任务打卡、用药提醒、体征记录、康复训练、日记与记账',
        'lang': 'zh-CN',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait',
        'background_color': '#F5F9F8',
        'theme_color': '#0F766E',
        'icons': [
            {'src': '/static/icon-192.png', 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'any'},
            {'src': '/static/icon-512.png', 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'any'},
            {'src': '/static/icon-512.png', 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'maskable'},
        ],
        'shortcuts': [
            {'name': '今日照护', 'url': '/patient/1/today'},
            {'name': '用药管理', 'url': '/patient/1/meds'},
            {'name': '体征记录', 'url': '/patient/1/vitals'},
            {'name': '照护日记', 'url': '/patient/1/diary'},
            {'name': '病人档案', 'url': '/patients'},
        ],
    }
    return jsonify(data), 200, {'Content-Type': 'application/manifest+json; charset=utf-8'}


@app.route('/sw.js')
def pwa_sw():
    resp = send_from_directory(app.static_folder, 'sw.js',
                               mimetype='application/javascript')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


# ---------------------------------------------------------------- 启动
@app.errorhandler(404)
def nf(e):
    return render_template('404.html'), 404


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class _Tee:
    """把输出同时写到控制台和日志文件（后台运行时控制台可能不存在）"""

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


def _setup_logging():
    try:
        os.makedirs(DB.DATA_DIR, exist_ok=True)
        f = open(os.path.join(DB.DATA_DIR, 'server.log'), 'a', encoding='utf-8')
        sys.stdout = _Tee(sys.stdout, f)
        sys.stderr = _Tee(sys.stderr, f)
    except Exception:
        pass


if __name__ == '__main__':
    _setup_logging()
    ensure_init()
    start_notify_loop()
    port = int(os.environ.get('CAREPLAT_PORT', 5810))
    ip = lan_ip()
    banner = (
        '\n' + '=' * 60 + '\n'
        f'  {APP_NAME} {APP_VERSION} 已启动\n'
        f'  作者：      {AUTHOR["name"]}（{AUTHOR["email"]}）\n'
        f'  本机访问：  http://127.0.0.1:{port}\n'
        f'  局域网访问：http://{ip}:{port}   （手机连同一 WiFi 打开这个）\n'
        f'  ⚠️ 只在家庭局域网用，不要做端口映射到公网（无登录）\n'
        f'  启动时间：  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
        + '=' * 60
    )
    print(banner)

    try:
        with open(os.path.join(DB.DATA_DIR, '访问地址.txt'), 'w', encoding='utf-8') as f:
            f.write(banner.strip() + '\n\n手机装到桌面：用局域网地址打开 → 浏览器菜单选「安装应用 / 添加到主屏幕」\n'
                    '⚠️ 本平台无登录，仅供家庭局域网使用，不要映射到公网。\n')
    except OSError:
        pass

    try:
        from waitress import serve
        print('  服务器：waitress（生产级，8 线程）')
        serve(app, host='0.0.0.0', port=port, threads=8, _quiet=True)
    except ImportError:
        print('  服务器：Flask 内置（建议 pip install waitress）')
        app.run(host='0.0.0.0', port=port, debug=False)
