"use strict";
// parkai 웹 설정 툴 (빌드 없는 순수 JS)

// ================= 공통 =================
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
function select(options, value, onchange) {
  return h("select", { onchange: (e) => onchange(e.target.value) },
    ...options.map(([v, label]) => h("option", { value: v, selected: v === value }, label)));
}
function toast(msg, ms = 2400) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}
function ago(iso) {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return s < 60 ? `${s}초 전` : s < 3600 ? `${Math.floor(s / 60)}분 전` : `${Math.floor(s / 3600)}시간 전`;
}
function fmtMs(s) { return s == null ? "-" : Math.round(s * 1000) + "ms"; }

// ================= 상수 =================
const STATUS_TEXT = {
  ok: "정상", partial: "일부 화면 이상", no_response: "응답 없음", black: "검은 화면",
  blur: "흐림", frozen: "화면 정지", decode_error: "이미지 오류", error: "처리 오류",
};
const COLOR_LABELS = { green: "녹색", blue: "파란색", yellow: "노란색", white: "흰색", purple: "보라색", cyan: "하늘색" };
const COLOR_HEX = { green: "#16a34a", blue: "#2563eb", yellow: "#eab308", white: "#e5e7eb", purple: "#9333ea", cyan: "#06b6d4" };
const TYPE_LINE_COLORS = { normal: "#3b82f6", compact: "#f59e0b", disabled: "#a855f7", ev: "#14b8a6" };
const PRESETS = [["legacy", "기존 방식 (Jetson과 동일)"], ["standard", "개선 방식"], ["custom", "직접 설정"]];
const AUTH = [["none", "인증 없음"], ["basic", "기본 (Basic)"], ["digest", "다이제스트 (Digest)"]];

function statusClass(s) { return s === "ok" ? "ok" : (s === "partial" ? "warn" : (s ? "bad" : "")); }
function typeName(id) { return (state.cfg.slot_types.find((t) => t.id === id) || {}).name || id; }

// ================= 상태 =================
const state = {
  cfg: null, status: { cameras: {} }, system: null,
  dirty: false, selectedIp: null, tab: "dashboard",
};

function markDirty() {
  state.dirty = true;
  $("#saveBar").classList.remove("hidden");
  $("#saveErrors").textContent = "";
  renderSidebar();
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
    state.system = await api.get("/api/v1/system");
    toast("저장했습니다. 다음 사이클부터 반영됩니다.");
    renderAll();
  } catch (e) {
    $("#saveErrors").textContent = e.message;
  }
}

// 이 보드가 처리하는 카메라인지
function camRole(c) {
  if (!c.enabled) return "off";
  const me = state.cfg.site.board_name;
  if (c.board && me && c.board !== me) return "other";
  return "mine";
}
function workerAlive() {
  const st = state.status;
  if (!st.running || !st.updated_at) return false;
  const age = (Date.now() - new Date(st.updated_at).getTime()) / 1000;
  return age < Math.max(30, state.cfg.runtime.cycle_target_sec * 3);
}
function camBadge(c) {
  const role = camRole(c);
  if (role === "off") return ["", "사용 안 함"];
  if (role === "other") return ["", `다른 보드 담당 (${c.board})`];
  if (!workerAlive()) return ["", "판정 정지"];
  const cs = state.status.cameras[c.ip] || {};
  return [statusClass(cs.status), STATUS_TEXT[cs.status] || "대기"];
}

// ================= 메뉴 =================
document.querySelectorAll(".menu button").forEach((b) =>
  b.addEventListener("click", () => switchTab(b.dataset.tab)));
function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".menu button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + tab));
  renderAll();
}
function renderAll() {
  renderSidebar();
  if (state.tab === "dashboard") { dash.key = ""; renderDashboard(); }
  if (state.tab === "camera") renderCameraTab();
  if (state.tab === "settings") renderSettings();
}

