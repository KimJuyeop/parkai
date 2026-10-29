import type { AppConfig, LedTestResult, ServerTestResult, SystemInfo, WorkerStatus } from "./types";

async function errorText(r: Response): Promise<string> {
  try {
    const j = await r.json();
    if (Array.isArray(j.detail)) return j.detail.join("\n");
    return j.detail || r.statusText;
  } catch {
    return r.statusText;
  }
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(await errorText(r));
  return r.json() as Promise<T>;
}

async function send<T>(method: "PUT" | "POST", path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errorText(r));
  return r.json() as Promise<T>;
}

export const api = {
  system: () => get<SystemInfo>("/api/v1/system"),
  status: () => get<WorkerStatus>("/api/v1/status"),
  config: () => get<AppConfig>("/api/v1/config"),
  saveConfig: (cfg: AppConfig) => send<{ ok: true }>("PUT", "/api/v1/config", cfg),
  serverTest: () => send<ServerTestResult>("POST", "/api/v1/server/test", {}),
  exportUrl: (passwords: boolean) => `/api/v1/config/export${passwords ? "?passwords=true" : ""}`,
  /** 판정 중인 카메라의 렌즈 원본 이미지 (워커가 매 사이클 갱신) */
  latestUrl: (ip: string, lens: number, t: number) => `/api/v1/cameras/${ip}/latest?lens=${lens}&t=${t}`,
  /** 카메라에서 바로 받은 렌즈 스냅샷 (원본. 화면이 분석 영역만 잘라 보여 줌) */
  snapshotUrl: (ip: string, lens: number, t: number) => `/api/v1/cameras/${ip}/snapshot?lens=${lens}&t=${t}`,
  /** 만공등에 색 하나를 바로 보내 본다 (저장된 설정 기준) */
  ledTest: (ip: string, color: string) => send<LedTestResult>("POST", `/api/v1/cameras/${ip}/led`, { color }),
};
