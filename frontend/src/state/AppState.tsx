import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { AppConfig, SystemInfo, WorkerStatus } from "../api/types";
import { workerAlive } from "../lib/domain";

const STATUS_POLL_MS = 3000;
const SYSTEM_POLL_MS = 5000;
const CYCLE_HISTORY = 12;

interface AppState {
  system: SystemInfo | null;
  status: WorkerStatus;
  /** 화면에서 고치는 중인 설정 (저장 전) */
  cfg: AppConfig | null;
  /** 서버에 저장된 카메라 IP (새로 추가하고 아직 저장 안 한 카메라는 스냅샷을 받을 수 없음) */
  savedIps: Set<string>;
  alive: boolean;
  cycleHistory: number[];
  changes: number;
  lastChange: string;
  saveError: string;
  /** 설정 수정. fn 안에서 draft 를 직접 고치면 된다. note 는 저장 바에 표시 */
  edit: (fn: (draft: AppConfig) => void, note?: string) => void;
  /** 드래그 중처럼 연속으로 바뀌는 값: 변경 건수는 늘리지 않음 */
  editQuiet: (fn: (draft: AppConfig) => void) => void;
  countChange: (note: string) => void;
  save: () => Promise<boolean>;
  revert: () => Promise<void>;
  reload: () => Promise<void>;
  toast: (msg: string, ms?: number) => void;
  toastMsg: string;
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("AppProvider 밖에서 useApp 사용");
  return v;
}

/** 설정이 로드된 뒤에만 그리는 화면용 */
export function useCfg(): AppState & { cfg: AppConfig } {
  const app = useApp();
  if (!app.cfg) throw new Error("설정이 아직 없습니다");
  return app as AppState & { cfg: AppConfig };
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [status, setStatus] = useState<WorkerStatus>({ running: false, cameras: {} });
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [savedIps, setSavedIps] = useState<Set<string>>(new Set());
  const [changes, setChanges] = useState(0);
  const [lastChange, setLastChange] = useState("");
  const [saveError, setSaveError] = useState("");
  const [cycleHistory, setCycleHistory] = useState<number[]>([]);
  const [toastMsg, setToastMsg] = useState("");
  const toastTimer = useRef<number>();
  const lastCycleAt = useRef<string>();

  const toast = useCallback((msg: string, msTime = 2400) => {
    setToastMsg(msg);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastMsg(""), msTime);
  }, []);

  const reload = useCallback(async () => {
    const c = await api.config();
    setCfg(c);
    setSavedIps(new Set(c.cameras.map((x) => x.ip)));
    setChanges(0);
    setLastChange("");
    setSaveError("");
  }, []);

  useEffect(() => {
    reload().catch((e) => setSaveError(`서버에 연결하지 못했습니다: ${e.message}`));
  }, [reload]);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const s = await api.status();
        if (stop) return;
        setStatus(s);
        if (s.cycle_sec != null && s.updated_at && s.updated_at !== lastCycleAt.current) {
          lastCycleAt.current = s.updated_at;
          setCycleHistory((h) => [...h, s.cycle_sec as number].slice(-CYCLE_HISTORY));
        }
      } catch {
        /* 다음 주기에 다시 */
      }
    };
    tick();
    const id = window.setInterval(tick, STATUS_POLL_MS);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let stop = false;
    const tick = () => api.system().then((s) => !stop && setSystem(s)).catch(() => undefined);
    tick();
    const id = window.setInterval(tick, SYSTEM_POLL_MS);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  const editQuiet = useCallback((fn: (d: AppConfig) => void) => {
    setCfg((cur) => {
      if (!cur) return cur;
      const next = structuredClone(cur);
      fn(next);
      return next;
    });
  }, []);

  const countChange = useCallback((note: string) => {
    setChanges((n) => n + 1);
    setLastChange(note);
    setSaveError("");
  }, []);

  const edit = useCallback(
    (fn: (d: AppConfig) => void, note = "설정 변경") => {
      editQuiet(fn);
      countChange(note);
    },
    [editQuiet, countChange],
  );

  const save = useCallback(async () => {
    if (!cfg) return false;
    try {
      await api.saveConfig(cfg);
      await reload();
      api.system().then(setSystem).catch(() => undefined);
      toast("저장했습니다. 다음 사이클부터 반영됩니다.");
      return true;
    } catch (e) {
      setSaveError((e as Error).message);
      return false;
    }
  }, [cfg, reload, toast]);

  const revert = useCallback(async () => {
    await reload();
  }, [reload]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (changes > 0) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changes]);

  const value = useMemo<AppState>(
    () => ({
      system, status, cfg, savedIps, alive: cfg ? workerAlive(status, cfg) : false, cycleHistory,
      changes, lastChange, saveError, edit, editQuiet, countChange, save, revert, reload, toast, toastMsg,
    }),
    [system, status, cfg, savedIps, cycleHistory, changes, lastChange, saveError, edit, editQuiet, countChange, save, revert, reload, toast, toastMsg],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