// ================= 좌측 패널 =================
function renderSidebar() {
  const s = state.system, cfg = state.cfg;
  if (!s || !cfg) return;
  $("#siteLabel").textContent = [cfg.site.name, cfg.site.board_name].filter(Boolean).join(" · ") || "현장 이름 미설정";
  $("#sysLabel").textContent = `v${s.version} · 보드 IP ${s.board_ip}`;

  const alive = workerAlive(), st = state.status;
  const mine = cfg.cameras.filter((c) => camRole(c) === "mine");
  const okCams = mine.filter((c) => (st.cameras[c.ip] || {}).status === "ok").length;
  const sum = (label, value, cls = "", wide = false) =>
    h("div", { class: "sum" + (wide ? " wide" : "") }, h("div", { class: "label" }, label), h("div", { class: "value " + cls }, value));
  $("#summary").replaceChildren(
    sum("판정", alive ? "동작 중" : "정지", alive ? "good" : "bad"),
    sum("사이클", alive && st.cycle_sec != null ? st.cycle_sec.toFixed(1) + "초" : "-"),
    sum("카메라 정상", alive ? `${okCams} / ${mine.length}` : "-", "", true),
    ...(cfg.server.enabled ? [sum("서버 전송", st.server_error ? "오류" : "정상", st.server_error ? "bad" : "good", true)] : []),
  );

  $("#camCount").textContent = `${cfg.cameras.length}`;
  $("#camList").replaceChildren(...cfg.cameras.map((c) => {
    const role = camRole(c);
    const cs = st.cameras[c.ip] || {};
    const dot = role !== "mine" || !alive ? "" : statusClass(cs.status);
    return h("li", {
      class: (c.ip === state.selectedIp && state.tab === "camera" ? "active " : "") + (role !== "mine" ? "off" : ""),
      title: camBadge(c)[1],
      onclick: () => onCameraClick(c.ip),
    }, h("span", { class: "dot " + dot }), h("span", { class: "ip" }, c.ip), h("span", { class: "cnt" }, `${c.slots.length}칸`));
  }));
}
function onCameraClick(ip) {
  if (state.tab === "dashboard") return openModal(ip);
  state.selectedIp = ip;
  $("#addCamPanel").classList.add("hidden");
  if (state.tab !== "camera") switchTab("camera"); else renderAll();
}
$("#openAddCam").addEventListener("click", () => {
  if (state.tab !== "camera") switchTab("camera");
  renderAddPanel();
});

// ================= 모니터링 =================
// 카드는 카메라 목록이 바뀔 때만 다시 만들고, 이미지/상태는 제자리에서 갱신한다 (깜빡임 방지).
const dash = { key: "", tiles: new Map(), modalIp: null };

function swapImage(img, url, onFail) {
  const pre = new Image();
  pre.onload = () => { img.src = pre.src; img.classList.remove("empty"); onFail && onFail(null); };
  pre.onerror = () => onFail && onFail("영상 없음");
  pre.src = url;
}

function renderDashboard() {
  const cams = state.cfg.cameras;
  const alive = workerAlive();
  const st = state.status;
  $("#dashNotice").classList.toggle("hidden", alive || !cams.length);

  if (!cams.length) {
    dash.key = "";
    $("#camCards").className = "grid";
    $("#camCards").replaceChildren(h("div", { class: "empty-state" },
      h("p", {}, "등록된 카메라가 없습니다."),
      h("button", { class: "primary", onclick: () => { switchTab("camera"); renderAddPanel(); } }, "카메라 추가하기")));
    return;
  }

  const key = cams.map((c) => c.ip + ":" + c.profile).join("|");
  if (key !== dash.key) {
    dash.key = key;
    dash.tiles.clear();
    $("#camCards").className = "grid" + (cams.length <= 2 ? " few" : "");
    $("#camCards").replaceChildren(...cams.map((c) => {
      const [, , bw, bh] = viewsBBox(c);
      const img = h("img", { class: "empty", alt: "" });
      const ph = h("div", { class: "placeholder" }, "불러오는 중...");
      const badge = h("span", { class: "badge" });
      const chips = h("div", { class: "chips" });
      const meta = h("div", { class: "meta" });
      const err = h("div", { class: "err" });
      const tile = h("div", { class: "card" },
        h("div", { class: "card-img", style: `aspect-ratio:${bw}/${bh}`, onclick: () => openModal(c.ip) },
          img, ph, h("div", { class: "overlay" }, h("strong", {}, c.ip), badge)),
        h("div", { class: "card-body" },
          chips, err,
          h("div", { class: "card-foot" }, meta,
            h("button", { class: "ghost", onclick: () => { state.selectedIp = c.ip; switchTab("camera"); } }, "설정"))));
      dash.tiles.set(c.ip, { img, ph, badge, chips, meta, err, shown: false });
      return tile;
    }));
  }

  const t = Date.now();
  for (const c of cams) {
    const tile = dash.tiles.get(c.ip);
    if (!tile) continue;
    const role = camRole(c);
    const cs = st.cameras[c.ip] || {};
    const live = alive && role === "mine";
    const states = live ? (cs.states || {}) : {};
    const [bcls, btxt] = camBadge(c);
    tile.badge.className = "badge " + bcls;
    tile.badge.textContent = btxt;
    const setPh = (msg) => { tile.ph.textContent = msg || ""; tile.ph.classList.toggle("hidden", !msg); };
    if (live) {
      swapImage(tile.img, `/api/v1/cameras/${c.ip}/latest?t=${t}`, (e) => {
        if (!e) setPh(null);
        else if (tile.img.classList.contains("empty")) setPh(cs.error || "영상 없음");
      });
    } else if (!tile.shown) {  // 판정하지 않는 카메라는 스냅샷을 한 번만
      tile.shown = true;
      swapImage(tile.img, `/api/v1/cameras/${c.ip}/snapshot?crop=1&t=${t}`, (e) => setPh(e ? "카메라 연결 안 됨" : null));
    }
    tile.chips.replaceChildren(...(c.slots.length ? c.slots.map((s) => {
      const v = states[String(s.no)];
      return h("span", { class: v == null ? "chip" : v ? "chip occ" : "chip free", title: `${s.no}번 · ${typeName(s.type)}` }, String(s.no));
    }) : [h("span", { class: "muted small" }, "설정된 칸 없음")]));
    tile.meta.textContent = live && cs.updated_at ? `갱신 ${ago(cs.updated_at)}` : "";
    tile.err.textContent = live && cs.error ? cs.error : "";
  }
  if (dash.modalIp) refreshModal();
}

