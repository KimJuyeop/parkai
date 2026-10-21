"use strict";
// parkai 웹 설정 툴 (빌드 없는 순수 JS)

const api = {
  async get(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error(await errText(r));
    return r.json();
  },
  async send(method, path, body) {
    const r = await fetch(path, {
      method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await errText(r));
    return r.json();
  },
};
async function errText(r) {
  try {
    const j = await r.json();
    return Array.isArray(j.detail) ? j.detail.join("\n") : (j.detail || r.statusText);
  } catch { return r.statusText; }
}

// ---------- 공통 ----------
const $ = (sel) => document.querySelector(sel);
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = v;
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
function field(label, input, cls = "") { return h("label", { class: "field " + cls }, h("span", {}, label), input); }
function toast(msg, ms = 2200) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}

const TYPE_COLORS = { normal: "#3b82f6", ev: "#14b8a6", disabled: "#a855f7", compact: "#f59e0b" };
const STATUS_TEXT = {
  ok: "정상", partial: "일부 화면 이상", no_response: "응답 없음", black: "검은 화면",
  blur: "흐림", frozen: "화면 정지", decode_error: "이미지 오류", error: "처리 오류",
};
function statusClass(s) { return s === "ok" ? "ok" : (s === "partial" ? "warn" : (s ? "bad" : "")); }

const state = {
  cfg: null, status: { cameras: {} }, system: null,
  dirty: false, selectedIp: null, tab: "dashboard",
};

function markDirty() {
  state.dirty = true;
  $("#saveBar").classList.remove("hidden");
  $("#saveErrors").textContent = "";
}

async function loadConfig() {
  state.cfg = await api.get("/api/v1/config");
  state.dirty = false;
  $("#saveBar").classList.add("hidden");
}

async function saveConfig() {
  try {
    await api.send("PUT", "/api/v1/config", state.cfg);
    await loadConfig();
    toast("저장했습니다. 워커는 다음 사이클에 반영합니다.");
    renderAll();
  } catch (e) {
    $("#saveErrors").textContent = e.message;
  }
}

// ---------- 탭 ----------
document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => switchTab(b.dataset.tab)));
function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + tab));
  renderAll();
}

function renderHeader() {
  const s = state.system;
  if (!s) return;
  const site = [s.site.name, s.site.board_name].filter(Boolean).join(" / ");
  $("#siteLabel").textContent = site;
  $("#sysLabel").textContent = `v${s.version} · ${s.board_ip} · ${s.board_model}`;
}

function renderAll() {
  renderHeader();
  if (state.tab === "dashboard") renderDashboard();
  if (state.tab === "camera") renderCameraTab();
  if (state.tab === "settings") renderSettings();
}

// ---------- 대시보드 ----------
function renderDashboard() {
  const st = state.status;
  const cams = state.cfg.cameras;
  const bad = cams.filter((c) => st.cameras[c.ip] && st.cameras[c.ip].status !== "ok").length;
  const metric = (label, value) => h("div", { class: "metric" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value));
  $("#metrics").replaceChildren(
    metric("워커", st.running ? "동작 중" : "정지"),
    metric("사이클 시간", st.cycle_sec != null ? st.cycle_sec.toFixed(2) + "초" : "-"),
    metric("카메라", cams.length + "대"),
    metric("이상 카메라", bad + "대"),
    metric("서버 전송", !state.cfg.server.enabled ? "사용 안 함" : (st.server_error ? "오류" : "정상")),
  );
  const t = Date.now();
  $("#camCards").replaceChildren(...cams.map((c) => {
    const cs = st.cameras[c.ip] || {};
    const states = Object.values(cs.states || {});
    const occ = states.filter((v) => v === true).length;
    const empty = states.filter((v) => v === false).length;
    const img = h("img", { src: st.running ? `/api/v1/cameras/${c.ip}/latest?t=${t}` : `/api/v1/cameras/${c.ip}/snapshot?t=${t}`, alt: c.ip });
    img.onerror = () => { img.removeAttribute("src"); };
    return h("div", { class: "card", onclick: () => { state.selectedIp = c.ip; switchTab("camera"); } },
      img,
      h("div", { class: "info" },
        h("strong", {}, c.ip),
        h("span", { class: "muted" }, `칸 ${c.slots.length} · 점유 ${occ} · 빈칸 ${empty}`),
        h("span", { class: "badge " + statusClass(cs.status) }, STATUS_TEXT[cs.status] || (st.running ? "대기" : "워커 정지"))));
  }));
}

