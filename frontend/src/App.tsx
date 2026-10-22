import { useEffect, useState } from "react";
import { AppHeader, type Tab } from "./components/AppHeader";
import { CameraPage } from "./pages/CameraPage";
import { MonitorPage } from "./pages/MonitorPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useApp } from "./state/AppState";

type Theme = "light" | "dark";

function load<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) || fallback;
  } catch {
    return fallback;
  }
}
function store(key: string, v: string) {
  try {
    localStorage.setItem(key, v);
  } catch {
    /* 저장 못 해도 화면은 동작 */
  }
}

export function App() {
  const app = useApp();
  const [tab, setTab] = useState<Tab>(() => {
    const h = location.hash.replace("#", "") as Tab;
    return ["monitor", "camera", "settings"].includes(h) ? h : "monitor";
  });
  const [theme, setTheme] = useState<Theme>(() =>
    load<Theme>("parkai.theme", window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  const [panelOpen, setPanelOpen] = useState(() => load<string>("parkai.panel", "0") === "1");
  const [cameraIp, setCameraIp] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    store("parkai.theme", theme);
  }, [theme]);
  useEffect(() => store("parkai.panel", panelOpen ? "1" : "0"), [panelOpen]);
  useEffect(() => {
    if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
    window.scrollTo(0, 0);
  }, [tab]);

  return (
    <div className="app">
      <AppHeader tab={tab} onTab={setTab} theme={theme} onTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
        panelOpen={panelOpen} onPanel={tab === "monitor" ? () => setPanelOpen(!panelOpen) : undefined} />
      {!app.cfg ? (
        <div className="empty">{app.saveError || "불러오는 중…"}</div>
      ) : tab === "monitor" ? (
        <MonitorPage panelOpen={panelOpen} setPanelOpen={setPanelOpen} onGoSettings={() => setTab("settings")} onGoCamera={() => setTab("camera")} />
      ) : tab === "camera" ? (
        <CameraPage selectedIp={cameraIp} setSelectedIp={setCameraIp} />
      ) : (
        <SettingsPage />
      )}
      {app.cfg && <SaveBar />}
      {app.toastMsg && <div className="toast" role="status">{app.toastMsg}</div>}
    </div>
  );
}

function SaveBar() {
  const { changes, lastChange, saveError, save, revert } = useApp();
  if (changes === 0) return null;
  return (
    <div className="savebar" role="status">
      <span className="savebar__dot" />
      <strong className="strong">저장하지 않은 변경 {changes}건</strong>
      {lastChange && <span className="savebar__note">마지막: {lastChange}</span>}
      {saveError && <span className="savebar__error">{saveError}</span>}
      <span className="spacer" />
      <button type="button" className="btn" onClick={revert}>되돌리기</button>
      <button type="button" className="btn btn--primary" onClick={save}>저장</button>
    </div>
  );
}