function openModal(ip) { dash.modalIp = ip; $("#modal").classList.remove("hidden"); refreshModal(); }
function closeModal() { dash.modalIp = null; $("#modal").classList.add("hidden"); }
$("#modalEdit").addEventListener("click", () => { state.selectedIp = dash.modalIp; closeModal(); switchTab("camera"); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && dash.modalIp) closeModal(); });
function refreshModal() {
  const ip = dash.modalIp;
  const c = state.cfg.cameras.find((x) => x.ip === ip);
  if (!c) return closeModal();
  const cs = state.status.cameras[ip] || {};
  const live = workerAlive() && camRole(c) === "mine";
  const [bcls, btxt] = camBadge(c);
  $("#modalTitle").textContent = ip;
  $("#modalStatus").className = "badge " + bcls;
  $("#modalStatus").textContent = btxt;
  swapImage($("#modalImg"), live ? `/api/v1/cameras/${ip}/latest?t=${Date.now()}` : `/api/v1/cameras/${ip}/snapshot?crop=1&t=${Date.now()}`);
  const states = live ? (cs.states || {}) : {};
  $("#modalSlots").replaceChildren(...c.slots.map((s) => {
    const v = states[String(s.no)];
    return h("span", { class: v == null ? "chip" : v ? "chip occ" : "chip free" }, `${s.no}번 ${typeName(s.type)}`);
  }));
  const tm = cs.timings || {};
  $("#modalInfo").textContent = live
    ? `갱신 ${ago(cs.updated_at)} · 수신 ${fmtMs(tm.fetch)} · 디코딩 ${fmtMs(tm.decode)} · 추론 ${fmtMs(tm.infer)} · 검출 차량 ${cs.boxes ?? "-"}대` + (cs.error ? ` · ${cs.error}` : "")
    : "판정 결과가 없어 카메라 스냅샷을 보여줍니다.";
}

// ================= 카메라 설정 =================
function refSize(cam) {
  const p = state.cfg.camera_profiles[cam.profile];
  return cam.ref_size || (p ? p.ref_size : [1280, 960]);
}
function viewsBBox(cam) {
  const p = state.cfg.camera_profiles[cam.profile];
  const [rw, rh] = refSize(cam);
  const views = p ? p.views : [];
  if (!views.length) return [0, 0, rw, rh];
  const x0 = Math.min(...views.map((v) => v[0])), y0 = Math.min(...views.map((v) => v[1]));
  const x1 = Math.max(...views.map((v) => v[0] + v[2])), y1 = Math.max(...views.map((v) => v[1] + v[3]));
  return [x0, y0, x1 - x0, y1 - y0];
}

function renderCameraTab() {
  const cams = state.cfg.cameras;
  if (!state.selectedIp || !cams.some((c) => c.ip === state.selectedIp)) state.selectedIp = cams.length ? cams[0].ip : null;
  renderSidebar();
  const cam = cams.find((c) => c.ip === state.selectedIp);
  if (!cam) {
    editor.detach();
    $("#camEditor").replaceChildren(h("div", { class: "empty-state" },
      h("p", {}, "등록된 카메라가 없습니다."),
      h("button", { class: "primary", onclick: renderAddPanel }, "카메라 추가하기")));
    if (!cams.length) renderAddPanel();
    return;
  }
  editor.attach(cam);
}

// ---------- 카메라 추가 (한 대 / IP 범위) ----------
function parseIp(s) {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(s.trim());
  if (!m) return null;
  const parts = m.slice(1).map(Number);
  return parts.every((n) => n <= 255) ? parts : null;
}
function ipRange(start, end) {
  const a = parseIp(start);
  if (!a) return { error: "시작 IP 형식을 확인하세요" };
  let last;
  const e = end.trim();
  if (!e) last = a[3];
  else if (/^\d{1,3}$/.test(e)) last = Number(e);
  else {
    const b = parseIp(e);
    if (!b) return { error: "끝 IP 형식을 확인하세요" };
    if (b[0] !== a[0] || b[1] !== a[1] || b[2] !== a[2]) return { error: "같은 대역(앞 세 자리)만 범위로 추가할 수 있습니다" };
    last = b[3];
  }
  if (last < a[3] || last > 254) return { error: "끝 번호를 확인하세요" };
  const ips = [];
  for (let i = a[3]; i <= last; i++) ips.push(`${a[0]}.${a[1]}.${a[2]}.${i}`);
  return { ips };
}

