import type { AppConfig, Camera, CameraStatus, IndicatorColor, Point, Rect, SlotTypeId, WorkerStatus } from "../api/types";

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
 * 만공등 색 (카메라로는 0xRRGGBB 로 보낸다: config.py LED_RGB).
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

/** 판정 규칙 (고정, docs/design.md 4절). 화면에서 바꾸는 값은 차량 인식 기준과 연속 확인 횟수 */
export const JUDGE_RULE = "선분이 차량 박스에 60% 이상 덮이면 차량 있음";

/** 카메라의 렌즈 수 (프로필 값) */
export function lensCount(cfg: AppConfig, cam: Camera): number {
  return Math.max(1, cfg.camera_profiles[cam.profile]?.lenses ?? 1);
}

/** 분석 영역 전체를 감싸는 사각형 (렌즈 사진 대비 비율). 화면에 보여 주는 영역 */
export function viewsBBox(views: Rect[]): Rect {
  if (!views.length) return [0, 0, 1, 1];
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

/** 저장된 비밀번호 자리 표시. 서버는 비밀번호를 화면에 보내지 않고 이 값을 준다 (그대로 저장하면 기존 값 유지) */
export const MASK = "****";

/** 이 주기 수만큼 연달아 실패해야 화면에 '응답 없음'·실패 원인을 보인다 (한 번씩 튀는 실패는 로그에만) */
export const DOWN_AFTER_CYCLES = 3;

/** 카메라가 응답 없음으로 보일 상태인지 */
export function cameraDown(cs: CameraStatus | undefined): boolean {
  return cs?.status === "no_response" && (cs.fail_cycles ?? DOWN_AFTER_CYCLES) >= DOWN_AFTER_CYCLES;
}

/** 카메라 설정 화면에 보일 실패 원인 (몇 주기 이어질 때만) */
export function lastingError(cs: CameraStatus | undefined): string | null {
  return cs?.error && (cs.fail_cycles ?? DOWN_AFTER_CYCLES) >= DOWN_AFTER_CYCLES ? cs.error : null;
}

/** 이 보드가 판정하는 카메라인지 (config.py cameras_for_board 와 같은 규칙) */
export function handledHere(cfg: AppConfig, cam: Camera): boolean {
  const me = cfg.site.board_name;
  return cam.enabled && (!cam.board || !me || cam.board === me);
}

/**
 * 지난 시간(초). now 는 보드 시각(status.now): 현장은 인터넷이 없어 보드 시계가 틀릴 수 있으므로
 * 보드가 남긴 시각은 보드 시계끼리 비교한다. now 가 없을 때(예전 보드)만 브라우저 시계를 쓴다.
 */
export function ageSec(iso: string, now?: string): number {
  const ref = now ? new Date(now).getTime() : Date.now();
  return Math.max(0, (ref - new Date(iso).getTime()) / 1000);
}

export function workerAlive(status: WorkerStatus, cfg: AppConfig): boolean {
  if (!status.running || !status.updated_at) return false;
  return ageSec(status.updated_at, status.now) < Math.max(30, cfg.runtime.cycle_target_sec * 3);
}

export type SlotState = boolean | null;
export function slotState(cs: CameraStatus | undefined, no: number): SlotState {
  const v = cs?.states?.[String(no)];
  return v === undefined ? null : v;
}

export const stateLabel = (s: SlotState) => (s === true ? "차량 있음" : s === false ? "빈칸" : "판정 없음");
/** 판정 결과 글자 색 클래스 */
export const stateTextClass = (s: SlotState) => (s === true ? "text-occ" : s === false ? "text-free" : "muted");

export function ago(iso?: string, now?: string): string {
  if (!iso) return "";
  const s = Math.round(ageSec(iso, now));
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

/** 선분 좌표 표시: 렌즈 사진 대비 % */
export const fmtPoint = (p: Point) => `${(p[0] * 100).toFixed(1)}%, ${(p[1] * 100).toFixed(1)}%`;
export const lensName = (lens: number) => `렌즈 ${lens + 1}`;
