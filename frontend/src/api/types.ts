// parkai/core/config.py 와 웹 API 응답의 형태. 백엔드 스키마가 바뀌면 여기부터 고친다.

/** 렌즈 사진 대비 비율 (0~1) */
export type Point = [number, number];
/** [x, y, w, h] 렌즈 사진 대비 비율 (0~1) */
export type Rect = [number, number, number, number];
export type SlotTypeId = "normal" | "compact" | "disabled" | "ev";
export type IndicatorColor = "green" | "blue" | "yellow" | "white" | "purple" | "cyan";
export type Preset = "legacy" | "standard" | "custom";

export interface Slot {
  no: number;
  type: SlotTypeId;
  /** 렌즈 번호 (0부터) */
  lens: number;
  line: [Point, Point];
  name: string;
  judge: { cover_ratio: number | null } | null;
}

export interface Camera {
  ip: string;
  port: number;
  profile: string;
  own_account: boolean;
  user: string;
  password: string;
  controller_ip: string | null;
  board: string | null;
  enabled: boolean;
  slots: Slot[];
}

export interface CameraProfile {
  /** {ip}, {port}, {channel}(렌즈 번호, 1부터) 치환 */
  snapshot_url: string;
  auth: "none" | "basic" | "digest";
  user: string;
  password: string;
  /** 렌즈 수 (렌즈마다 사진을 따로 받음) */
  lenses: number;
  /** 분석 영역 (모든 렌즈에 같게) */
  views: Rect[];
}

export interface SlotType {
  id: SlotTypeId;
  name: string;
  color_available: IndicatorColor;
}

export interface AppConfig {
  schema_version: number;
  site: { name: string; board_name: string };
  network: { interface: string | null; board_ip: string | null };
  runtime: {
    cycle_target_sec: number;
    fetch_concurrency: number;
    fetch_timeout_sec: number;
    fetch_retries: number;
    results: { max_mb: number; save_interval_sec: number };
  };
  detection: {
    preset: Preset;
    model: string | null;
    classes: Record<string, { enabled: boolean; conf: number }>;
    nms_iou: number;
    judge: { mode: "intersect" | "cover_ratio"; cover_ratio: number; cover_ratio_shared: number };
    stabilize: { count: number };
    image_check: { black_mean: number; blur_var: number; frozen_cycles: number };
  };
  slot_types: SlotType[];
  camera_profiles: Record<string, CameraProfile>;
  cameras: Camera[];
  server: { enabled: boolean; base_url: string; path: string; timeout_sec: number };
  indicator: { enabled: boolean; protocol: "idis"; led_type: "internal" | "external"; resend_sec: number };
}

export interface Resources {
  cpu_percent: number | null;
  memory: { used_mb: number; total_mb: number } | null;
  temperature_c: number | null;
  storage: { used_mb: number; total_mb: number } | null;
}

export interface SystemInfo {
  version: string;
  device_id: string;
  board_model: string;
  board_ip: string;
  site: { name: string; board_name: string };
  model: string | null;
  preset: Preset;
  config_path: string;
  resources?: Resources;
}

export type CameraStatusCode =
  | "ok" | "partial" | "no_response" | "black" | "blur" | "frozen" | "decode_error" | "error";

export interface CameraStatus {
  status?: CameraStatusCode;
  timings?: Partial<Record<"fetch" | "decode" | "check" | "infer" | "judge" | "output", number>>;
  error?: string | null;
  updated_at?: string;
  states?: Record<string, boolean>;
  sent?: boolean;
  boxes?: number;
  /** 검출 박스 [렌즈, x1, y1, x2, y2, score] (렌즈 사진 대비 비율) */
  dets?: Det[];
}

export type Det = [number, number, number, number, number, number];

export interface LedTestResult {
  ok: boolean;
  url: string;
  status_code?: number;
  return_code?: number | null;
  error?: string;
}

export interface WorkerStatus {
  running: boolean;
  cycle_sec?: number;
  updated_at?: string;
  server_error?: string | null;
  cameras: Record<string, CameraStatus>;
}

export interface ServerTestResult {
  url: string;
  status_code?: number;
  body?: string;
  error?: string;
  payload: unknown;
}