function renderAddPanel() {
  const cfg = state.cfg;
  const profiles = Object.keys(cfg.camera_profiles);
  const panel = $("#addCamPanel");
  panel.classList.remove("hidden");
  if (!profiles.length) {
    panel.replaceChildren(h("h3", {}, "카메라 추가"),
      h("p", { class: "muted" }, "먼저 시스템 설정에서 카메라 프로필을 만드세요."),
      h("button", { onclick: () => switchTab("settings") }, "시스템 설정으로"));
    return;
  }
  const f = { start: "", end: "", port: 80, profile: profiles[0], board: cfg.site.board_name || "" };
  const preview = h("span", { class: "muted small" });
  const addBtn = h("button", { class: "primary" }, "추가");
  const update = () => {
    const r = ipRange(f.start, f.end);
    if (!f.start.trim()) { preview.textContent = ""; addBtn.textContent = "추가"; return; }
    if (r.error) { preview.textContent = r.error; addBtn.textContent = "추가"; return; }
    const exist = r.ips.filter((ip) => cfg.cameras.some((c) => c.ip === ip)).length;
    preview.textContent = `${r.ips[0]} ~ ${r.ips[r.ips.length - 1]}` + (exist ? ` (이미 있는 ${exist}대 제외)` : "");
    addBtn.textContent = `${r.ips.length - exist}대 추가`;
  };
  const inp = (key, attrs = {}) => h("input", { value: f[key], ...attrs, oninput: (e) => { f[key] = e.target.value; update(); } });
  addBtn.addEventListener("click", () => {
    const r = ipRange(f.start, f.end);
    if (r.error) return toast(r.error);
    const added = [];
    for (const ip of r.ips) {
      if (cfg.cameras.some((c) => c.ip === ip)) continue;
      cfg.cameras.push({
        ip, port: Number(f.port) || 80, profile: f.profile, own_account: false, user: "", password: "",
        controller_ip: null, board: f.board || null, ref_size: null, enabled: true, slots: [],
      });
      added.push(ip);
    }
    if (!added.length) return toast("추가할 카메라가 없습니다 (모두 이미 있음)");
    state.selectedIp = added[0];
    panel.classList.add("hidden");
    markDirty();
    toast(`${added.length}대를 추가했습니다. 저장해야 반영됩니다.`);
    renderCameraTab();
  });

  panel.replaceChildren(
    h("div", { class: "editor-head" }, h("h3", { style: "margin:0" }, "카메라 추가"), h("span", { class: "spacer" }),
      h("button", { class: "ghost", onclick: () => panel.classList.add("hidden") }, "닫기")),
    h("p", { class: "note" }, "한 대만 추가하려면 시작 IP만 입력하세요. 범위는 끝 번호(예: 230) 또는 끝 IP를 입력합니다. 이미 있는 IP는 건너뜁니다. 카메라 계정은 프로필의 공통 계정을 사용합니다 (시스템 설정 → 카메라 프로필)."),
    h("div", { class: "form-row" },
      field("시작 IP", inp("start", { placeholder: "192.168.0.201", size: 15 })),
      field("끝 (번호 또는 IP)", inp("end", { placeholder: "230", size: 15 })),
      field("포트", inp("port", { type: "number", style: "width:80px" })),
      field("프로필", select(profiles.map((p) => [p, p]), f.profile, (v) => { f.profile = v; })),
      field("담당 보드", inp("board", { size: 8, placeholder: "모든 보드" })),
      addBtn),
    preview);
  update();
}

