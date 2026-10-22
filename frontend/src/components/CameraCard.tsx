import type { Camera } from "../api/types";
import { ago, ms, slotType, stateLabel } from "../lib/domain";
import { CameraMedia } from "./CameraMedia";
import { Icon } from "./Icon";
import { SlotChip } from "./ui";
import { useCameraImage, useCameraView } from "./useCamera";

/** 모니터링 카드: 영상(누르면 크게 보기) · 칸 칩 · 처리 시간 · 선 편집 */
export function CameraCard({ cam, onOpen, onEdit }: { cam: Camera; onOpen: () => void; onEdit: () => void }) {
  const view = useCameraView(cam)!;
  const img = useCameraImage(cam);
  const cs = view.cs;
  const t = cs?.timings ?? {};
  const meta = view.offline
    ? cs?.error ?? "카메라 응답 없음"
    : cs ? `수신 ${ms(t.fetch)} · 추론 ${ms(t.infer)} · 차량 ${cs.boxes ?? "-"}대` : "판정 결과 없음 · 스냅샷 표시";
  const msg = !img.src ? (img.error ? "카메라 연결 안 됨" : "불러오는 중…") : view.offline ? "만공등은 마지막 상태 유지" : null;

  return (
    <article className={`card${view.offline ? " card--offline" : ""}`}>
      <button type="button" className="card__media" onClick={onOpen} aria-label={`${cam.ip} 크게 보기`} title="크게 보기">
        <CameraMedia
          bbox={view.bbox} views={view.views} slots={cam.slots} states={view.states} imageSrc={img.src}
          message={msg} dimMessage colorMode="state" label={`${cam.ip} 영상`}
          overlay={
            <div className="media__top">
              <span className="media__ip">{cam.ip}</span>
              <span className="spacer" />
              {view.offline && <span className="badge badge--solid-bad">응답 없음</span>}
              <span className="media__time">{cs?.updated_at ? ago(cs.updated_at) : ""}</span>
            </div>
          }
        />
      </button>
      <div className="card__chips chips">
        {cam.slots.length === 0 && <span className="meta">설정된 칸 없음</span>}
        {cam.slots.map((s) => {
          const st = view.states(s.no);
          return <SlotChip key={s.no} no={s.no} state={st} type={s.type} title={`${s.no}번 · ${slotType(s.type).name} · ${stateLabel(st)}`} />;
        })}
      </div>
      <div className="card__foot">
        <span className="card__meta" title={meta}>{meta}</span>
        <button type="button" className="btn btn--ghost" onClick={onEdit} aria-label={`${cam.ip} 선 편집`}>
          <Icon name="line" size={14} />선 편집
        </button>
      </div>
    </article>
  );
}
