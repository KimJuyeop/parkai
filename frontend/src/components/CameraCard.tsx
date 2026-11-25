import type { Camera } from "../api/types";
import { ago, ms, slotType, stateLabel } from "../lib/domain";
import { useCfg } from "../state/AppState";
import { CameraLenses } from "./CameraLenses";
import { Icon } from "./Icon";
import { SlotChip } from "./ui";
import { useCameraImages, useCameraView } from "./useCamera";

/** 모니터링 카드: 영상(누르면 크게 보기) · 칸 칩 · 처리 시간 · 선 편집 */
export function CameraCard({ cam, span = 1, onOpen, onEdit }: {
  cam: Camera; /** 카드가 차지할 칸 수 (렌즈 수) */ span?: number; onOpen: () => void; onEdit: () => void;
}) {
  const { status } = useCfg();
  const view = useCameraView(cam)!;
  const img = useCameraImages(cam);
  const cs = view.cs;
  const t = cs?.timings ?? {};
  // 좁은 카드에서는 항목 사이에서 줄을 바꾼다 (항목 안에서는 끊지 않음)
  const meta = view.offline
    ? [cs?.error ?? "카메라 응답 없음"]
    : cs ? [`수신 ${ms(t.fetch)}`, `추론 ${ms(t.infer)}`, `차량 ${cs.boxes ?? "-"}대`] : ["판정 결과 없음", "스냅샷 표시"];

  return (
    <article className={`card${view.offline ? " card--offline" : ""}`} style={span > 1 ? { gridColumn: `span ${span}` } : undefined}>
      <div className="card__media">
        <button type="button" className="card__open" onClick={onOpen} aria-label={`${cam.ip} 크게 보기`} title="크게 보기">
          <CameraLenses
            cam={cam} urls={img.urls} bbox={view.bbox} views={view.views} states={view.states}
            errorMessage={img.unsavedError ?? "카메라 연결 안 됨"} loadedMessage={view.offline ? "만공등은 마지막 상태 유지" : null}
            dimMessage colorMode="state" compact label={`${cam.ip} 영상`}
            overlay={
              <div className="media__top">
                <span className="media__ip">{cam.ip}</span>
                <span className="spacer" />
                {view.offline && <span className="badge badge--solid-bad">응답 없음</span>}
                <span className="media__time">{cs?.updated_at ? ago(cs.updated_at, status.now) : ""}</span>
              </div>
            }
          />
        </button>
        {/* 칸 칩이 카드 폭을 다 쓰게 영상 위에 둔다 (칸 12개 카메라도 칩이 두세 줄로 끝나게) */}
        <button type="button" className="card__edit" onClick={onEdit} aria-label={`${cam.ip} 선 편집`} title="선 편집">
          <Icon name="line" size={14} /><span className="card__edit-label">선 편집</span>
        </button>
      </div>
      <div className="card__foot">
        <div className="chips chips--sm">
          {cam.slots.length === 0 && <span className="meta">설정된 칸 없음</span>}
          {cam.slots.map((s) => {
            const st = view.states(s.no);
            return <SlotChip key={s.no} no={s.no} state={st} type={s.type} title={`${s.no}번 · ${slotType(s.type).name} · ${stateLabel(st)}`} />;
          })}
        </div>
        <div className={`card__meta${view.offline ? " card__meta--wrap" : ""}`}>
          {meta.map((m, i) => <span key={i}>{m}{i < meta.length - 1 && " ·"}</span>)}
        </div>
      </div>
    </article>
  );
}
