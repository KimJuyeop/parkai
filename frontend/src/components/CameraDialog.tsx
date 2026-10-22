import { useState } from "react";
import type { SlotTypeId } from "../api/types";
import { ago, fmtPoint, slotType, stateLabel } from "../lib/domain";
import { useCfg } from "../state/AppState";
import { CameraMedia } from "./CameraMedia";
import { Icon } from "./Icon";
import { LineEditor } from "./LineEditor";
import { CloseButton, Dialog, SlotChip, TypePicker } from "./ui";
import { useCameraImage, useCameraView, useSlotEditing } from "./useCamera";

/**
 * 모니터링 큰 창: 보기 ↔ 선 편집. 고친 내용은 앱 전체의 "저장하지 않은 변경"에 쌓이고
 * 창을 닫아도 남는다 (화면 아래 저장 바에서 저장/되돌리기).
 */
export function CameraDialog({ ip, startEditing, onClose }: { ip: string; startEditing: boolean; onClose: () => void }) {
  const { cfg, changes, save, revert, saveError } = useCfg();
  const [editingMode, setEditingMode] = useState(startEditing);
  const [newType, setNewType] = useState<SlotTypeId>("normal");
  const [showDets, setShowDets] = useState(false);
  const editing = useSlotEditing(ip, newType);
  const cam = cfg.cameras.find((c) => c.ip === ip);
  const view = useCameraView(cam);
  const img = useCameraImage(cam);
  if (!cam || !view) return null;
  const selNo = editing.selected ?? cam.slots[0]?.no ?? null;
  const sel = cam.slots.find((s) => s.no === selNo);
  const selState = sel ? view.states(sel.no) : null;

  return (
    <Dialog label={`${ip} 카메라`} width={1180} onClose={onClose}>
      <div className="panel__head" style={{ flexWrap: "wrap", rowGap: 8 }}>
        <span className="mono title">{ip}</span>
        <span className="meta">{view.cs?.updated_at ? `${ago(view.cs.updated_at)} 갱신 · ` : ""}{cam.slots.length}칸</span>
        {view.offline && <span className="badge badge--bad">응답 없음</span>}
        {editingMode && <span className="badge badge--accent">선 편집 중</span>}
        <span className="spacer" />
        {!editingMode && (
          <label className="check" style={{ minHeight: 36, fontSize: "var(--fs-control)" }}>
            <input type="checkbox" checked={showDets} onChange={(e) => setShowDets(e.target.checked)} />
            검출 박스
          </label>
        )}
        <button type="button" className={`btn ${editingMode ? "" : "btn--soft"}`} onClick={() => setEditingMode((v) => !v)}>
          <Icon name="line" size={14} />{editingMode ? "편집 끝내기" : "선 편집"}
        </button>
        <CloseButton onClick={onClose} />
      </div>

      {editingMode ? (
        <div style={{ padding: "12px 12px 0" }}>
          <LineEditor cam={cam} editing={editing} newType={newType} setNewType={setNewType} />
        </div>
      ) : (
        <CameraMedia
          bbox={view.bbox} views={view.views} slots={cam.slots} states={view.states} imageSrc={img.src}
          message={!img.src ? (img.error ? "카메라 연결 안 됨" : "불러오는 중…") : null}
          colorMode="state" selectedNo={selNo} onSelect={editing.setSelected}
          dets={showDets ? view.cs?.dets : undefined} label={`${ip} 영상과 칸 선분`}
        />
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "16px 24px", padding: "14px 18px" }}>
        <div style={{ flex: "999 1 420px", minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="meta">칸 {cam.slots.length}개 · 누르면 영상에서 강조</span>
          <div className="chips">
            {cam.slots.map((s) => (
              <button key={s.no} type="button" className="slot-btn" aria-pressed={s.no === selNo} onClick={() => editing.setSelected(s.no)}>
                <SlotChip no={s.no} state={view.states(s.no)} type={s.type} />
                <span className="type-bar" style={{ background: slotType(s.type).color, width: 12 }} />
                {slotType(s.type).name}
              </button>
            ))}
          </div>
        </div>
        {sel && (
          <div style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="section-title">{sel.no}번 칸</span>
              <span style={{ fontWeight: 600, fontSize: "var(--fs-control)", color: selState === true ? "var(--occ)" : selState === false ? "var(--free)" : "var(--muted)" }}>
                {stateLabel(selState)}
              </span>
            </div>
            <TypePicker value={sel.type} onPick={(t) => editing.setType(sel.no, t)} label={`${sel.no}번 칸 주차 종류`} />
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="mono meta spacer">{fmtPoint(sel.line[0])} → {fmtPoint(sel.line[1])}</span>
              {editingMode && (
                <button type="button" className="btn btn--danger" onClick={() => editing.remove(sel.no)}>
                  <Icon name="trash" size={14} />이 칸 삭제
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {changes > 0 && (
        <div className="dialog__foot" style={{ justifyContent: "flex-start", alignItems: "center", background: "var(--surface-2)" }}>
          <span className="dot" style={{ background: "var(--occ)" }} />
          <span style={{ fontWeight: 600, fontSize: "var(--fs-control)" }}>저장하지 않은 변경 {changes}건</span>
          {saveError && <span className="meta" style={{ color: "var(--bad)", whiteSpace: "pre-line" }}>{saveError}</span>}
          <span className="spacer" />
          <button type="button" className="btn" onClick={revert}>되돌리기</button>
          <button type="button" className="btn btn--primary" onClick={async () => { if (await save()) setEditingMode(false); }}>저장</button>
        </div>
      )}
    </Dialog>
  );
}
