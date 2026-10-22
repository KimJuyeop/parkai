import { useState } from "react";
import { CameraCard } from "../components/CameraCard";
import { CameraDialog } from "../components/CameraDialog";
import { Icon } from "../components/Icon";
import { StatusStrip } from "../components/StatusStrip";
import { handledHere, slotState } from "../lib/domain";
import { BasicFields, JudgeFields, LampFields, ServerFields } from "../settings/sections";
import { PRESETS } from "../lib/domain";
import { useCfg } from "../state/AppState";

type Filter = "all" | "free" | "full";

export function MonitorPage({ panelOpen, setPanelOpen, onGoSettings, onGoCamera }: {
  panelOpen: boolean; setPanelOpen: (v: boolean) => void; onGoSettings: () => void; onGoCamera: () => void;
}) {
  const { cfg, status, alive } = useCfg();
  const [filter, setFilter] = useState<Filter>("all");
  const [dialog, setDialog] = useState<{ ip: string; edit: boolean } | null>(null);

  // 이 보드가 판정하는 카메라만 보여준다 (사용 안 함 / 다른 보드 담당은 카메라 설정에서)
  const cams = cfg.cameras.filter((c) => handledHere(cfg, c));
  const info = cams.map((c) => {
    const cs = alive ? status.cameras[c.ip] : undefined;
    const st = c.slots.map((s) => slotState(cs, s.no));
    return { cam: c, free: st.some((v) => v === false), full: st.length > 0 && st.every((v) => v === true) };
  });
  const filters: { id: Filter; name: string; count: number }[] = [
    { id: "all", name: "전체", count: info.length },
    { id: "free", name: "빈칸 있음", count: info.filter((x) => x.free).length },
    { id: "full", name: "만차", count: info.filter((x) => x.full).length },
  ];
  const shown = info.filter((x) => filter === "all" || (filter === "free" ? x.free : x.full));

  return (
    <div className="page">
      {panelOpen ? <QuickSettings onClose={() => setPanelOpen(false)} onGoSettings={onGoSettings} /> : (
        <button type="button" className="rail" aria-label="빠른 설정 패널 열기" onClick={() => setPanelOpen(true)}>
          <Icon name="chevronRight" size={18} />
          <span className="rail__label">설정</span>
        </button>
      )}

      <main className="page__main">
        <StatusStrip />

        <div className="list-head">
          <h1 className="title">카메라</h1>
          <div className="tabs" role="group" aria-label="카메라 보기 필터">
            {filters.map((f) => (
              <button key={f.id} type="button" className="tabs__btn" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
                {f.name}<span className="tabs__count">{f.count}</span>
              </button>
            ))}
          </div>
          <span className="spacer" />
          <div className="legend">
            <span className="legend__item"><span className="legend__swatch" style={{ background: "var(--occ)" }} />차량 있음</span>
            <span className="legend__item"><span className="legend__swatch" style={{ background: "var(--free-soft)", border: "1.5px solid var(--free)" }} />빈칸</span>
            <span className="legend__item"><span className="legend__swatch" style={{ border: "1.5px dashed var(--unj)" }} />판정 없음</span>
          </div>
        </div>

        {cams.length === 0 ? (
          <div className="empty">
            <span>등록된 카메라가 없습니다.</span>
            <button type="button" className="btn btn--primary" onClick={onGoCamera}><Icon name="plus" />카메라 추가하기</button>
          </div>
        ) : shown.length === 0 ? (
          <div className="empty">조건에 맞는 카메라가 없습니다.</div>
        ) : (
          <div className="cards">
            {shown.map(({ cam }) => (
              <CameraCard key={cam.ip} cam={cam} onOpen={() => setDialog({ ip: cam.ip, edit: false })} onEdit={() => setDialog({ ip: cam.ip, edit: true })} />
            ))}
          </div>
        )}
      </main>

      {dialog && <CameraDialog ip={dialog.ip} startEditing={dialog.edit} onClose={() => setDialog(null)} />}
    </div>
  );
}

type Sec = "basic" | "server" | "judge" | "lamp";

function QuickSettings({ onClose, onGoSettings }: { onClose: () => void; onGoSettings: () => void }) {
  const { cfg } = useCfg();
  const [open, setOpen] = useState<Sec | null>("judge");
  const sections: { id: Sec; title: string; summary: string; body: JSX.Element }[] = [
    { id: "basic", title: "기본 정보", summary: `판정 주기 ${cfg.runtime.cycle_target_sec}초`, body: <BasicFields compact /> },
    { id: "server", title: "서버 전송", summary: cfg.server.enabled ? "사용 중" : "사용 안 함", body: <ServerFields compact /> },
    { id: "judge", title: "판정 방식", summary: PRESETS.find((p) => p.id === cfg.detection.preset)?.name ?? "", body: <JudgeFields compact /> },
    { id: "lamp", title: "만공등 색", summary: "종류별", body: <LampFields /> },
  ];
  return (
    <aside className="panel quick" aria-label="빠른 설정">
      <div className="panel__head">
        <h2 className="section-title spacer">빠른 설정</h2>
        <button type="button" className="btn btn--icon" aria-label="빠른 설정 패널 접기" onClick={onClose}>
          <Icon name="chevronLeft" size={18} />
        </button>
      </div>
      {sections.map((s) => (
        <div key={s.id}>
          <button type="button" className="acc__head" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
            <span className="acc__title">{s.title}</span>
            <span className="meta">{s.summary}</span>
            <span className="acc__chev"><Icon name="chevronDown" size={14} /></span>
          </button>
          {open === s.id && <div className="acc__body">{s.body}</div>}
        </div>
      ))}
      <div style={{ padding: "14px 16px" }}>
        <button type="button" className="btn btn--ghost" style={{ paddingLeft: 0 }} onClick={onGoSettings}>
          카메라 프로필 · 설정 파일은 시스템 설정에서<Icon name="chevronRight" size={14} />
        </button>
      </div>
    </aside>
  );
}
