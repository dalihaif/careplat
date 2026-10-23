# -*- coding: utf-8 -*-
"""照护管理平台 · 数据库连接与建表

架构借鉴狗狗管理平台（Flask + SQLite 单文件），全部字段带 patient_id，
从第一天就是多病人架构；当前版本不做登录，靠局域网隔离。
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

from flask import g

# 打包成 exe 后（PyInstaller），数据目录跟着 exe 放，而不是临时解包目录
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.dirname(os.environ['CAREPLAT_DB']) if os.environ.get('CAREPLAT_DB') else os.path.join(BASE_DIR, 'data')
# 上传的图片/视频落这里（不是 static，走 /media 路由按需读取）
UPLOAD_DIR = os.environ.get('CAREPLAT_UPLOADS') or os.path.join(DATA_DIR, 'uploads')
# 环境变量 CAREPLAT_DB 指向别的库文件（自检/演示用，避免污染真实数据）
DB_PATH = os.environ.get('CAREPLAT_DB') or os.path.join(DATA_DIR, 'careplat.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    sex               TEXT,
    birth_year        INTEGER,
    care_level        TEXT,              -- 自理 / 半协助 / 全协助 / 卧床
    diagnosis         TEXT,              -- 主要诊断
    condition_desc    TEXT,              -- 病情概述 / 照护要点
    allergies         TEXT,              -- 过敏史
    doctor            TEXT,              -- 主治医生
    doctor_phone      TEXT,
    hospital          TEXT,
    contact_name      TEXT,              -- 紧急联系人
    contact_phone     TEXT,
    contact_relation  TEXT,
    weight_current    REAL,
    weight_updated_at TEXT,
    start_date        TEXT,              -- 开始照护日期
    -- 管理状态：在照护 / 康复出院 / 转院 / 去世 / 其他
    status            TEXT DEFAULT '在照护',
    status_changed_at TEXT,
    note              TEXT,
    active            INTEGER DEFAULT 1, -- 兼容字段，等于 status=='在照护'
    created_at        TEXT
);

-- 病人状态变更流水（改了什么、为什么、什么时候）
CREATE TABLE IF NOT EXISTS patient_status_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT,
    note       TEXT,
    changed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_psl_patient ON patient_status_log(patient_id, changed_at);

-- 照护事件：翻身 / 进食 / 饮水 / 服药 / 康复训练 / 排泄 / 皮肤 / 洗澡 / 交接班 / 体重 / 备注
CREATE TABLE IF NOT EXISTS care_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    day        TEXT NOT NULL,
    time       TEXT,
    type       TEXT NOT NULL,
    payload    TEXT,        -- JSON；计划任务存 {"key": "turn-08:00"} 用于对账
    note       TEXT,
    by         TEXT,        -- 谁记录的（护工/家属署名，可选）
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ce_patient_day ON care_events(patient_id, day);

-- 用药时间表：一张药一行，times 是逗号分隔的服药时间点
CREATE TABLE IF NOT EXISTS med_schedule (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    med_name   TEXT NOT NULL,
    dose       TEXT,             -- 剂量，如 5mg、1片
    form       TEXT,             -- 剂型：片 / 粒 / 支 / 贴 / 袋
    times      TEXT NOT NULL,    -- 如 08:00,12:00,20:00
    usage_txt  TEXT,             -- 用法：饭后 / 空腹 / 嚼服
    purpose    TEXT,             -- 用途：降压 / 降糖
    note       TEXT,
    active     INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ms_patient ON med_schedule(patient_id, active);

-- 体征记录：一天可多条，趋势图 + 异常判断都在这
CREATE TABLE IF NOT EXISTS vitals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    day        TEXT NOT NULL,
    time       TEXT,
    bp_high    REAL,             -- 收缩压（高压）
    bp_low     REAL,             -- 舒张压（低压）
    hr         REAL,             -- 心率
    temp       REAL,             -- 体温 ℃
    spo2       REAL,             -- 血氧 %
    sugar      REAL,             -- 血糖 mmol/L
    weight     REAL,             -- 体重 kg
    note       TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_v_patient_day ON vitals(patient_id, day);

-- 照护日记：一条日记可带多张图片/视频（媒体另存 diary_media）
CREATE TABLE IF NOT EXISTS patient_diary (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    day        TEXT NOT NULL,
    title      TEXT,
    mood       TEXT,
    place      TEXT,
    content    TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_diary_patient_day ON patient_diary(patient_id, day);

-- 日记媒体：文件落在 data/uploads 下，这里只存相对路径与元信息
CREATE TABLE IF NOT EXISTS diary_media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    diary_id   INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    kind       TEXT,          -- image / video
    path       TEXT,          -- 相对 data/uploads 的路径
    thumb      TEXT,          -- 图片缩略图相对路径（视频为空）
    orig_name  TEXT,          -- 上传时的原始文件名（含中文）
    mime       TEXT,
    size       INTEGER,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dm_diary ON diary_media(diary_id);

-- 照护费用：护工工资 / 药品 / 耗材 / 复诊 等
CREATE TABLE IF NOT EXISTS patient_expense (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    day        TEXT NOT NULL,
    category   TEXT,
    item       TEXT,
    amount     REAL DEFAULT 0,
    qty        REAL,
    unit       TEXT,
    shop       TEXT,
    pay_method TEXT,
    note       TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ex_patient_day ON patient_expense(patient_id, day);

-- 医疗档案：就诊 / 检查 / 手术 / 复诊提醒
CREATE TABLE IF NOT EXISTS medical_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER NOT NULL,
    kind        TEXT,             -- 门诊 / 住院 / 检查 / 手术 / 复诊
    happen_date TEXT,
    next_due    TEXT,             -- 下次复诊日期
    hospital    TEXT,
    doctor      TEXT,
    summary     TEXT,             -- 结论 / 医嘱摘要
    note        TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mr_patient ON medical_records(patient_id);

-- 通知发送记录（同一条预警一天只发一次，防轰炸）
CREATE TABLE IF NOT EXISTS notify_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    day        TEXT NOT NULL,
    key        TEXT NOT NULL,
    title      TEXT,
    ok         INTEGER,
    error      TEXT,
    sent_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_nl_dedup ON notify_log(patient_id, day, key);

CREATE TABLE IF NOT EXISTS knowledge (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT,
    topic      TEXT,
    conclusion TEXT,
    source     TEXT,
    url        TEXT,
    age_range  TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def get_db():
    if 'db' not in g:
        g.db = connect()
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db(conn=None):
    own = conn is None
    if own:
        conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    if own:
        conn.close()
