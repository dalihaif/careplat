# -*- coding: utf-8 -*-
"""照护管理平台 · 全量自检

跑在临时库 + 临时上传目录上（CAREPLAT_DB / CAREPLAT_UPLOADS 环境变量在 import app 前设置），
不碰真实数据。覆盖：页面、API、打卡、用药表、体征边界、记账、CSV、日记上传。
"""
import io
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

_TMP = tempfile.mkdtemp(prefix='careplat_selftest_')
os.environ['CAREPLAT_DB'] = os.path.join(_TMP, 'test.db')
os.environ['CAREPLAT_UPLOADS'] = os.path.join(_TMP, 'uploads')
os.environ['CAREPLAT_NO_AUTH'] = '1'      # 自检用 test_client 走免密（登录门单独测）

import app as A          # noqa: E402  必须在环境变量之后
import care              # noqa: E402
import db as DB          # noqa: E402

OK = 0
FAIL = []


def check(name, cond, detail=''):
    global OK
    if cond:
        OK += 1
        print(f'  ✅ {name}')
    else:
        FAIL.append(name)
        print(f'  ❌ {name}  {detail}')


def main():
    A.ensure_init()
    c = A.app.test_client()
    today = date.today().isoformat()

    print('\n== 1. 基础页面 ==')
    for path in ['/', '/patients', '/patients/new', '/knowledge', '/about',
                 '/manifest.webmanifest', '/sw.js', '/no-such-page']:
        r = c.get(path)
        expect = 404 if path == '/no-such-page' else 200
        check(f'{path} → {expect}', r.status_code == expect, f'got {r.status_code}')

    print('\n== 2. 病人档案 CRUD ==')
    r = c.post('/patients/new', data={
        'name': '测试老人', 'sex': '男', 'birth_year': '1946',
        'care_level': '卧床', 'diagnosis': '脑梗', 'allergies': '',
        'condition_desc': '长期卧床', 'doctor': '测试医生', 'doctor_phone': '',
        'hospital': '', 'contact_name': '测试家属', 'contact_phone': '13800000000',
        'contact_relation': '儿子', 'weight_current': '60', 'start_date': today,
        'note': ''}, follow_redirects=True)
    check('建档成功', r.status_code == 200 and '测试老人'.encode() in r.data)
    conn = DB.connect()
    pid = conn.execute('SELECT id FROM patients WHERE name=?', ('测试老人',)).fetchone()['id']
    conn.close()

    r = c.get(f'/patients/{pid}/edit')
    check('编辑页 200', r.status_code == 200)
    r = c.post(f'/patients/{pid}/edit', data={
        'name': '测试老人', 'sex': '男', 'birth_year': '1946', 'care_level': '半协助',
        'diagnosis': '脑梗', 'condition_desc': '', 'allergies': '', 'doctor': '',
        'doctor_phone': '', 'hospital': '', 'contact_name': '', 'contact_phone': '',
        'contact_relation': '', 'weight_current': '61', 'start_date': today,
        'status': '在照护', 'status_note': '', 'note': ''}, follow_redirects=True)
    check('改档案+改等级成功', r.status_code == 200)
    conn = DB.connect()
    lv = conn.execute('SELECT care_level, weight_current FROM patients WHERE id=?',
                      (pid,)).fetchone()
    check('等级/体重已更新', lv['care_level'] == '半协助' and lv['weight_current'] == 61)
    conn.close()

    print('\n== 3. 状态变更留痕 ==')
    r = c.post('/api/patient/status', json={'patient_id': pid, 'status': '康复出院',
                                            'note': '测试出院'})
    check('API 改状态', r.get_json()['ok'] and r.get_json()['changed'])
    r = c.post('/api/patient/status', json={'patient_id': pid, 'status': '不存在的状态'})
    check('非法状态被拒', r.status_code == 400)
    r = c.post('/api/patient/status', json={'patient_id': pid, 'status': '在照护'})
    check('改回在照护', r.get_json()['ok'])
    conn = DB.connect()
    n = conn.execute('SELECT COUNT(*) c FROM patient_status_log WHERE patient_id=?',
                     (pid,)).fetchone()['c']
    check('状态流水 2 条', n == 2, f'got {n}')
    conn.close()

    print('\n== 4. 打卡 / 编辑 / 删除 ==')
    r = c.post('/api/checkin', json={'patient_id': pid, 'type': 'turn', 'day': today,
                                     'time': '08:00', 'data': {'side': '左侧卧', 'key': 'turn-08:00'}})
    check('翻身打卡', r.get_json()['ok'])
    r = c.post('/api/checkin', json={'patient_id': pid, 'type': 'weight', 'day': today,
                                     'data': {'kg': 60.5}})
    check('体重打卡', r.get_json()['ok'])
    conn = DB.connect()
    w = conn.execute('SELECT weight_current FROM patients WHERE id=?', (pid,)).fetchone()
    check('档案体重同步', w['weight_current'] == 60.5, f"got {w['weight_current']}")
    eid = conn.execute("SELECT id FROM care_events WHERE type='turn'").fetchone()['id']
    conn.close()

    r = c.post('/api/event/update', json={'id': eid, 'data': {'side': '右侧卧', 'key': 'turn-08:00'}})
    check('编辑事件', r.get_json()['ok'])
    conn = DB.connect()
    import json as J
    payload = conn.execute('SELECT payload FROM care_events WHERE id=?', (eid,)).fetchone()['payload']
    check('编辑生效', J.loads(payload)['side'] == '右侧卧')
    conn.close()
    r = c.post('/api/event/delete', json={'id': eid})
    check('删除事件', r.get_json()['ok'])

    print('\n== 5. 用药时间表 ==')
    r = c.post('/api/med/schedule', json={'patient_id': pid, 'med_name': '阿司匹林',
                                          'dose': '100mg', 'form': '片',
                                          'times': '08:00, 20:00 ', 'usage_txt': '饭后'})
    check('加药', r.get_json()['ok'])
    r = c.post('/api/med/schedule', json={'patient_id': pid, 'med_name': '坏时间',
                                          'times': '25:99'})
    check('非法时间被拒', r.status_code == 400)
    r = c.post('/api/med/schedule', json={'patient_id': pid, 'med_name': '', 'times': '08:00'})
    check('空药名被拒', r.status_code == 400)
    conn = DB.connect()
    sid = conn.execute('SELECT id, times FROM med_schedule').fetchone()
    check('时间规整去重排序', sid['times'] == '08:00,20:00', f"got {sid['times']}")
    sid = sid['id']
    conn.close()
    r = c.post('/api/med/schedule/update', json={'id': sid, 'med_name': '阿司匹林',
                                                 'times': '09:00', 'dose': '100mg', 'form': '片'})
    check('改药时间', r.get_json()['ok'])
    r = c.post('/api/med/schedule/toggle', json={'id': sid})
    check('停用', r.get_json()['active'] == 0)
    r = c.post('/api/med/schedule/toggle', json={'id': sid})
    check('再启用', r.get_json()['active'] == 1)
    r = c.get(f'/patient/{pid}/meds')
    check('用药页 200 + 出现在时间轴', r.status_code == 200 and '09:00'.encode() in r.data)
    # 打卡吃药 → 时间轴该槽位应完成
    c.post('/api/checkin', json={'patient_id': pid, 'type': 'med', 'day': today,
                                 'time': '09:05', 'data': {'name': '阿司匹林', 'dose': '100mg',
                                                           'key': 'med-1-09:00'}})
    r = c.get(f'/patient/{pid}/today')
    check('服药后时间轴标完成', '已完成'.encode() in r.data)
    r = c.post('/api/med/schedule/delete', json={'id': sid})
    check('删药', r.get_json()['ok'])

    print('\n== 6. 体征（含边界校验） ==')
    r = c.post('/api/vitals', json={'patient_id': pid, 'day': today, 'time': '08:00',
                                    'bp_high': 132, 'bp_low': 82, 'hr': 76,
                                    'temp': 36.5, 'spo2': 97})
    check('正常体征', r.get_json()['ok'])
    r = c.post('/api/vitals', json={'patient_id': pid, 'day': today, 'bp_high': 158, 'bp_low': 96})
    check('高血压记录成功', r.get_json()['ok'])
    check('高危预警返回', any(a['level'] == 'danger' for a in r.get_json().get('alerts', [])))
    r = c.post('/api/vitals', json={'patient_id': pid, 'day': today, 'temp': 99})
    check('体温超范围被拒', r.status_code == 400)
    r = c.post('/api/vitals', json={'patient_id': pid, 'day': 'bad-date'})
    check('坏日期被拒', r.status_code == 400)
    r = c.post('/api/vitals', json={'patient_id': pid, 'day': today, 'note': '只有备注没数值'})
    check('全空被拒', r.status_code == 400)
    r = c.get(f'/patient/{pid}/vitals')
    check('体征页 200 + 图表数据', r.status_code == 200 and b'bpChart' in r.data)
    conn = DB.connect()
    vid = conn.execute('SELECT id FROM vitals ORDER BY id DESC LIMIT 1').fetchone()['id']
    conn.close()
    r = c.post('/api/vitals/delete', json={'id': vid})
    check('删体征', r.get_json()['ok'])

    print('\n== 7. 记账 ==')
    r = c.post('/api/expense', json={'patient_id': pid, 'day': today, 'category': '护工工资',
                                     'item': '测试工资', 'amount': 100})
    check('记一笔', r.get_json()['ok'] and r.get_json()['summary']['total'] == 100)
    r = c.post('/api/expense', json={'patient_id': pid, 'day': today, 'category': '不存在的分类',
                                     'amount': 100})
    check('坏分类被拒', r.status_code == 400)
    r = c.post('/api/expense', json={'patient_id': pid, 'day': today, 'category': '药品',
                                     'amount': -5})
    check('负金额被拒', r.status_code == 400)
    r = c.get(f'/patient/{pid}/expense.csv')
    check('CSV 导出带 BOM', r.status_code == 200 and r.data[:3] == b'\xef\xbb\xbf')
    check('CSV 中文文件名 RFC5987', "filename*=UTF-8''" in r.headers.get('Content-Disposition', ''))
    conn = DB.connect()
    xid = conn.execute('SELECT id FROM patient_expense').fetchone()['id']
    conn.close()
    r = c.post('/api/expense/update', json={'id': xid, 'patient_id': pid, 'day': today,
                                            'category': '耗材', 'amount': 50, 'item': '尿垫'})
    check('改账', r.get_json()['ok'] and r.get_json()['summary']['total'] == 50)
    r = c.post('/api/expense/delete', json={'id': xid})
    check('删账', r.get_json()['ok'] and r.get_json()['summary']['total'] == 0)

    print('\n== 8. 日记（multipart 上传 + 媒体删除） ==')
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (60, 40), (200, 220, 210)).save(buf, 'PNG')
    buf.seek(0)
    r = c.post(f'/patient/{pid}/diary/new', data={
        'day': today, 'title': '测试日记', 'mood': '恢复中', 'place': '家中',
        'content': '今天状态不错', 'files': [(buf, '测试照片.png')]},
        content_type='multipart/form-data', follow_redirects=True)
    check('日记上传', r.status_code == 200 and '测试日记'.encode() in r.data)
    conn = DB.connect()
    m = conn.execute('SELECT * FROM diary_media').fetchone()
    check('媒体入库+缩略图', m is not None and m['thumb'], 'no thumb')
    fpath = os.path.join(DB.UPLOAD_DIR, m['path'].replace('/', os.sep))
    check('文件落盘', os.path.exists(fpath))
    r = c.get(f"/media/{m['path']}")
    check('/media 可读', r.status_code == 200)
    r = c.get('/media/../../etc/passwd')
    check('防穿越', r.status_code in (404, 403))
    r = c.post('/api/diary/media/delete', json={'id': m['id']})
    check('删媒体双清', r.get_json()['ok'] and not os.path.exists(fpath))
    did = conn.execute('SELECT id FROM patient_diary').fetchone()['id']
    conn.close()
    r = c.post(f'/patient/{pid}/diary/{did}/delete', follow_redirects=True)
    check('删日记', r.status_code == 200)

    print('\n== 9. 康复 / 记录 / 周报 / 详情 ==')
    c.post('/api/checkin', json={'patient_id': pid, 'type': 'rehab', 'day': today,
                                 'data': {'project': '抬腿练习', 'minutes': 10,
                                          'success': 8, 'total': 10}})
    r = c.get(f'/patient/{pid}')
    check('/patient/1 重定向到 today', r.status_code == 302)
    for path in [f'/patient/{pid}/today', f'/patient/{pid}/meds',
                 f'/patient/{pid}/vitals', f'/patient/{pid}/rehab', f'/patient/{pid}/records',
                 f'/patient/{pid}/diary', f'/patient/{pid}/expense', f'/patient/{pid}/medical',
                 f'/patient/{pid}/weekly', f'/patient/{pid}/profile',
                 f'/patient/{pid}/bedcard', f'/patient/{pid}/weekly.txt', '/settings']:
        r = c.get(path)
        check(f'{path} → 200', r.status_code == 200, f'got {r.status_code}')
    r = c.get(f'/patient/{pid}/weekly.txt')
    check('周报文本含完成率', '任务完成率'.encode() in r.data and '照护管理平台'.encode() in r.data)
    r = c.get(f'/patient/{pid}/medical')
    check('复诊清单渲染', '复诊准备清单'.encode() in r.data)
    r = c.get(f'/patient/{pid}/bedcard')
    check('床头卡含药名与紧急联系', '床头卡'.encode() in r.data)
    r = c.get('/patient/99999/today', follow_redirects=False)
    check('不存在病人重定向', r.status_code == 302)
    r = c.get(f'/patient/{pid}/records?type=rehab&q=抬腿')
    check('记录筛选', r.status_code == 200 and '抬腿练习'.encode() in r.data)
    r = c.post('/api/medical_record', json={'patient_id': pid, 'kind': '复诊',
                                            'happen_date': today,
                                            'next_due': (date.today() + timedelta(days=5)).isoformat(),
                                            'summary': '测试复诊提醒'})
    check('医疗记录 + 预警', r.get_json()['ok'])
    r = c.get(f'/patient/{pid}/medical')
    check('医疗页含复诊提醒', '复诊'.encode() in r.data)

    print('\n== 10. 今日时间轴一致性 ==')
    conn = DB.connect()
    p = dict(conn.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone())
    timeline, hit, total = care.today_timeline(conn, p, today)
    check('半协助有餐有饮水无翻身',
          any(t['type'] == 'meal' for t in timeline) and
          not any(t['type'] == 'turn' for t in timeline))
    p['care_level'] = '卧床'
    t2, h2, tt2 = care.today_timeline(conn, p, today)
    check('卧床有 8 次翻身', sum(1 for t in t2 if t['type'] == 'turn') == 8)
    check('卧床有皮肤检查', sum(1 for t in t2 if t['type'] == 'skin') == 2)
    alerts = care.alerts_for(conn, p)
    check('预警结构完整', all({'level', 'title', 'detail', 'action'} <= set(a) for a in alerts))
    conn.close()

    print('\n== 11. 通知设置与去重 ==')
    r = c.post('/api/settings', json={'notify_enabled': '0', 'notify_email': 'a@b.com',
                                      'smtp_host': '', 'notify_missed': '1'})
    check('保存设置', r.get_json()['ok'])
    conn = DB.connect()
    v = conn.execute("SELECT v FROM settings WHERE k='notify_enabled'").fetchone()['v']
    check('设置落库', v == '0')
    conn.close()
    r = c.post('/api/settings/test')
    check('未配 SMTP 时测试被拒', r.status_code == 400)

    print('\n== 12. 访问密码（登录门） ==')
    conn = DB.connect()
    A._set_password(conn, 'test1234')
    conn.close()
    # 临时关掉免密开关，模拟公网访问
    os.environ.pop('CAREPLAT_NO_AUTH', None)
    try:
        gate = A.app.test_client()
        r = gate.get('/')
        check('未登录访问首页 → 跳登录页', r.status_code == 302 and '/login' in r.headers['Location'],
              f'got {r.status_code} {r.headers.get("Location")}')
        r = gate.get('/api/health')
        check('/api/health 免密放行', r.status_code == 200)
        r = gate.post('/api/checkin', json={'patient_id': 1, 'type': 'water'})
        check('未登录调 API → 401 JSON', r.status_code == 401 and r.get_json().get('need_login'))
        r = gate.post('/login', data={'pwd': 'wrong'})
        check('密码错 → 提示且不进门', r.status_code == 200 and '密码不对'.encode() in r.data, r.status_code)
        r = gate.post('/login', data={'pwd': 'test1234'})
        check('密码对 → 跳首页', r.status_code == 302, r.status_code)
        r = gate.get('/')
        check('登录后访问首页 → 200', r.status_code == 200, r.status_code)
        r = gate.get('/logout')
        r = gate.get('/patients')
        check('退出后又被拦', r.status_code == 302 and '/login' in r.headers['Location'])
        # 连错 5 次锁 10 分钟
        gate2 = A.app.test_client()
        for _ in range(5):
            gate2.post('/login', data={'pwd': 'x'}, environ_base={'REMOTE_ADDR': '9.9.9.9'})
        r = gate2.post('/login', data={'pwd': 'test1234'}, environ_base={'REMOTE_ADDR': '9.9.9.9'})
        check('连错 5 次 → 锁定', '试太多次'.encode() in r.data)
        A.LOGIN_FAIL.clear()
        # 改密码
        gc = A.app.test_client()
        gc.post('/login', data={'pwd': 'test1234'})
        r = gc.post('/api/settings/password', json={'old': 'bad', 'new': 'abcdefg1'})
        check('改密码：旧密码错被拒', r.status_code == 200 and not r.get_json()['ok'])
        r = gc.post('/api/settings/password', json={'old': 'test1234', 'new': 'abcdefg1'})
        check('改密码：旧密码对成功', r.get_json()['ok'])
        r = gc.post('/login', data={'pwd': 'abcdefg1'})
        check('新密码可登录', r.status_code == 302)
    finally:
        os.environ['CAREPLAT_NO_AUTH'] = '1'

    print(f'\n========== 结果：{OK} 通过 / {len(FAIL)} 失败 ==========')
    if FAIL:
        for f in FAIL:
            print(f'  ❌ {f}')
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