// ---------- 선분 편집기 ----------
const editor = {
  cam: null, img: null, imgSource: "", canvas: null, ctx: null,
  addMode: false, pending: null, hover: null, drag: null, selected: null, showState: false, newType: "normal",
  bbox: [0, 0, 1280, 480], k: 1, ro: null,

  detach() { this.cam = null; },

  attach(cam) {
    const changed = this.cam !== cam;
    this.cam = cam;
    if (changed) { this.selected = null; this.pending = null; this.addMode = false; this.img = null; }
    this.build();
    if (changed || !this.img) this.loadSnapshot(); else this.resize();
  },

  build() {
    const cam = this.cam;
    const profiles = Object.keys(state.cfg.camera_profiles);
    const set = (key, conv = (v) => v) => (e) => {
      cam[key] = conv(e.target.type === "checkbox" ? e.target.checked : e.target.value); markDirty();
    };
    const ipInput = h("input", { value: cam.ip, size: 14 });
    ipInput.addEventListener("change", (e) => {
      const v = e.target.value.trim();
      if (!parseIp(v)) { toast("IP 형식을 확인하세요"); e.target.value = cam.ip; return; }
      if (state.cfg.cameras.some((c) => c !== cam && c.ip === v)) { toast("이미 있는 IP입니다"); e.target.value = cam.ip; return; }
      cam.ip = v; state.selectedIp = v; markDirty(); renderCameraTab();
    });

    this.canvas = h("canvas", { tabindex: 0 });
    this.ctx = this.canvas.getContext("2d");
    this.bindCanvas();

    this.srcLabel = h("span", { class: "muted small" }, this.imgSource);
    this.addBtn = h("button", { class: this.addMode ? "on" : "", onclick: () => this.toggleAdd() }, "선 추가");
    this.stateBtn = h("button", { class: this.showState ? "on" : "", onclick: () => {
      this.showState = !this.showState; this.stateBtn.classList.toggle("on", this.showState); this.draw();
    } }, "판정 결과 보기");
    const typeSeg = h("span", { class: "seg" }, ...state.cfg.slot_types.map((t) => h("button", {
      class: t.id === this.newType ? "on" : "",
      onclick: (e) => { this.newType = t.id; typeSeg.querySelectorAll("button").forEach((b) => b.classList.remove("on")); e.target.classList.add("on"); },
    }, t.name)));

    const [bcls, btxt] = camBadge(cam);
    const acct = h("span", { class: "form-row" + (cam.own_account ? "" : " hidden"), style: "margin:0" },
      field("사용자", h("input", { value: cam.user, size: 10, onchange: set("user") })),
      field("비밀번호", h("input", { type: "password", value: cam.password, size: 10, onchange: set("password") })));
    this.table = h("tbody");
    $("#camEditor").replaceChildren(
      h("div", { class: "editor-head" }, h("h2", {}, cam.ip), h("span", { class: "badge " + bcls }, btxt)),
      h("div", { class: "form-row" },
        field("카메라 IP", ipInput),
        field("포트", h("input", { type: "number", value: cam.port, style: "width:80px", onchange: set("port", Number) })),
        field("프로필", select(profiles.map((p) => [p, p]), cam.profile, (v) => { cam.profile = v; markDirty(); this.loadSnapshot(); })),
        field("개별 계정", h("input", { type: "checkbox", checked: cam.own_account, onchange: (e) => {
          cam.own_account = e.target.checked; acct.classList.toggle("hidden", !cam.own_account); markDirty();
        } }), "inline"),
        acct,
        field("담당 보드", h("input", { value: cam.board || "", size: 8, placeholder: "모든 보드", onchange: set("board", (v) => v || null) })),
        field("컨트롤러 IP", h("input", { value: cam.controller_ip || "", size: 14, placeholder: "없음", onchange: set("controller_ip", (v) => v || null) })),
        field("사용", h("input", { type: "checkbox", checked: cam.enabled, onchange: (e) => { set("enabled")(e); renderSidebar(); } }), "inline"),
      ),
      h("div", { class: "toolbar" },
        h("button", { onclick: () => this.loadSnapshot() }, "스냅샷 새로고침"),
        h("span", { class: "spacer" }),
        h("span", { class: "muted small" }, "새 선 종류"), typeSeg,
        this.addBtn, this.stateBtn,
      ),
      h("div", { class: "src-label" }, this.srcLabel),
      h("div", { class: "canvas-wrap" }, this.canvas),
      h("div", { class: "hint" }, "선 추가를 누르고 두 점을 클릭 · 끝점을 끌어서 수정 · 선을 클릭하고 Delete로 삭제 · Esc 취소 · 카메라당 최대 12칸"),
      h("table", {}, h("thead", {}, h("tr", {}, ...["번호", "종류", "시작 (x, y)", "끝 (x, y)", "현재 판정", ""].map((t) => h("th", {}, t)))), this.table),
      h("div", { class: "toolbar", style: "margin-top:14px" }, h("span", { class: "spacer" }),
        h("button", { class: "danger", onclick: () => this.deleteCamera() }, "이 카메라 삭제")),
    );
    this.renderTable();
    if (this.ro) this.ro.disconnect();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(this.canvas.parentElement);
  },

  async loadSnapshot() {
    const cam = this.cam;
    this.srcLabel.textContent = "불러오는 중...";
    try {
      const r = await fetch(`/api/v1/cameras/${cam.ip}/snapshot?t=${Date.now()}`);
      if (!r.ok) throw new Error(await errText(r));
      const src = r.headers.get("X-Parkai-Source");
      const err = r.headers.get("X-Parkai-Error");
      const blob = await r.blob();
      const img = new Image();
      img.onload = () => {
        if (this.cam !== cam) return;
        this.img = img;
        this.imgSource = src === "sample"
          ? "샘플 이미지 (카메라 연결 실패" + (err ? ": " + decodeURIComponent(err) : "") + ")"
          : "카메라 실시간";
        this.srcLabel.textContent = `${this.imgSource} · ${img.naturalWidth}×${img.naturalHeight}`;
        this.resize();
      };
      img.src = URL.createObjectURL(blob);
    } catch (e) {
      this.img = null;
      this.srcLabel.textContent = "스냅샷 실패: " + e.message + (state.dirty ? " (변경 사항을 저장한 뒤 다시 시도하세요)" : "");
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
      const v = ((state.status.cameras[this.cam.ip] || {}).states || {})[String(s.no)];
      return v === true ? "#16a34a" : v === false ? "#dc2626" : "#9ca3af";
    }
    return TYPE_LINE_COLORS[s.type] || "#64748b";
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
      ctx.fillText("스냅샷 없음 - 카메라 주소와 인증을 확인하세요", 16, 28);
    }
    const p = state.cfg.camera_profiles[cam.profile];
    ctx.setLineDash([6, 4]); ctx.strokeStyle = "rgba(255,255,255,.45)"; ctx.lineWidth = 1;
    for (const v of (p ? p.views : [])) {
      const [x, y] = this.toScreen([v[0], v[1]]);
      ctx.strokeRect(x + .5, y + .5, v[2] * this.k - 1, v[3] * this.k - 1);
    }
    ctx.setLineDash([]);
    for (const s of cam.slots) {
      const a = this.toScreen(s.line[0]), b = this.toScreen(s.line[1]);
      const color = this.slotColor(s);
      if (this.selected === s) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 10; line(ctx, a, b); }
      ctx.strokeStyle = color; ctx.lineWidth = 6; line(ctx, a, b);
      for (const q of [a, b]) { ctx.fillStyle = "#fff"; dot(ctx, q, 5); ctx.fillStyle = color; dot(ctx, q, 3.5); }
      const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      const label = `${s.no} ${typeName(s.type)}`;
      ctx.font = "bold 13px sans-serif";
      ctx.fillStyle = "rgba(0,0,0,.65)"; ctx.fillRect(m[0] + 8, m[1] - 18, ctx.measureText(label).width + 10, 20);
      ctx.fillStyle = "#fff"; ctx.fillText(label, m[0] + 13, m[1] - 3);
    }
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
        if (!this.pending) this.pending = p;
        else { this.addSlot(this.pending, p); this.pending = null; }
        this.draw(); return;
      }
      const hit = this.hitEndpoint(e);
      if (hit) { this.drag = hit; this.selected = hit.slot; } else this.selected = this.hitLine(e);
      this.renderTable(); this.draw();
    });
    c.addEventListener("mousemove", (e) => {
      if (this.drag) { this.drag.slot.line[this.drag.i] = this.toRef(e); markDirty(); this.draw(); this.renderTable(); return; }
      if (this.addMode) { this.hover = this.toRef(e); this.draw(); return; }
      c.style.cursor = this.hitEndpoint(e) ? "move" : (this.hitLine(e) ? "pointer" : "crosshair");
    });
    c.addEventListener("mouseup", () => { this.drag = null; });
    c.addEventListener("mouseleave", () => { this.drag = null; });
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
    markDirty(); this.renderTable();
  },
  removeSlot(s) {
    this.cam.slots = this.cam.slots.filter((x) => x !== s);
    if (this.selected === s) this.selected = null;
    markDirty(); this.renderTable(); this.draw();
  },
  deleteCamera() {
    if (!confirm(`${this.cam.ip} 카메라를 삭제할까요? (저장해야 반영됩니다)`)) return;
    state.cfg.cameras = state.cfg.cameras.filter((c) => c !== this.cam);
    state.selectedIp = null; this.cam = null;
    markDirty(); renderCameraTab();
  },

  renderTable() {
    if (!this.table || !this.cam) return;
    const st = (state.status.cameras[this.cam.ip] || {}).states || {};
    const live = workerAlive() && camRole(this.cam) === "mine";
    this.table.replaceChildren(...this.cam.slots.map((s) => {
      const no = h("input", { type: "number", min: 1, max: 12, value: s.no });
      no.addEventListener("change", (e) => {
        const v = Number(e.target.value);
        if (v < 1 || v > 12 || this.cam.slots.some((x) => x !== s && x.no === v)) { toast("1~12 사이의 겹치지 않는 번호"); e.target.value = s.no; return; }
        s.no = v; this.cam.slots.sort((x, y) => x.no - y.no); markDirty(); this.renderTable(); this.draw();
      });
      const type = select(state.cfg.slot_types.map((t) => [t.id, t.name]), s.type, (v) => { s.type = v; markDirty(); this.draw(); });
      const v = live ? st[String(s.no)] : undefined;
      return h("tr", { class: this.selected === s ? "selected" : "", onclick: (e) => { if (e.target.tagName === "TD") { this.selected = s; this.renderTable(); this.draw(); } } },
        h("td", {}, no), h("td", {}, type),
        h("td", {}, `${Math.round(s.line[0][0])}, ${Math.round(s.line[0][1])}`), h("td", {}, `${Math.round(s.line[1][0])}, ${Math.round(s.line[1][1])}`),
        h("td", {}, v === true ? h("span", { class: "badge car" }, "차량 있음") : v === false ? h("span", { class: "badge nocar" }, "빈칸") : h("span", { class: "muted" }, "-")),
        h("td", {}, h("button", { class: "danger small", onclick: () => this.removeSlot(s) }, "삭제")));
    }));
  },
};
function line(ctx, a, b) { ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
function dot(ctx, p, r) { ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, Math.PI * 2); ctx.fill(); }
function segDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

