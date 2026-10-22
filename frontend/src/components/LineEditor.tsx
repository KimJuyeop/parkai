import { useState } from "react";
import type { Camera, SlotTypeId } from "../api/types";
import { MAX_SLOTS } from "../lib/domain";
import { CameraMedia, type ColorMode } from "./CameraMedia";
import { Icon } from "./Icon";
import { TypeSegment } from "./ui";
import { useCameraImage, useCameraView, type useSlotEditing } from "./useCamera";

type Editing = ReturnType<typeof useSlotEditing>;

/**
 * 선 편집기: 도구 줄 + 영상 + 안내. 모니터링 큰 창과 카메라 설정이 같이 쓴다.
 * 편집 상태(선택한 칸, 추가 중)는 부모가 useSlotEditing 으로 들고 있다.
 */
export function LineEditor({ cam, editing, newType, setNewType, allowStateColor = true }: {
  cam: Camera; editing: Editing; newType: SlotTypeId; setNewType: (t: SlotTypeId) => void; allowStateColor?: boolean;
}) {
  const view = useCameraView(cam)!;
  const img = useCameraImage(cam);
  const [stateColor, setStateColor] = useState(false);
  const mode: ColorMode = stateColor ? "state" : "type";
  // 종류 고르기: 선을 고른 상태면 그 칸의 종류를 바꾸고, 아니면 다음에 그을 선의 종류를 정한다.
  // 고른 종류는 다음 새 선에도 이어 쓴다 (같은 종류 칸을 연달아 긋기 편하게).
  const sel = !editing.adding && editing.selected != null ? cam.slots.find((s) => s.no === editing.selected) : undefined;
  const typeLabel = sel ? `${sel.no}번 칸 종류` : "새 선 종류";
  const pickType = (t: SlotTypeId) => {
    if (sel) editing.setType(sel.no, t);
    setNewType(t);
  };
  const msg = cam.slots.length === 0 && !editing.adding ? "아직 칸이 없습니다 · 선 추가로 시작하세요"
    : !img.src ? (img.error ?? "영상을 불러오는 중…") : null;

  return (
    <div className="panel panel--clip">
      <div className="editor-bar">
        <button type="button" className={`btn ${editing.adding ? "btn--on" : ""}`} aria-pressed={editing.adding}
          disabled={editing.full && !editing.adding} onClick={editing.toggleAdd}>
          <Icon name="plus" />
          {editing.adding ? "추가 취소" : editing.full ? `최대 ${MAX_SLOTS}칸` : "선 추가"}
        </button>
        <span className={`meta${sel ? " text-accent strong" : ""}`}>{typeLabel}</span>
        <TypeSegment value={sel ? sel.type : newType} onPick={pickType} label={typeLabel} />
        <span className="spacer" />
        {allowStateColor && (
          <label className="check check--inline">
            <input type="checkbox" checked={stateColor} onChange={(e) => setStateColor(e.target.checked)} />
            판정 결과로 색 표시
          </label>
        )}
        <button type="button" className="btn" onClick={img.refresh} disabled={img.live} title={img.live ? "판정 중에는 매 사이클 자동으로 갱신됩니다" : undefined}>
          <Icon name="refresh" />스냅샷 새로고침
        </button>
      </div>
      <CameraMedia
        bbox={view.bbox} views={view.views} slots={cam.slots} states={view.states} imageSrc={img.src}
        message={msg} colorMode={mode} selectedNo={editing.selected} onSelect={editing.setSelected}
        edit={editing.handlers} label={`${cam.ip} 스냅샷과 칸 선분`}
      />
      <div className="editor-hint">
        선 추가 → 두 점 클릭 · 흰 점을 끌어 위치 수정 · 선이나 번호를 눌러 선택 후 종류 변경 · Delete 로 삭제 · 최대 {MAX_SLOTS}칸 (현재 {cam.slots.length}칸)
      </div>
    </div>
  );
}