// ---------- 카메라 설정 ----------
$("#addCamBtn").addEventListener("click", () => {
  const ip = $("#newCamIp").value.trim();
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) return toast("IP 형식을 확인하세요");
  if (state.cfg.cameras.some((c) => c.ip === ip)) return toast("이미 있는 카메라입니다");
  const profiles = Object.keys(state.cfg.camera_profiles);
  if (!profiles.length) return toast("시스템 설정에서 카메라 프로필을 먼저 만드세요");
  state.cfg.cameras.push({
    ip, port: 80, profile: profiles[0], user: "admin", password: "", controller_ip: null,
    board: state.cfg.site.board_name || null, ref_size: null, enabled: true, slots: [],
  });
  $("#newCamIp").value = "";
  state.selectedIp = ip;
  markDirty();
  renderCameraTab();
});

function renderCameraTab() {
  const cams = state.cfg.cameras;
  if (!state.selectedIp && cams.length) state.selectedIp = cams[0].ip;
  $("#camList").replaceChildren(...cams.map((c) => {
    const cs = state.status.cameras[c.ip];
    return h("li", { class: c.ip === state.selectedIp ? "active" : "", onclick: () => { state.selectedIp = c.ip; renderCameraTab(); } },
      h("span", {}, c.ip, h("span", { class: "muted small" }, `  ${c.slots.length}칸`)),
      h("span", { class: "dot " + statusClass(cs && cs.status) }));
  }));
  const cam = cams.find((c) => c.ip === state.selectedIp);
  if (!cam) { editor.detach(); $("#camEditor").replaceChildren(h("p", { class: "muted" }, "왼쪽에서 카메라를 선택하거나 IP를 입력해 추가하세요.")); return; }
  editor.attach(cam);
}

function refSize(cam) {
  return cam.ref_size || state.cfg.camera_profiles[cam.profile].ref_size;
}
function viewsBBox(cam) {
  const views = state.cfg.camera_profiles[cam.profile].views;
  const [rw, rh] = refSize(cam);
  if (!views.length) return [0, 0, rw, rh];
  const x0 = Math.min(...views.map((v) => v[0])), y0 = Math.min(...views.map((v) => v[1]));
  const x1 = Math.max(...views.map((v) => v[0] + v[2])), y1 = Math.max(...views.map((v) => v[1] + v[3]));
  return [x0, y0, x1 - x0, y1 - y0];
}

