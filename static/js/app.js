/* 照护管理平台 · 前端交互（架构借鉴狗狗管理平台） */
(function () {
  'use strict';

  /* ------------------------------------------------ 打卡 / 编辑弹窗 */
  var modalEl = document.getElementById('ckModal');
  var ck = modalEl ? new bootstrap.Modal(modalEl) : null;

  var TITLES = {
    turn: '🔄 记录翻身',
    meal: '🍚 记录进食',
    water: '💧 记录饮水',
    med: '💊 记录服药',
    rehab: '💪 记录康复训练',
    potty: '🚽 记录排泄',
    skin: '🩹 记录皮肤检查',
    bath: '🛁 记录洗澡擦浴',
    handover: '🤝 记录交接班',
    weight: '⚖️ 记录体重',
    note: '📝 记录备注'
  };

  var FIELDS = {
    turn: ['turn_side', 'turn_skin'],
    meal: ['meal_food', 'meal_eaten', 'meal_method'],
    water: ['water_ml'],
    med: ['med_name', 'med_dose'],
    rehab: ['rehab_project', 'rehab_minutes', 'rehab_success', 'rehab_total'],
    potty: ['potty_kind', 'potty_amount', 'potty_extra'],
    skin: ['skin_finding', 'skin_site'],
    bath: ['bath_kind'],
    handover: [],
    weight: ['weight_kg'],
    note: []
  };
  var SELECTS = ['meal_eaten', 'meal_method', 'potty_kind', 'skin_finding',
                 'turn_side', 'bath_kind', 'rehab_project'];

  function show(kind) {
    modalEl.querySelectorAll('[data-sec]').forEach(function (s) {
      s.classList.toggle('d-none', s.dataset.sec !== kind);
    });
  }

  function el(id) { return document.getElementById(id); }
  function val(id) {
    var e = el(id);
    return e ? String(e.value).trim() : '';
  }
  function num(id) {
    var v = val(id);
    return v === '' ? null : Number(v);
  }

  function todayISO() {
    var n = new Date();
    return n.getFullYear() + '-' + ('0' + (n.getMonth() + 1)).slice(-2) + '-' + ('0' + n.getDate()).slice(-2);
  }

  function setVal(id, v) {
    var e = el(id);
    if (e) e.value = (v === null || v === undefined) ? '' : v;
  }

  function setSelect(id, v) {
    var e = el(id);
    if (!e) return;
    v = (v === null || v === undefined) ? '' : String(v);
    var found = false;
    for (var i = 0; i < e.options.length; i++) {
      if (e.options[i].value === v) { found = true; break; }
    }
    if (!found && v !== '') {
      var o = document.createElement('option');
      o.value = v;
      o.textContent = v;
      o.setAttribute('data-tmp', '1');
      e.appendChild(o);
    }
    e.value = v;
  }

  function resetForm() {
    el('ckEditId').value = '';
    Object.keys(FIELDS).forEach(function (k) {
      FIELDS[k].forEach(function (id) { setVal(id, ''); });
    });
    setVal('ckNote', '');
    setVal('ckBy', '');
    ['potty_blood'].forEach(function (id) {
      var c = el(id);
      if (c) c.checked = false;
    });
    el('ckEditHint').classList.add('d-none');
    el('ckSaveBtn').textContent = '保存记录';
    SELECTS.forEach(function (id) {
      var e = el(id);
      if (e) e.querySelectorAll('option[data-tmp]').forEach(function (o) { o.remove(); });
    });
  }

  function fillForm(kind, d, ev) {
    d = d || {};
    if (kind === 'turn') {
      setSelect('turn_side', d.side || '左侧卧');
      setVal('turn_skin', d.skin || '');
    } else if (kind === 'meal') {
      setVal('meal_food', d.food);
      setSelect('meal_eaten', d.eaten || '');
      setSelect('meal_method', d.method || '经口正常');
    } else if (kind === 'water') {
      setVal('water_ml', d.ml);
    } else if (kind === 'med') {
      setVal('med_name', d.name);
      setVal('med_dose', d.dose);
    } else if (kind === 'rehab') {
      setSelect('rehab_project', d.project || '');
      setVal('rehab_minutes', d.minutes);
      setVal('rehab_success', d.success);
      setVal('rehab_total', d.total);
    } else if (kind === 'potty') {
      setSelect('potty_kind', d.kind || '尿');
      if (el('potty_blood')) el('potty_blood').checked = !!d.blood;
      setVal('potty_amount', d.amount);
      setVal('potty_extra', d.extra);
    } else if (kind === 'skin') {
      setSelect('skin_finding', d.finding || '无异常');
      setVal('skin_site', d.site);
    } else if (kind === 'bath') {
      setSelect('bath_kind', d.kind || '擦浴');
    } else if (kind === 'weight') {
      setVal('weight_kg', d.kg);
    }
    setVal('ckNote', ev.note || '');
    setVal('ckBy', ev.by || '');
  }

  window.openCheckin = function (btn) {
    if (!ck) return;
    resetForm();
    var kind = btn.dataset.kind;
    var t = btn.dataset.time;
    if (!t) {
      var n = new Date();
      t = ('0' + n.getHours()).slice(-2) + ':' + ('0' + n.getMinutes()).slice(-2);
    }
    el('ckTitle').textContent = TITLES[kind] || '记录';
    el('ckType').value = kind;
    el('ckTime').value = t;
    el('ckDay').value = btn.dataset.day || '';
    el('ckKey').value = btn.dataset.key || '';
    el('ckDayInput').value = btn.dataset.day || todayISO();
    el('ckTimeInput').value = t;
    show(kind);
    if (kind === 'med' && btn.dataset.def) {
      /* data-def = "药名|剂量" */
      var parts = btn.dataset.def.split('|');
      if (!el('med_name').value) el('med_name').value = parts[0] || '';
      if (!el('med_dose').value) el('med_dose').value = parts[1] || '';
    }
    if (kind === 'rehab') {
      if (!el('rehab_total').value) el('rehab_total').value = '10';
      if (!el('rehab_success').value) el('rehab_success').value = '8';
      if (!el('rehab_minutes').value) el('rehab_minutes').value = '15';
    }
    ck.show();
  };

  window.openEdit = function (btn) {
    if (!ck) return;
    var ev;
    try {
      ev = JSON.parse(btn.dataset.event);
    } catch (e) {
      alert('记录数据读取失败');
      return;
    }
    resetForm();
    el('ckEditId').value = ev.id;
    el('ckType').value = ev.type;
    el('ckTime').value = ev.time || '';
    el('ckDay').value = ev.day || '';
    el('ckKey').value = (ev.data && ev.data.key) || '';
    el('ckDayInput').value = ev.day || todayISO();
    el('ckTimeInput').value = ev.time || '';
    el('ckTitle').textContent = '✏️ 编辑记录（' + (TITLES[ev.type] || ev.type).replace(/^\S+\s/, '') + '）';
    fillForm(ev.type, ev.data, ev);
    show(ev.type);
    el('ckEditHint').classList.remove('d-none');
    el('ckSaveBtn').textContent = '保存修改';
    ck.show();
  };

  function collect(kind) {
    var d = {};
    if (kind === 'turn') {
      d.side = val('turn_side') || '左侧卧';
      d.skin = val('turn_skin');
    } else if (kind === 'meal') {
      d.food = val('meal_food');
      d.eaten = val('meal_eaten');
      d.method = val('meal_method') || '经口正常';
    } else if (kind === 'water') {
      d.ml = num('water_ml');
    } else if (kind === 'med') {
      d.name = val('med_name');
      d.dose = val('med_dose');
      if (!d.name) { alert('请填药名'); return null; }
    } else if (kind === 'rehab') {
      d.project = val('rehab_project');
      d.minutes = num('rehab_minutes');
      d.success = num('rehab_success') || 0;
      d.total = num('rehab_total') || 0;
    } else if (kind === 'potty') {
      d.kind = val('potty_kind') || '尿';
      d.blood = !!(el('potty_blood') && el('potty_blood').checked);
      d.amount = val('potty_amount');
      d.extra = val('potty_extra');
    } else if (kind === 'skin') {
      d.finding = val('skin_finding') || '无异常';
      d.site = val('skin_site');
    } else if (kind === 'bath') {
      d.kind = val('bath_kind') || '擦浴';
    } else if (kind === 'weight') {
      d.kg = num('weight_kg');
      if (!d.kg) { alert('请填体重'); return null; }
    }
    return d;
  }

  window.submitCheckin = function () {
    var kind = el('ckType').value;
    var data = collect(kind);
    if (data === null) return;
    /* 计划任务打卡时带上槽位 key，方便对账 */
    if (!data.key && el('ckKey').value && !el('ckEditId').value) data.key = el('ckKey').value;
    var editId = el('ckEditId').value;
    var body = {
      patient_id: Number(el('ckPatient').value),
      type: kind,
      time: el('ckTimeInput').value || el('ckTime').value,
      day: el('ckDayInput').value || el('ckDay').value,
      note: val('ckNote'),
      by: val('ckBy'),
      data: data
    };
    var url = '/api/checkin';
    if (editId) {
      url = '/api/event/update';
      body.id = Number(editId);
    }
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) {
        ck.hide();
        /* 计划任务：局部更新时间轴；临时/详细记录：需要进「已记录」列表，刷新 */
        if (!editId && body.data.key && markDone(body.data.key)) {
          toast('✅ 已记录，不用刷新');
        } else {
          location.reload();
        }
      } else {
        alert('保存失败：' + (res.error || '未知错误'));
      }
    }).catch(function () { alert('网络错误，记录没有保存'); });
  };

  window.delEvent = function (id) {
    if (!confirm('删除这条记录？删了就找不回来了。')) return;
    fetch('/api/event/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，记录没有删除'); });
  };

  window.copyText = function (elId, btn) {
    var e = document.getElementById(elId);
    if (!e) return;
    copyTextFromString(e.innerText, btn);
  };

  function copyTextFromString(t, btn) {
    var done = function () {
      var old = btn.textContent;
      btn.textContent = '✅ 已复制';
      setTimeout(function () { btn.textContent = old; }, 1500);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t).then(done).catch(function () { fallback(t, done); });
    } else {
      fallback(t, done);
    }
  }

  function fallback(t, done) {
    var ta = document.createElement('textarea');
    ta.value = t;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (e) { alert('复制失败，请手动选择'); }
    document.body.removeChild(ta);
  }

  /* ------------------------------------------------ 快速打卡（单字段） */
  window.quickHit = function (patientId, day, time, type, data) {
    fetch('/api/checkin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: patientId, type: type, day: day, time: time, data: data || {} })
    }).then(function () { location.reload(); });
  };

  /* ------------------------------------------------ 一键记完成（不打弹窗） */
  function toast(msg) {
    var t = document.getElementById('cpToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'cpToast';
      t.style.cssText = 'position:fixed;left:50%;bottom:70px;transform:translateX(-50%);' +
        'background:#22312E;color:#fff;padding:8px 18px;border-radius:20px;font-size:.85rem;' +
        'z-index:9999;opacity:.95;box-shadow:0 4px 14px rgba(0,0,0,.25);transition:opacity .3s';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.display = 'block';
    t.style.opacity = '.95';
    setTimeout(function () { t.style.opacity = '0'; }, 1600);
  }

  function markDone(key) {
    var item = document.querySelector('.tl-item[data-key="' + key + '"]');
    if (!item) return false;
    item.classList.add('done');
    var chip = document.createElement('span');
    chip.className = 'chip ok';
    chip.textContent = '✅ 已完成';
    var title = item.querySelector('.tl-body .d-flex');
    if (title && !item.querySelector('.chip.ok')) title.appendChild(chip);
    var box = item.querySelector('.d-flex.gap-1') || item.lastElementChild;
    if (box) box.innerHTML = '<button class="btn btn-sm btn-outline-secondary" disabled>✓</button>';
    /* 更新进度条与计数 */
    var items = document.querySelectorAll('.tl-item');
    var done = document.querySelectorAll('.tl-item.done').length;
    var prog = document.getElementById('ckProgress');
    var bar = document.getElementById('ckBar');
    if (prog && items.length) prog.textContent = done + '/' + items.length + ' 已完成';
    if (bar && items.length) bar.style.width = Math.round(done / items.length * 100) + '%';
    return true;
  }

  window.quickDone = function (btn) {
    var body = {
      patient_id: Number(document.getElementById('ckPatient').value),
      type: btn.dataset.kind,
      time: btn.dataset.time,
      day: btn.dataset.day,
      data: { key: btn.dataset.key }
    };
    if (btn.dataset.kind === 'med' && btn.dataset.def) {
      var parts = btn.dataset.def.split('|');
      body.data.name = parts[0] || '';
      body.data.dose = parts[1] || '';
    }
    btn.disabled = true;
    fetch('/api/checkin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) {
        markDone(btn.dataset.key);
        toast('✅ 已记录，不用刷新');
      } else {
        btn.disabled = false;
        alert('保存失败：' + (res.error || '未知错误'));
      }
    }).catch(function () { btn.disabled = false; alert('网络错误，没有保存'); });
  };

  /* ------------------------------------------------ 病人管理状态 */
  var stEl = document.getElementById('stModal');
  var stModal = stEl ? new bootstrap.Modal(stEl) : null;

  window.openStatusModal = function (btn) {
    if (!stModal) return;
    var d;
    try {
      d = JSON.parse(btn.dataset.patient);
    } catch (e) {
      alert('病人信息读取失败');
      return;
    }
    document.getElementById('stPatientId').value = d.id;
    document.getElementById('stPatientName').textContent = d.name || '';
    document.getElementById('stCurrent').textContent = d.status || '在照护';
    document.getElementById('stNew').value = d.status || '在照护';
    document.getElementById('stNote').value = '';
    stModal.show();
  };

  window.submitStatus = function () {
    var id = Number(document.getElementById('stPatientId').value);
    var st = document.getElementById('stNew').value;
    var note = document.getElementById('stNote').value.trim();
    fetch('/api/patient/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: id, status: st, note: note })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) {
        alert('保存失败：' + (res.error || '未知错误'));
        return;
      }
      if (!res.changed) {
        stModal.hide();
        alert('状态没变，没有改动。');
        return;
      }
      location.reload();
    }).catch(function () { alert('网络错误，状态没有保存'); });
  };

  /* ------------------------------------------------ 用药时间表 */
  var mdEl = document.getElementById('medModal');
  var medModal = mdEl ? new bootstrap.Modal(mdEl) : null;

  window.openMedNew = function () {
    if (!medModal) return;
    document.getElementById('mdTitle').textContent = '＋ 添加药品';
    document.getElementById('mdId').value = '';
    document.getElementById('mdName').value = '';
    document.getElementById('mdDose').value = '';
    document.getElementById('mdForm').value = '片';
    document.getElementById('mdTimes').value = '';
    document.getElementById('mdUsage').value = '';
    document.getElementById('mdPurpose').value = '';
    document.getElementById('mdNote').value = '';
    medModal.show();
  };

  window.openMedEdit = function (btn) {
    if (!medModal) return;
    var d;
    try { d = JSON.parse(btn.dataset.med); }
    catch (e) { alert('数据读取失败'); return; }
    document.getElementById('mdTitle').textContent = '✏️ 编辑药品';
    document.getElementById('mdId').value = d.id;
    document.getElementById('mdName').value = d.med_name || '';
    document.getElementById('mdDose').value = d.dose || '';
    document.getElementById('mdForm').value = d.form || '';
    document.getElementById('mdTimes').value = d.times || '';
    document.getElementById('mdUsage').value = d.usage_txt || '';
    document.getElementById('mdPurpose').value = d.purpose || '';
    document.getElementById('mdNote').value = d.note || '';
    medModal.show();
  };

  window.submitMed = function () {
    var id = document.getElementById('mdId').value;
    if (!val('mdName')) { alert('药名必填'); return; }
    var body = {
      id: id ? Number(id) : undefined,
      patient_id: Number(document.getElementById('mdPatient').value),
      med_name: val('mdName'),
      dose: val('mdDose'),
      form: val('mdForm'),
      times: val('mdTimes'),
      usage_txt: val('mdUsage'),
      purpose: val('mdPurpose'),
      note: val('mdNote')
    };
    var url = id ? '/api/med/schedule/update' : '/api/med/schedule';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) { medModal.hide(); location.reload(); }
      else alert('保存失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有保存'); });
  };

  window.toggleMed = function (id) {
    fetch('/api/med/schedule/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('操作失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误'); });
  };

  window.delMed = function (id) {
    if (!confirm('删除这条药品时间表？已经吃过的打卡记录不受影响。')) return;
    fetch('/api/med/schedule/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误'); });
  };

  /* ------------------------------------------------ 体征记录 */
  var vtEl = document.getElementById('vtModal');
  var vtModal = vtEl ? new bootstrap.Modal(vtEl) : null;

  window.openVitals = function () {
    if (!vtModal) return;
    document.getElementById('vtTitle').textContent = '＋ 记录体征';
    document.getElementById('vtId').value = '';
    var n = new Date();
    document.getElementById('vtTime').value =
      ('0' + n.getHours()).slice(-2) + ':' + ('0' + n.getMinutes()).slice(-2);
    ['bp_high', 'bp_low', 'hr', 'temp', 'spo2', 'sugar', 'weight', 'vtNote'].forEach(function (id) {
      setVal(id, '');
    });
    vtModal.show();
  };

  window.openVitalsEdit = function (btn) {
    if (!vtModal) return;
    var d;
    try { d = JSON.parse(btn.dataset.vitals); }
    catch (e) { alert('数据读取失败'); return; }
    document.getElementById('vtTitle').textContent = '✏️ 编辑体征';
    document.getElementById('vtId').value = d.id;
    document.getElementById('vtDay').value = d.day || todayISO();
    document.getElementById('vtTime').value = d.time || '';
    ['bp_high', 'bp_low', 'hr', 'temp', 'spo2', 'sugar', 'weight'].forEach(function (id) {
      setVal(id, d[id]);
    });
    setVal('vtNote', d.note || '');
    vtModal.show();
  };

  window.submitVitals = function () {
    var body = {
      patient_id: Number(document.getElementById('vtPatient').value),
      day: val('vtDay') || todayISO(),
      time: val('vtTime'),
      bp_high: num('bp_high'), bp_low: num('bp_low'), hr: num('hr'),
      temp: num('temp'), spo2: num('spo2'), sugar: num('sugar'),
      weight: num('weight'), note: val('vtNote')
    };
    fetch('/api/vitals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) { vtModal.hide(); location.reload(); }
      else alert('保存失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有保存'); });
  };

  window.delVitals = function (id) {
    if (!confirm('删除这条体征记录？')) return;
    fetch('/api/vitals/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误'); });
  };

  /* ------------------------------------------------ 医疗档案 */
  var mcEl = document.getElementById('mcModal');
  var mcModal = mcEl ? new bootstrap.Modal(mcEl) : null;

  window.openMedRecNew = function () {
    if (!mcModal) return;
    document.getElementById('mcTitle').textContent = '＋ 新增就诊记录';
    document.getElementById('mcId').value = '';
    document.getElementById('mcKind').value = '门诊';
    document.getElementById('mcHappen').value = todayISO();
    document.getElementById('mcNext').value = '';
    document.getElementById('mcHospital').value = '';
    document.getElementById('mcDoctor').value = '';
    document.getElementById('mcSummary').value = '';
    document.getElementById('mcNote').value = '';
    mcModal.show();
  };

  window.openMedRecEdit = function (btn) {
    if (!mcModal) return;
    var d;
    try { d = JSON.parse(btn.dataset.rec); }
    catch (e) { alert('数据读取失败'); return; }
    document.getElementById('mcTitle').textContent = '✏️ 编辑就诊记录';
    document.getElementById('mcId').value = d.id;
    document.getElementById('mcKind').value = d.kind || '门诊';
    document.getElementById('mcHappen').value = d.happen_date || '';
    document.getElementById('mcNext').value = d.next_due || '';
    document.getElementById('mcHospital').value = d.hospital || '';
    document.getElementById('mcDoctor').value = d.doctor || '';
    document.getElementById('mcSummary').value = d.summary || '';
    document.getElementById('mcNote').value = d.note || '';
    mcModal.show();
  };

  window.submitMedRec = function () {
    var id = document.getElementById('mcId').value;
    var body = {
      id: id ? Number(id) : undefined,
      patient_id: Number(document.getElementById('mcPatient').value),
      kind: val('mcKind'), happen_date: val('mcHappen'), next_due: val('mcNext'),
      hospital: val('mcHospital'), doctor: val('mcDoctor'),
      summary: val('mcSummary'), note: val('mcNote')
    };
    var url = id ? '/api/medical_record/update' : '/api/medical_record';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) { mcModal.hide(); location.reload(); }
      else alert('保存失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有保存'); });
  };

  window.delMedRec = function (id) {
    if (!confirm('删除这条就诊记录？')) return;
    fetch('/api/medical_record/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误'); });
  };

  /* ------------------------------------------------ 照护日记 */
  var deEl = document.getElementById('diaryEditModal');
  var deModal = deEl ? new bootstrap.Modal(deEl) : null;

  window.openDiaryEdit = function (btn) {
    if (!deModal) return;
    var d;
    try { d = JSON.parse(btn.dataset.diary); }
    catch (e) { alert('日记数据读取失败'); return; }
    document.getElementById('deId').value = d.id;
    document.getElementById('deDay').value = d.day || todayISO();
    document.getElementById('deMood').value = d.mood || '';
    document.getElementById('dePlace').value = d.place || '';
    document.getElementById('deTitle').value = d.title || '';
    document.getElementById('deContent').value = d.content || '';
    deModal.show();
  };

  window.submitDiaryEdit = function () {
    var body = {
      id: Number(document.getElementById('deId').value),
      day: document.getElementById('deDay').value,
      mood: document.getElementById('deMood').value,
      place: document.getElementById('dePlace').value.trim(),
      title: document.getElementById('deTitle').value.trim(),
      content: document.getElementById('deContent').value.trim()
    };
    fetch('/api/diary/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) { deModal.hide(); location.reload(); }
      else alert('保存失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有保存'); });
  };

  window.delMedia = function (id) {
    if (!confirm('删掉这个附件？文件会从硬盘上一并删除。')) return;
    fetch('/api/diary/media/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有删除'); });
  };

  /* ------------------------------------------------ 记账 */
  var exEl = document.getElementById('exModal');
  var exModal = exEl ? new bootstrap.Modal(exEl) : null;

  function exNumOr(v) { return v === '' || v === null ? null : Number(v); }

  window.exTip = function () {
    var sel = document.getElementById('exCategory');
    var box = document.getElementById('exTipBox');
    if (!sel || !box) return;
    var o = sel.options[sel.selectedIndex];
    box.textContent = o ? (o.dataset.tip || '') : '';
  };

  window.openExpenseNew = function () {
    if (!exModal) return;
    document.getElementById('exTitle').textContent = '＋ 记一笔';
    document.getElementById('exId').value = '';
    document.getElementById('exDay').value = todayISO();
    document.getElementById('exAmount').value = '';
    document.getElementById('exCategory').value = '护工工资';
    document.getElementById('exItem').value = '';
    document.getElementById('exQty').value = '';
    document.getElementById('exUnit').value = '';
    document.getElementById('exShop').value = '';
    document.getElementById('exPay').value = '';
    document.getElementById('exNote').value = '';
    exTip();
  };

  window.openExpenseEdit = function (btn) {
    if (!exModal) return;
    var d;
    try { d = JSON.parse(btn.dataset.ex); }
    catch (e) { alert('记录数据读取失败'); return; }
    document.getElementById('exTitle').textContent = '✏️ 编辑消费记录';
    document.getElementById('exId').value = d.id;
    document.getElementById('exDay').value = d.day || todayISO();
    document.getElementById('exAmount').value = (d.amount === null || d.amount === undefined) ? '' : d.amount;
    document.getElementById('exCategory').value = d.category || '护工工资';
    document.getElementById('exItem').value = d.item || '';
    document.getElementById('exQty').value = (d.qty === null || d.qty === undefined) ? '' : d.qty;
    document.getElementById('exUnit').value = d.unit || '';
    document.getElementById('exShop').value = d.shop || '';
    document.getElementById('exPay').value = d.pay_method || '';
    document.getElementById('exNote').value = d.note || '';
    exTip();
    exModal.show();
  };

  window.submitExpense = function () {
    var id = document.getElementById('exId').value;
    var amt = document.getElementById('exAmount').value;
    if (!amt || Number(amt) <= 0) { alert('金额要大于 0'); return; }
    var body = {
      id: id ? Number(id) : undefined,
      patient_id: Number(document.getElementById('exPatientId').value),
      day: document.getElementById('exDay').value,
      amount: Number(amt),
      category: document.getElementById('exCategory').value,
      item: document.getElementById('exItem').value.trim(),
      qty: exNumOr(document.getElementById('exQty').value),
      unit: document.getElementById('exUnit').value.trim(),
      shop: document.getElementById('exShop').value.trim(),
      pay_method: document.getElementById('exPay').value,
      note: document.getElementById('exNote').value.trim()
    };
    var url = id ? '/api/expense/update' : '/api/expense';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) { exModal.hide(); location.reload(); }
      else alert('保存失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有保存'); });
  };

  window.delExpense = function (id) {
    if (!confirm('删除这条消费记录？')) return;
    fetch('/api/expense/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) location.reload();
      else alert('删除失败：' + (res.error || '未知错误'));
    }).catch(function () { alert('网络错误，没有删除'); });
  };

})();
