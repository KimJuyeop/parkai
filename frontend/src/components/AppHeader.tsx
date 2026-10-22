import { Icon } from "./Icon";

export type Tab = "monitor" | "camera" | "settings";
const TABS: { id: Tab; name: string }[] = [
  { id: "monitor", name: "모니터링" },
  { id: "camera", name: "카메라 설정" },
  { id: "settings", name: "시스템 설정" },
];

export function AppHeader({ tab, onTab, theme, onTheme, panelOpen, onPanel }: {
  tab: Tab; onTab: (t: Tab) => void;
  theme: "light" | "dark"; onTheme: () => void;
  panelOpen: boolean; onPanel?: () => void;
}) {
  return (
    <header className="header">
      {onPanel && (
        <button type="button" className="btn btn--icon header__icon-btn" aria-pressed={panelOpen}
          aria-label="빠른 설정 패널" title="빠른 설정 패널 열기/접기" onClick={onPanel}>
          <Icon name="panel" size={18} />
        </button>
      )}
      <div className="header__brand">
        <span className="header__name">주차유도 시스템</span>
        <span className="header__sub">parking AI</span>
      </div>
      <nav className="header__nav" aria-label="주 메뉴">
        {TABS.map((t) => (
          <button key={t.id} type="button" className="header__tab" aria-current={t.id === tab ? "page" : undefined} onClick={() => onTab(t.id)}>
            {t.name}
          </button>
        ))}
      </nav>
      <span className="spacer" />
      <button type="button" className="btn" onClick={onTheme} aria-label="화면 테마 전환">
        <Icon name="sun" />
        {theme === "dark" ? "라이트로" : "다크로"}
      </button>
    </header>
  );
}