// 선분 편집기
const editor = {
  cam: null, img: null, imgSource: "", canvas: null, ctx: null,
  addMode: false, pending: null, hover: null, drag: null, selected: null, showState: false, newType: "normal",
  bbox: [0, 0, 1280, 480], k: 1,

  detach() { this.cam = null; },

  attach(cam) {
    const changed = this.cam !== cam;
    this.cam = cam;
    if (changed) { this.selected = null; this.pending = null; this.addMode = false; }
    this.build();
    if (changed || !this.img) this.loadSnapshot();
    else this.draw();
  },

  build() {
    const cam = this.cam;
    const profiles = Object.keys(state.cfg.camera_profiles);
    const set = (key, conv = (v) => v) => (e) => { cam[key] = conv(e.target.type === "checkbox" ? e.target.checked : e.target.value); markDirty(); };
    const ipInput = h("input", { value: cam.ip, size: 14 });
    ipInput.addEventListener("change", (e) => {
      const v = e.target.value.trim();
      if (state.cfg.cameras.some((c) => c !== cam && c.ip === v)) { toast("이미 있는 IP입니다"); e.target.value = cam.ip; return; }
      cam.ip = v; state.selectedIp = v; markDirty(); renderCameraTab();
    });

    this.canvas = h("canvas", { tabindex: 0 });
    this.ctx = this.canvas.getContext("2d");
    this.bindCanvas();

    const typeSelect = h("select", { onchange: (e) => { this.newType = e.target.value; } },
      ...state.cfg.slot_types.map((t) => h("option", { value: t.id }, t.name)));
    typeSelect.value = this.newType;

    this.srcLabel = h("span", { class: "muted small" }, this.imgSource);
    this.addBtn = h("button", { class: this.addMode ? "on" : "", onclick: () => this.toggleAdd() }, "선 추가");
    this.stateBtn = h("button", { class: this.showState ? "on" : "", onclick: () => { this.showState = !this.showState; this.stateBtn.classList.toggle("on", this.showState); this.draw(); } }, "판정 결과 보기");

    this.table = h("tbody");
    $("#camEditor").replaceChildren(
      h("div", { class: "form-row" },
        field("카메라 IP", ipInput),
        field("포트", h("input", { type: "number", value: cam.port, style: "width:80px", onchange: set("port", Number) })),
        field("프로필", h("select", { onchange: (e) => { cam.profile = e.target.value; markDirty(); this.loadSnapshot(); } },
          ...profiles.map((p) => h("option", { value: p, selected: p === cam.profile }, p)))),
        field("사용자", h("input", { value: cam.user, size: 10, onchange: set("user") })),
        field("비밀번호", h("input", { type: "password", value: cam.password, size: 10, onchange: set("password") })),
        field("담당 보드", h("input", { value: cam.board || "", size: 8, placeholder: "비우면 모든 보드", onchange: set("board", (v) => v || null) })),
        field("컨트롤러 IP", h("input", { value: cam.controller_ip || "", size: 14, onchange: set("controller_ip", (v) => v || null) })),
        field("사용", h("input", { type: "checkbox", checked: cam.enabled, onchange: set("enabled") }), "inline"),
      ),
      h("div", { class: "toolbar" },
        h("button", { onclick: () => this.loadSnapshot() }, "스냅샷 새로고침"),
        this.srcLabel,
        h("span", { class: "spacer" }),
        this.addBtn,
        h("span", { class: "muted small" }, "새 선 종류"), typeSelect,
        this.stateBtn,
        h("button", { class: "danger", onclick: () => this.deleteCamera() }, "카메라 삭제"),
      ),
      h("div", { class: "canvas-wrap" }, this.canvas),
      h("div", { class: "hint" }, "선 추가: 버튼을 누르고 두 점을 클릭 · 끝점을 끌어서 수정 · 선 클릭 후 Delete로 삭제 · Esc 취소 · 최대 12칸"),
      h("table", {}, h("thead", {}, h("tr", {}, ...["번호", "종류", "시작 (x, y)", "끝 (x, y)", "현재 판정", ""].map((t) => h("th", {}, t)))), this.table),
    );
    this.renderTable();
    new ResizeObserver(() => this.resize()).observe(this.canvas.parentElement);
  },

  async loadSnapshot() {
    const cam = this.cam;
    this.srcLabel && (this.srcLabel.textContent = "불러오는 중...");
    try {
      const r = await fetch(`/api/v1/cameras/${cam.ip}/snapshot?t=${Date.now()}`);
      if (!r.ok) throw new Error(await errText(r));
      const src = r.headers.get("X-Parkai-Source");
      const blob = await r.blob();
      const img = new Image();
      img.onload = () => {
        if (this.cam !== cam) return;
        this.img = img;
        const err = r.headers.get("X-Parkai-Error");
        this.imgSource = src === "sample"
          ? "샘플 이미지 (카메라 연결 실패" + (err ? ": " + decodeURIComponent(err) : "") + ")"
          : "카메라 실시간";
        this.srcLabel.textContent = `${this.imgSource} · ${img.naturalWidth}×${img.naturalHeight}`;
        this.resize();
      };
      img.src = URL.createObjectURL(blob);
    } catch (e) {
      this.img = null;
      this.srcLabel.textContent = "스냅샷 실패: " + e.message;
      this.resize();
    }
  },

  resize() {
    if (!this.cam || !this.canvas.isConnected) return;
    this.bbox = viewsBBox(this.cam);
    const w = this.canvas.parentElement.clientWidth;
    this.k = w / this.bbox[2];
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(this.bbox[3] * this.k * dpr);
    this.canvas.style.height = this.bbox[3] * this.k + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  },

  toScreen(p) { return [(p[0] - this.bbox[0]) * this.k, (p[1] - this.bbox[1]) * this.k]; },
  toRef(e) {
    const r = this.canvas.getBoundingClientRect();
    const [rw, rh] = refSize(this.cam);
    const x = Math.round((e.clientX - r.left) / this.k + this.bbox[0]);
    const y = Math.round((e.clientY - r.top) / this.k + this.bbox[1]);
    return [Math.max(0, Math.min(rw, x)), Math.max(0, Math.min(rh, y))];
  },

  slotColor(s) {
    if (this.showState) {
      const st = (state.status.cameras[this.cam.ip] || {}).states || {};
      const v = st[String(s.no)];
      return v === true ? "#16a34a" : v === false ? "#dc2626" : "#9ca3af";
    }
    return TYPE_COLORS[s.type] || "#64748b";
  },

  draw() {
    const ctx = this.ctx, cam = this.cam;
    if (!ctx || !cam) return;
    const W = this.canvas.clientWidth, H = this.bbox[3] * this.k;
    ctx.clearRect(0, 0, W, H);
    if (this.img) {
      const [rw, rh] = refSize(cam);
      const sx = this.img.naturalWidth / rw, sy = this.img.naturalHeight / rh;
      const [bx, by, bw, bh] = this.bbox;
      ctx.drawImage(this.img, bx * sx, by * sy, bw * sx, bh * sy, 0, 0, W, H);
    } else {
      ctx.fillStyle = "#111"; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "#9ca3af"; ctx.font = "14px sans-serif";
      ctx.fillText("스냅샷 없음 - 카메라 주소/인증 또는 샘플 폴더를 확인하세요", 16, 28);
    }
    // 화면 영역 경계
    ctx.setLineDash([6, 4]); ctx.strokeStyle = "rgba(255,255,255,.5)"; ctx.lineWidth = 1;
    for (const v of state.cfg.camera_profiles[cam.profile].views) {
      const [x, y] = this.toScreen([v[0], v[1]]);
      ctx.strokeRect(x + .5, y + .5, v[2] * this.k - 1, v[3] * this.k - 1);
    }
    ctx.setLineDash([]);
    // 칸 선분
    for (const s of cam.slots) {
      const a = this.toScreen(s.line[0]), b = this.toScreen(s.line[1]);
      const sel = this.selected === s;
      const color = this.slotColor(s);
      if (sel) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 10; line(ctx, a, b); }
      ctx.strokeStyle = color; ctx.lineWidth = 6; line(ctx, a, b);
      for (const p of [a, b]) { ctx.fillStyle = "#fff"; dot(ctx, p, 5); ctx.fillStyle = color; dot(ctx, p, 3.5); }
      const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      ctx.font = "bold 14px sans-serif";
      const label = String(s.no);
      ctx.fillStyle = "rgba(0,0,0,.65)"; ctx.fillRect(m[0] + 8, m[1] - 18, ctx.measureText(label).width + 10, 20);
      ctx.fillStyle = "#fff"; ctx.fillText(label, m[0] + 13, m[1] - 3);
    }
    // 추가 중인 선
    if (this.addMode && this.pending) {
      const a = this.toScreen(this.pending);
      ctx.fillStyle = "#facc15"; dot(ctx, a, 5);
      if (this.hover) { ctx.strokeStyle = "#facc15"; ctx.lineWidth = 3; ctx.setLineDash([6, 4]); line(ctx, a, this.toScreen(this.hover)); ctx.setLineDash([]); }
    }
  },

  hitEndpoint(e) {
    const r = this.canvas.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    for (const s of this.cam.slots) for (let i = 0; i < 2; i++) {
      const [x, y] = this.toScreen(s.line[i]);
      if (Math.hypot(px - x, py - y) <= 10) return { slot: s, i };
    }
    return null;
  },
  hitLine(e) {
    const r = this.canvas.getBoundingClientRect();
    const p = [e.clientX - r.left, e.clientY - r.top];
    let best = null, bd = 9;
    for (const s of this.cam.slots) {
      const d = segDist(p, this.toScreen(s.line[0]), this.toScreen(s.line[1]));
      if (d < bd) { bd = d; best = s; }
    }
    return best;
  },

  bindCanvas() {
    const c = this.canvas;
    c.addEventListener("mousedown", (e) => {
      c.focus();
      if (this.addMode) {
        const p = this.toRef(e);
        if (!this.pending) { this.pending = p; }
        else { this.addSlot(this.pending, p); this.pending = null; }
        this.draw(); return;
      }
      const hit = this.hitEndpoint(e);
      if (hit) { this.drag = hit; this.selected = hit.slot; }
      else { this.selected = this.hitLine(e); }
      this.renderTable(); this.draw();
    });
    c.addEventListener("mousemove", (e) => {
      if (this.drag) {
        this.drag.slot.line[this.drag.i] = this.toRef(e);
        markDirty(); this.draw(); this.renderTable(); return;
      }
      if (this.addMode) { this.hover = this.toRef(e); this.draw(); return; }
      c.style.cursor = this.hitEndpoint(e) ? "move" : (this.hitLine(e) ? "pointer" : "crosshair");
    });
    window.addEventListener("mouseup", () => { this.drag = null; });
    c.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { this.pending = null; if (this.addMode) this.toggleAdd(); this.draw(); }
      if ((e.key === "Delete" || e.key === "Backspace") && this.selected) { this.removeSlot(this.selected); e.preventDefault(); }
    });
  },

  toggleAdd() {
    this.addMode = !this.addMode; this.pending = null;
    this.addBtn.classList.toggle("on", this.addMode);
    this.canvas.focus(); this.draw();
  },

  addSlot(a, b) {
    const used = new Set(this.cam.slots.map((s) => s.no));
    let no = 1; while (used.has(no)) no++;
    if (no > 12) { toast("카메라당 최대 12칸입니다"); return; }
    const s = { no, type: this.newType, line: [a, b], name: "", judge: null };
    this.cam.slots.push(s);
    this.cam.slots.sort((x, y) => x.no - y.no);
    this.selected = s;
    markDirty(); this.renderTable(); renderCamListOnly();
  },

  removeSlot(s) {
    this.cam.slots = this.cam.slots.filter((x) => x !== s);
    if (this.selected === s) this.selected = null;
    markDirty(); this.renderTable(); this.draw(); renderCamListOnly();
  },

  deleteCamera() {
    if (!confirm(`${this.cam.ip} 카메라를 삭제할까요? (저장해야 반영됩니다)`)) return;
    state.cfg.cameras = state.cfg.cameras.filter((c) => c !== this.cam);
    state.selectedIp = null; this.cam = null;
    markDirty(); renderCameraTab();
  },

  renderTable() {
    if (!this.table) return;
    const st = (state.status.cameras[this.cam.ip] || {}).states || {};
    this.table.replaceChildren(...this.cam.slots.map((s) => {
      const no = h("input", { type: "number", min: 1, max: 12, value: s.no });
      no.addEventListener("change", (e) => {
        const v = Number(e.target.value);
        if (v < 1 || v > 12 || this.cam.slots.some((x) => x !== s && x.no === v)) { toast("1~12 사이의 겹치지 않는 번호"); e.target.value = s.no; return; }
        s.no = v; this.cam.slots.sort((x, y) => x.no - y.no); markDirty(); this.renderTable(); this.draw();
      });
      const type = h("select", { onchange: (e) => { s.type = e.target.value; markDirty(); this.draw(); } },
        ...state.cfg.slot_types.map((t) => h("option", { value: t.id, selected: t.id === s.type }, t.name)));
      const v = st[String(s.no)];
      return h("tr", { class: this.selected === s ? "selected" : "", onclick: (e) => { if (e.target.tagName === "TD") { this.selected = s; this.renderTable(); this.draw(); } } },
        h("td", {}, no), h("td", {}, type),
        h("td", {}, `${s.line[0][0]}, ${s.line[0][1]}`), h("td", {}, `${s.line[1][0]}, ${s.line[1][1]}`),
        h("td", {}, v === true ? h("span", { class: "badge bad" }, "차량 있음") : v === false ? h("span", { class: "badge ok" }, "빈칸") : h("span", { class: "muted" }, "-")),
        h("td", {}, h("button", { class: "danger", onclick: () => this.removeSlot(s) }, "삭제")));
    }));
  },
};

