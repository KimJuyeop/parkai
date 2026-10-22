import type { AppConfig, ServerTestResult, SystemInfo, WorkerStatus } from "./types";

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
  /** 판정 중인 카메라의 최신 원본 이미지 (워커가 매 사이클 갱신) */
  latestUrl: (ip: string, t: number) => `/api/v1/cameras/${ip}/latest?t=${t}`,
  /** 카메라에서 바로 받은 스냅샷. crop: 분석 영역만 */
  snapshotUrl: (ip: string, t: number) => `/api/v1/cameras/${ip}/snapshot?crop=1&t=${t}`,
};