// ================= 시스템 설정 =================
function renderSettings() {
  const cfg = state.cfg;
  const bind = (obj, key, conv = (v) => v) => (e) => {
    obj[key] = conv(e.target.type === "checkbox" ? e.target.checked : e.target.value); markDirty();
  };
  const num = (v) => Number(v);
  const sec = (title, note, ...body) => h("div", { class: "panel" }, h("h3", {}, title), note ? h("p", { class: "note" }, note) : null, ...body);

  const basic = sec("기본 정보", "보드명은 카메라의 '담당 보드'와 비교해서 이 보드가 처리할 카메라를 정합니다. 전송용 보드 IP를 비우면 자동으로 읽습니다.",
    h("div", { class: "form-row" },
      field("현장명", h("input", { value: cfg.site.name, onchange: bind(cfg.site, "name") })),
      field("보드명", h("input", { value: cfg.site.board_name, onchange: bind(cfg.site, "board_name") })),
      field("전송용 보드 IP", h("input", { value: cfg.network.board_ip || "", placeholder: "자동", onchange: bind(cfg.network, "board_ip", (v) => v || null) })),
      field("판정 주기 (초)", h("input", { type: "number", step: "1", value: cfg.runtime.cycle_target_sec, style: "width:90px", onchange: bind(cfg.runtime, "cycle_target_sec", num) })),
    ));

  const result = h("pre", { class: "result hidden" });
  const server = sec("서버 전송", "카메라마다 판정 주기마다 주차면 상태를 보냅니다. 전송 테스트는 저장된 설정으로 한 번 보내 봅니다.",
    h("div", { class: "form-row" },
      field("사용", h("input", { type: "checkbox", checked: cfg.server.enabled, onchange: bind(cfg.server, "enabled") }), "inline"),
      field("서버 주소", h("input", { value: cfg.server.base_url, size: 28, placeholder: "http://192.168.0.197:8000", onchange: bind(cfg.server, "base_url") })),
      field("경로", h("input", { value: cfg.server.path, size: 22, onchange: bind(cfg.server, "path") })),
      field("응답 대기 (초)", h("input", { type: "number", step: "0.5", value: cfg.server.timeout_sec, style: "width:80px", onchange: bind(cfg.server, "timeout_sec", num) })),
      h("button", { onclick: async () => {
        if (state.dirty) return toast("먼저 저장하세요");
        result.classList.remove("hidden"); result.textContent = "보내는 중...";
        try {
          const r = await api.send("POST", "/api/v1/server/test", {});
          result.textContent = r.error ? `실패: ${r.error}` : `응답 ${r.status_code}\n${r.body}`;
          result.textContent += `\n\n보낸 내용:\n${JSON.stringify(r.payload, null, 2)}`;
        } catch (e) { result.textContent = e.message; }
      } }, "전송 테스트"),
    ), result);

  const det = cfg.detection;
  const custom = h("div", { class: "form-row" + (det.preset === "custom" ? "" : " hidden") },
    field("판정 방식", select([["intersect", "선에 닿으면 차량 있음"], ["cover_ratio", "선이 덮인 비율로 판단"]], det.judge.mode, (v) => { det.judge.mode = v; markDirty(); })),
    field("덮임 비율 기준", h("input", { type: "number", step: "0.05", value: det.judge.cover_ratio, style: "width:80px", onchange: bind(det.judge, "cover_ratio", num) })),
    field("겹친 칸 기준", h("input", { type: "number", step: "0.05", value: det.judge.cover_ratio_shared, style: "width:80px", onchange: bind(det.judge, "cover_ratio_shared", num) })),
    field("연속 일치 횟수", h("input", { type: "number", min: 1, value: det.stabilize.count, style: "width:80px", onchange: bind(det.stabilize, "count", num) })),
  );
  const carConf = det.classes.car || (det.classes.car = { enabled: true, conf: 0.45 });
  const judge = sec("판정",
    "기존 방식: 선에 차량 박스가 닿으면 차량 있음, 매 주기 결과를 그대로 반영합니다. 개선 방식: 선이 덮인 비율로 판단하고 2회 연속 같을 때 반영합니다.",
    h("div", { class: "form-row" },
      field("판정 방식", select(PRESETS, det.preset, (v) => { det.preset = v; custom.classList.toggle("hidden", v !== "custom"); markDirty(); })),
      field("차량 인식 기준 (0~1)", h("input", { type: "number", step: "0.05", min: 0, max: 1, value: carConf.conf, style: "width:90px", onchange: bind(carConf, "conf", num) })),
      field("모델", h("input", { value: det.model || "", placeholder: "없음", size: 18, onchange: bind(det, "model", (v) => v || null) })),
    ), custom);

  const types = sec("만공등 색", "빈칸이 있을 때 켜질 색을 주차 종류별로 고릅니다. 모두 차면 항상 빨간색입니다.",
    h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "주차 종류"), h("th", {}, "빈칸일 때 색"))),
      h("tbody", {}, ...cfg.slot_types.map((t) => {
        const sw = h("span", { style: `display:inline-block;width:14px;height:14px;border-radius:3px;margin-left:8px;vertical-align:-2px;border:1px solid #ccc;background:${COLOR_HEX[t.color_available]}` });
        return h("tr", {}, h("td", {}, t.name),
          h("td", {}, select(Object.entries(COLOR_LABELS), t.color_available, (v) => { t.color_available = v; sw.style.background = COLOR_HEX[v]; markDirty(); }), sw));
      }))));

  const profBox = h("div");
  const renderProfiles = () => profBox.replaceChildren(...Object.entries(cfg.camera_profiles).map(([name, p]) => h("div", { class: "form-row" },
    field("이름", h("input", { value: name, size: 14, onchange: (e) => {
      const n = e.target.value.trim();
      if (!n || n === name) { e.target.value = name; return; }
      if (cfg.camera_profiles[n]) { toast("같은 이름의 프로필이 있습니다"); e.target.value = name; return; }
      cfg.camera_profiles = Object.fromEntries(Object.entries(cfg.camera_profiles).map(([k, v]) => [k === name ? n : k, v]));
      for (const c of cfg.cameras) if (c.profile === name) c.profile = n;  // 카메라도 새 이름으로
      if (cfg.camera_profiles[n].password === "****") {
        cfg.camera_profiles[n].password = "";
        toast("이름을 바꿨으니 공통 비밀번호를 다시 입력하세요", 4000);
      }
      markDirty(); renderProfiles();
    } })),
    field("스냅샷 주소 ({ip}, {port} 자리에 카메라 값이 들어감)", h("input", { value: p.snapshot_url, size: 56, onchange: bind(p, "snapshot_url") })),
    field("인증", select(AUTH, p.auth, (v) => { p.auth = v; markDirty(); })),
    field("공통 사용자", h("input", { value: p.user || "", size: 10, onchange: bind(p, "user") })),
    field("공통 비밀번호", h("input", { type: "password", value: p.password || "", size: 10, onchange: bind(p, "password") })),
    field("기준 해상도", h("input", { value: p.ref_size.join("x"), size: 9, onchange: (e) => { p.ref_size = e.target.value.split("x").map(Number); markDirty(); } })),
    field("분석 영역 (x,y,가로,세로; ...)", h("input", { value: p.views.map((v) => v.join(",")).join("; "), size: 28, onchange: (e) => {
      p.views = e.target.value.split(";").map((s) => s.trim()).filter(Boolean).map((s) => s.split(",").map(Number)); markDirty();
    } })),
    h("button", { class: "danger", onclick: () => {
      if (cfg.cameras.some((c) => c.profile === name)) return toast("사용 중인 프로필은 삭제할 수 없습니다");
      delete cfg.camera_profiles[name]; markDirty(); renderProfiles();
    } }, "삭제"))));
  renderProfiles();
  const newProf = h("input", { placeholder: "새 프로필 이름", size: 14 });
  const profiles = sec("카메라 프로필", "카메라 기종별 스냅샷 주소, 인증 방식, 공통 계정, 차량을 분석할 화면 영역입니다. 계정이 다른 카메라만 카메라 설정에서 '개별 계정'을 켜세요.",
    profBox,
    h("div", { class: "toolbar" }, newProf, h("button", { onclick: () => {
      const n = newProf.value.trim();
      if (!n || cfg.camera_profiles[n]) return toast("이름을 확인하세요");
      cfg.camera_profiles[n] = { snapshot_url: "http://{ip}:{port}/snapshot.jpg", auth: "digest", user: "admin", password: "", ref_size: [1280, 960], views: [[0, 0, 640, 480], [640, 0, 640, 480]] };
      newProf.value = ""; markDirty(); renderProfiles();
    } }, "프로필 추가")));

  const fileInput = h("input", { type: "file", accept: ".json", onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      if (!confirm("가져온 설정으로 전체를 덮어씁니다. 계속할까요?")) return;
      await api.send("PUT", "/api/v1/config", data); await loadConfig(); toast("가져왔습니다"); renderAll();
    } catch (err) { toast("가져오기 실패: " + err.message, 5000); }
    e.target.value = "";
  } });
  const files = sec("설정 파일", "현장 전체 설정(카메라, 칸, 서버)을 파일로 내보내거나 가져옵니다. 가져오면 바로 저장됩니다.",
    h("div", { class: "toolbar" },
      h("a", { href: "/api/v1/config/export" }, h("button", {}, "내보내기 (비밀번호 제외)")),
      h("a", { href: "/api/v1/config/export?passwords=true" }, h("button", {}, "내보내기 (비밀번호 포함)")),
      h("span", { class: "muted" }, "가져오기"), fileInput));

  $("#settingsForm").replaceChildren(
    h("div", { class: "page-head" }, h("h2", {}, "시스템 설정")),
    basic, server, judge, types, profiles, files);
}

// ================= 시작 =================
$("#saveBtn").addEventListener("click", saveConfig);
$("#revertBtn").addEventListener("click", async () => { await loadConfig(); editor.cam = null; renderAll(); });
window.addEventListener("beforeunload", (e) => { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });

async function pollStatus() {
  try {
    state.status = await api.get("/api/v1/status");
    renderSidebar();
    if (state.tab === "dashboard") renderDashboard();
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