function renderCamListOnly() {
  const cur = editor.cam;
  document.querySelectorAll("#camList li").forEach((li, i) => {
    const c = state.cfg.cameras[i];
    if (c && c === cur) li.firstChild.lastChild.textContent = `  ${c.slots.length}칸`;
  });
}
function line(ctx, a, b) { ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
function dot(ctx, p, r) { ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, Math.PI * 2); ctx.fill(); }
function segDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

// ---------- 시스템 설정 ----------
function renderSettings() {
  const cfg = state.cfg;
  const bind = (obj, key, conv = (v) => v) => (e) => {
    obj[key] = conv(e.target.type === "checkbox" ? e.target.checked : e.target.value); markDirty();
  };
  const num = (v) => Number(v);
  const sec = (title, note, ...body) => h("div", { class: "settings-section" }, h("h3", {}, title), note ? h("p", { class: "note" }, note) : null, ...body);

  // 기본 정보
  const basic = sec("기본 정보", "보드명은 현장 파일에서 카메라 배정 기준으로 씁니다. 보드 IP를 비우면 자동으로 읽습니다.",
    h("div", { class: "form-row" },
      field("현장명", h("input", { value: cfg.site.name, onchange: bind(cfg.site, "name") })),
      field("보드명", h("input", { value: cfg.site.board_name, onchange: bind(cfg.site, "board_name") })),
      field("전송용 보드 IP", h("input", { value: cfg.network.board_ip || "", placeholder: "자동", onchange: bind(cfg.network, "board_ip", (v) => v || null) })),
      field("사이클 목표(초)", h("input", { type: "number", step: "1", value: cfg.runtime.cycle_target_sec, style: "width:90px", onchange: bind(cfg.runtime, "cycle_target_sec", num) })),
    ));

  // 서버
  const result = h("pre", { class: "result hidden" });
  const server = sec("서버 전송", "POST {서버 주소}{경로} 로 카메라마다 매 사이클 전송합니다. 전송 테스트는 저장된 설정으로 보냅니다.",
    h("div", { class: "form-row" },
      field("사용", h("input", { type: "checkbox", checked: cfg.server.enabled, onchange: bind(cfg.server, "enabled") }), "inline"),
      field("서버 주소", h("input", { value: cfg.server.base_url, size: 28, placeholder: "http://192.168.0.197:8000", onchange: bind(cfg.server, "base_url") })),
      field("경로", h("input", { value: cfg.server.path, size: 22, onchange: bind(cfg.server, "path") })),
      field("타임아웃(초)", h("input", { type: "number", step: "0.5", value: cfg.server.timeout_sec, style: "width:80px", onchange: bind(cfg.server, "timeout_sec", num) })),
      h("button", { onclick: async () => {
        if (state.dirty) return toast("먼저 저장하세요");
        result.classList.remove("hidden"); result.textContent = "보내는 중...";
        try { result.textContent = JSON.stringify(await api.send("POST", "/api/v1/server/test", {}), null, 2); }
        catch (e) { result.textContent = e.message; }
      } }, "전송 테스트"),
    ), result);

  // 판정
  const det = cfg.detection;
  const custom = h("div", { class: "form-row" + (det.preset === "custom" ? "" : " hidden") },
    field("판정 방식", h("select", { onchange: bind(det.judge, "mode") },
      h("option", { value: "intersect", selected: det.judge.mode === "intersect" }, "선에 닿으면 점유"),
      h("option", { value: "cover_ratio", selected: det.judge.mode === "cover_ratio" }, "덮임 비율"))),
    field("덮임 비율 기준", h("input", { type: "number", step: "0.05", value: det.judge.cover_ratio, style: "width:80px", onchange: bind(det.judge, "cover_ratio", num) })),
    field("공유 칸 기준", h("input", { type: "number", step: "0.05", value: det.judge.cover_ratio_shared, style: "width:80px", onchange: bind(det.judge, "cover_ratio_shared", num) })),
    field("연속 일치 횟수(N)", h("input", { type: "number", min: 1, value: det.stabilize.count, style: "width:80px", onchange: bind(det.stabilize, "count", num) })),
  );
  const carConf = det.classes.car || (det.classes.car = { enabled: true, conf: 0.45 });
  const judge = sec("판정", "legacy: 선에 닿으면 점유 + 매 사이클 그대로 (기존 Jetson과 동일). standard: 덮임 비율 + 연속 2회 일치.",
    h("div", { class: "form-row" },
      field("프리셋", h("select", { onchange: (e) => { det.preset = e.target.value; custom.classList.toggle("hidden", det.preset !== "custom"); markDirty(); } },
        ...["legacy", "standard", "custom"].map((p) => h("option", { value: p, selected: det.preset === p }, p)))),
      field("차량 신뢰도", h("input", { type: "number", step: "0.05", min: 0, max: 1, value: carConf.conf, style: "width:80px", onchange: bind(carConf, "conf", num) })),
      field("모델", h("input", { value: det.model || "", placeholder: "없음", size: 18, onchange: bind(det, "model", (v) => v || null) })),
    ), custom);

  // 주차 종류
  const typeRows = h("tbody");
  const renderTypes = () => typeRows.replaceChildren(...cfg.slot_types.map((t) => h("tr", {},
    h("td", {}, t.id),
    h("td", {}, h("input", { value: t.name, size: 10, onchange: bind(t, "name") })),
    h("td", {}, h("input", { value: t.color_available, size: 10, onchange: bind(t, "color_available") })),
    h("td", {}, h("input", { value: t.color_full, size: 10, onchange: bind(t, "color_full") })),
    h("td", {}, h("button", { class: "danger", onclick: () => {
      if (cfg.cameras.some((c) => c.slots.some((s) => s.type === t.id))) return toast("사용 중인 종류는 삭제할 수 없습니다");
      cfg.slot_types = cfg.slot_types.filter((x) => x !== t); markDirty(); renderTypes();
    } }, "삭제")))));
  renderTypes();
  const newTypeId = h("input", { placeholder: "id (영문)", size: 10 });
  const types = sec("주차 종류와 만공등 색", "만공등: 설정된 칸 중 빈칸이 있으면 '빈칸 색', 모두 차면 '만차 색'. 색 값은 카메라 사양 확인 후 맞춥니다.",
    h("table", {}, h("thead", {}, h("tr", {}, ...["id", "이름", "빈칸 색", "만차 색", ""].map((x) => h("th", {}, x)))), typeRows),
    h("div", { class: "toolbar" }, newTypeId, h("button", { onclick: () => {
      const id = newTypeId.value.trim();
      if (!/^[a-z0-9_]+$/.test(id) || cfg.slot_types.some((t) => t.id === id)) return toast("영문 소문자/숫자, 중복 불가");
      cfg.slot_types.push({ id, name: id, color_available: "green", color_full: "red" }); newTypeId.value = ""; markDirty(); renderTypes();
    } }, "종류 추가")));

  // 카메라 프로필
  const profBox = h("div");
  const renderProfiles = () => profBox.replaceChildren(...Object.entries(cfg.camera_profiles).map(([name, p]) => h("div", { class: "form-row" },
    field("이름", h("input", { value: name, size: 14, disabled: true })),
    field("스냅샷 URL ({ip} 또는 {ipaddress}, {port})", h("input", { value: p.snapshot_url, size: 46, onchange: bind(p, "snapshot_url") })),
    field("인증", h("select", { onchange: bind(p, "auth") }, ...["none", "basic", "digest"].map((a) => h("option", { value: a, selected: p.auth === a }, a)))),
    field("기준 해상도", h("input", { value: p.ref_size.join("x"), size: 9, onchange: (e) => { p.ref_size = e.target.value.split("x").map(Number); markDirty(); } })),
    field("화면 영역 (x,y,w,h; ...)", h("input", { value: p.views.map((v) => v.join(",")).join("; "), size: 30, onchange: (e) => {
      p.views = e.target.value.split(";").map((s) => s.trim()).filter(Boolean).map((s) => s.split(",").map(Number)); markDirty();
    } })),
    h("button", { class: "danger", onclick: () => {
      if (cfg.cameras.some((c) => c.profile === name)) return toast("사용 중인 프로필은 삭제할 수 없습니다");
      delete cfg.camera_profiles[name]; markDirty(); renderProfiles();
    } }, "삭제"))));
  renderProfiles();
  const newProf = h("input", { placeholder: "프로필 이름", size: 14 });
  const profiles = sec("카메라 프로필", "카메라 기종별 스냅샷 주소와 인증 방식, 추론할 화면 영역입니다.",
    profBox,
    h("div", { class: "toolbar" }, newProf, h("button", { onclick: () => {
      const n = newProf.value.trim();
      if (!n || cfg.camera_profiles[n]) return toast("이름을 확인하세요");
      cfg.camera_profiles[n] = { snapshot_url: "http://{ip}:{port}/snapshot.jpg", auth: "digest", ref_size: [1280, 960], views: [[0, 0, 640, 480], [640, 0, 640, 480]] };
      newProf.value = ""; markDirty(); renderProfiles();
    } }, "프로필 추가")));

  // 설정 파일
  const fileInput = h("input", { type: "file", accept: ".json", onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      if (!confirm("가져온 설정으로 전체를 덮어씁니다. 계속할까요?")) return;
      await api.send("PUT", "/api/v1/config", data); await loadConfig(); toast("가져왔습니다"); renderAll();
    } catch (err) { toast("가져오기 실패: " + err.message, 5000); }
    e.target.value = "";
  } });
  const files = sec("설정 파일", "현장 파일(카메라 전체)을 내보내거나 가져옵니다. 가져오면 즉시 저장됩니다.",
    h("div", { class: "toolbar" },
      h("a", { href: "/api/v1/config/export" }, h("button", {}, "내보내기 (비밀번호 제외)")),
      h("a", { href: "/api/v1/config/export?passwords=true" }, h("button", {}, "내보내기 (비밀번호 포함)")),
      h("span", { class: "muted" }, "가져오기"), fileInput));

  $("#settingsForm").replaceChildren(basic, server, judge, types, profiles, files);
}

// ---------- 시작 ----------
$("#saveBtn").addEventListener("click", saveConfig);
$("#revertBtn").addEventListener("click", async () => { await loadConfig(); editor.cam = null; renderAll(); });
window.addEventListener("beforeunload", (e) => { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });

async function pollStatus() {
  try {
    state.status = await api.get("/api/v1/status");
    // 워커가 돌 때만 갱신 (정지 중에는 카메라 스냅샷을 반복 요청하지 않도록)
    if (state.tab === "dashboard" && !state.dirty && state.status.running) renderDashboard();
    if (state.tab === "camera" && editor.cam) { editor.renderTable(); if (editor.showState) editor.draw(); }
  } catch { /* 다음 주기에 다시 */ }
}

(async function init() {
  try {
    [state.system] = await Promise.all([api.get("/api/v1/system"), loadConfig()]);
    await pollStatus();
    renderAll();
    setInterval(pollStatus, 3000);
  } catch (e) {
    document.querySelector("main").replaceChildren(h("p", { class: "error" }, "서버에 연결하지 못했습니다: " + e.message));
  }
})();
