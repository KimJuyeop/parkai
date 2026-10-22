import { useState } from "react";
import type { Camera } from "../api/types";
import { MAX_SLOTS, SLOT_TYPES } from "../lib/domain";
import { CameraMedia, type ColorMode } from "./CameraMedia";
import { Icon } from "./Icon";
import { useCameraImage, useCameraView, type useSlotEditing } from "./useCamera";

type Editing = ReturnType<typeof useSlotEditing>;

/**
 * 선 편집기: 도구 줄 + 영상 + 안내. 모니터링 큰 창과 카메라 설정이 같이 쓴다.
 * 편집 상태(선택한 칸, 추가 중)는 부모가 useSlotEditing 으로 들고 있다.
 */
export function LineEditor({ cam, editing, allowStateColor = true }: {
  cam: Camera; editing: Editing; allowStateColor?: boolean;
}) {
  const view = useCameraView(cam)!;
  const img = useCameraImage(cam);
  const [stateColor, setStateColor] = useState(false);
  const mode: ColorMode = stateColor ? "state" : "type";
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
        {mode === "state" ? (
          <div className="legend" aria-label="선 색 범례">
            <span className="legend__item"><span className="legend__swatch legend__swatch--occ" />차량 있음</span>
            <span className="legend__item"><span className="legend__swatch legend__swatch--free" />빈칸</span>
            <span className="legend__item"><span className="legend__swatch legend__swatch--unj" />판정 없음</span>
          </div>
        ) : (
          <div className="legend" aria-label="선 색 범례">
            {SLOT_TYPES.map((t) => (
              <span key={t.id} className="legend__item"><span className="type-bar" style={{ background: t.color }} />{t.name}</span>
            ))}
          </div>
        )}
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
        선 추가 → 두 점 클릭 · 흰 점을 끌어 위치 수정 · 선이나 번호를 눌러 선택 후 옆에서 종류 변경 · Delete 로 삭제 · 최대 {MAX_SLOTS}칸 (현재 {cam.slots.length}칸)
      </div>
    </div>
  );
}
