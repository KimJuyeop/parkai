import type { AppConfig, Camera, CameraStatus, IndicatorColor, Point, SlotTypeId, WorkerStatus } from "../api/types";

export const MAX_SLOTS = 12;

/** 주차 종류: 이름은 고정, 선 색은 화면 표시용 (tokens.css 의 --type-*) */
export const SLOT_TYPES: { id: SlotTypeId; name: string; short: string; color: string }[] = [
  { id: "normal", name: "일반", short: "", color: "var(--type-normal)" },
  { id: "compact", name: "경차", short: "경", color: "var(--type-compact)" },
  { id: "disabled", name: "장애인", short: "장", color: "var(--type-disabled)" },
  { id: "ev", name: "전기차", short: "EV", color: "var(--type-ev)" },
];
export const slotType = (id: string) => SLOT_TYPES.find((t) => t.id === id) ?? SLOT_TYPES[0];

/**
 * 만공등 색 (실제 지원 색은 카메라 사양 확인 후 조정).
 * 화면 테마가 아니라 실제 LED 색 정의라 tokens.css 규칙의 예외로 여기에 둔다.
 */
export const INDICATOR_COLORS: { id: IndicatorColor; name: string; hex: string }[] = [
  { id: "green", name: "녹색", hex: "#16a34a" },
  { id: "blue", name: "파란색", hex: "#2563eb" },
  { id: "yellow", name: "노란색", hex: "#eab308" },
  { id: "white", name: "흰색", hex: "#e5e7eb" },
  { id: "purple", name: "보라색", hex: "#9333ea" },
  { id: "cyan", name: "하늘색", hex: "#06b6d4" },
];
/** 만차일 때 만공등 색 (항상 빨강, 바꿀 수 없음) */
export const FULL_LAMP = { name: "빨간색", hex: "#dc2626" } as const;

export const PRESETS = [
  { id: "legacy", name: "기존 방식", desc: "선에 차량 박스가 닿으면 차량 있음 · 매 주기 반영", tag: "Jetson과 동일" },
  { id: "standard", name: "개선 방식", desc: "선이 덮인 비율(0.6)로 판단 · 2회 연속 같을 때 반영", tag: "검증 후 전환 후보" },
  { id: "custom", name: "직접 설정", desc: "판정 기준과 연속 일치 횟수를 직접 정합니다", tag: "현장 보정용" },
] as const;

export function refSize(cfg: AppConfig, cam: Camera): [number, number] {
  return cam.ref_size ?? cfg.camera_profiles[cam.profile]?.ref_size ?? [1280, 960];
}

/** 분석 영역 전체를 감싸는 사각형 [x, y, w, h]. 화면에 보여주는 영역이자 스냅샷 crop 영역 */
export function viewsBBox(cfg: AppConfig, cam: Camera): [number, number, number, number] {
  const [rw, rh] = refSize(cfg, cam);
  const views = cfg.camera_profiles[cam.profile]?.views ?? [];
  if (!views.length) return [0, 0, rw, rh];
  const x0 = Math.min(...views.map((v) => v[0]));
  const y0 = Math.min(...views.map((v) => v[1]));
  const x1 = Math.max(...views.map((v) => v[0] + v[2]));
  const y1 = Math.max(...views.map((v) => v[1] + v[3]));
  return [x0, y0, x1 - x0, y1 - y0];
}

/** 비어 있는 가장 작은 칸 번호 (서버 전송 ps01~ps12 와 맞물리므로 삭제해도 다른 번호는 그대로) */
export function nextSlotNo(cam: Camera): number | null {
  const used = new Set(cam.slots.map((s) => s.no));
  for (let n = 1; n <= MAX_SLOTS; n++) if (!used.has(n)) return n;
  return null;
}

/** 이 보드가 판정하는 카메라인지 (config.py cameras_for_board 와 같은 규칙) */
export function handledHere(cfg: AppConfig, cam: Camera): boolean {
  const me = cfg.site.board_name;
  return cam.enabled && (!cam.board || !me || cam.board === me);
}

export function workerAlive(status: WorkerStatus, cfg: AppConfig): boolean {
  if (!status.running || !status.updated_at) return false;
  const age = (Date.now() - new Date(status.updated_at).getTime()) / 1000;
  return age < Math.max(30, cfg.runtime.cycle_target_sec * 3);
}

export type SlotState = boolean | null;
export function slotState(cs: CameraStatus | undefined, no: number): SlotState {
  const v = cs?.states?.[String(no)];
  return v === undefined ? null : v;
}

export const stateLabel = (s: SlotState) => (s === true ? "차량 있음" : s === false ? "빈칸" : "판정 없음");
/** 판정 결과 글자 색 클래스 */
export const stateTextClass = (s: SlotState) => (s === true ? "text-occ" : s === false ? "text-free" : "muted");

export function ago(iso?: string): string {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return s < 60 ? `${s}초 전` : s < 3600 ? `${Math.floor(s / 60)}분 전` : `${Math.floor(s / 3600)}시간 전`;
}

export const ms = (sec?: number) => (sec == null ? "-" : `${Math.round(sec * 1000)}ms`);

export function parseIp(s: string): number[] | null {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(s.trim());
  if (!m) return null;
  const parts = m.slice(1).map(Number);
  return parts.every((n) => n <= 255) ? parts : null;
}

/** "192.168.13.26" + "30" 또는 "192.168.13.30" → IP 목록 */
export function ipRange(start: string, end: string): { ips: string[] } | { error: string } {
  const a = parseIp(start);
  if (!a) return { error: "시작 IP 형식을 확인하세요 (예: 192.168.13.26)" };
  let last = a[3];
  const e = end.trim();
  if (/^\d{1,3}$/.test(e)) last = Number(e);
  else if (e) {
    const b = parseIp(e);
    if (!b || b[0] !== a[0] || b[1] !== a[1] || b[2] !== a[2]) return { error: "끝은 같은 대역의 번호나 IP로 입력하세요" };
    last = b[3];
  }
  if (last < a[3] || last > 254) return { error: "끝 번호는 시작 번호 이상, 254 이하로 입력하세요" };
  const ips: string[] = [];
  for (let i = a[3]; i <= last && ips.length < 64; i++) ips.push(`${a[0]}.${a[1]}.${a[2]}.${i}`);
  return { ips };
}

export const fmtPoint = (p: Point) => `${Math.round(p[0])}, ${Math.round(p[1])}`;
