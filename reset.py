# -*- coding: utf-8 -*-
"""清空所有业务数据（保留知识库）
用法：python reset.py        —— 清空病人及全部记录
     python reset.py all    —— 连知识库一起清空并重新灌入内置底表
"""
import sys

import app as A
import db as DB

conn = DB.connect()
DB.init_db(conn)
conn.executescript(
    'DELETE FROM care_events;'
    'DELETE FROM medical_records;'
    'DELETE FROM med_schedule;'
    'DELETE FROM vitals;'
    'DELETE FROM diary_media;'
    'DELETE FROM patient_diary;'
    'DELETE FROM patient_expense;'
    'DELETE FROM patient_status_log;'
    'DELETE FROM patients;'
    "DELETE FROM sqlite_sequence WHERE name IN ('patients','care_events','med_schedule',"
    "'vitals','diary_media','patient_diary','patient_expense','patient_status_log','medical_records');"
)
if len(sys.argv) > 1 and sys.argv[1] == 'all':
    conn.execute('DELETE FROM knowledge')
    conn.commit()
    A.seed_knowledge(conn)
    print('已清空全部数据，并重建照护知识库')
else:
    conn.commit()
    print('已清空病人与全部记录（知识库保留）')
conn.close()
