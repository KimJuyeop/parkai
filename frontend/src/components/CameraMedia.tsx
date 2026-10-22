import { useEffect, useRef, useState, type KeyboardEvent as RKeyboardEvent, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import type { Point, Slot } from "../api/types";
import { slotType, type SlotState } from "../lib/domain";

export type ColorMode = "state" | "type";

export interface EditHandlers {
  adding: boolean;
  onAdd: (a: Point, b: Point) => void;
  onMove: (no: number, end: 0 | 1, p: Point) => void;
  onMoveEnd: (no: number) => void;
  onDelete: (no: number) => void;
  onCancelAdd: () => void;
}

interface Props {
  /** 화면에 보이는 영역 [x, y, w, h] (기준 해상도 좌표 = 선 좌표계) */
  bbox: [number, number, number, number];
  slots: Slot[];
  states: (no: number) => SlotState;
  imageSrc: string | null;
  message?: string | null;
  dimMessage?: boolean;
  colorMode: ColorMode;
  selectedNo?: number | null;
  onSelect?: (no: number) => void;
  edit?: EditHandlers;
  dets?: [number, number, number, number, number][];
  /** 분석 영역 경계 (점선) */
  views?: [number, number, number, number][];
  overlay?: ReactNode;
  label: string;
}

const FREE_DASH = "10 6";

function lineColor(mode: ColorMode, slot: Slot, st: SlotState): string {
  if (mode === "type") return slotType(slot.type).color;
  return st === true ? "var(--occ)" : st === false ? "var(--free)" : "var(--unj)";
}

/** 카메라 영상 위에 칸 선분을 그린다. edit 를 주면 선 추가·끝점 끌기·삭제가 된다 */
export function CameraMedia(props: Props) {
  const { bbox, slots, states, imageSrc, message, dimMessage, colorMode, selectedNo, onSelect, edit, dets, views, overlay, label } = props;
  const [x0, y0, bw, bh] = bbox;
  const wrap = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [px, setPx] = useState(1); // 화면 1px 이 기준 좌표로 몇인지
  const drag = useRef<{ no: number; end: 0 | 1; moved: boolean } | null>(null);
  const [pending, setPending] = useState<Point | null>(null);
  const [hover, setHover] = useState<Point | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => el.clientWidth && setPx(bw / el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [bw]);

  useEffect(() => {
    if (!edit?.adding) {
      setPending(null);
      setHover(null);
    }
  }, [edit?.adding]);

  const toRef = (e: { clientX: number; clientY: number }): Point => {
    const s = svg.current!;
    const pt = s.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(s.getScreenCTM()!.inverse());
    const cx = Math.min(x0 + bw, Math.max(x0, p.x));
    const cy = Math.min(y0 + bh, Math.max(y0, p.y));
    return [Math.round(cx), Math.round(cy)];
  };

  const onPointerDown = (e: RPointerEvent<SVGSVGElement>) => {
    if (!edit?.adding) return;
    const p = toRef(e);
    if (!pending) {
      setPending(p);
      setHover(p);
    } else {
      edit.onAdd(pending, p);
      setPending(null);
      setHover(null);
    }
  };
  const onPointerMove = (e: RPointerEvent<SVGSVGElement>) => {
    if (drag.current && edit) {
      drag.current.moved = true;
      edit.onMove(drag.current.no, drag.current.end, toRef(e));
    } else if (pending) setHover(toRef(e));
  };
  const endDrag = () => {
    if (drag.current?.moved && edit) edit.onMoveEnd(drag.current.no);
    drag.current = null;
  };
  const grab = (no: number, end: 0 | 1) => (e: RPointerEvent<SVGCircleElement>) => {
    e.stopPropagation();
    svg.current?.setPointerCapture(e.pointerId);
    drag.current = { no, end, moved: false };
    onSelect?.(no);
  };
  const onKeyDown = (e: RKeyboardEvent) => {
    if (!edit) return;
    if (e.key === "Escape") edit.onCancelAdd();
    if ((e.key === "Delete" || e.key === "Backspace") && selectedNo != null) {
      e.preventDefault();
      edit.onDelete(selectedNo);
    }
  };

  const u = px; // 화면 px → 기준 좌표
  return (
    <div ref={wrap} className="media" style={{ aspectRatio: `${bw} / ${bh}` }}>
      {imageSrc && <img className="media__img" src={imageSrc} alt="" draggable={false} />}
      <svg ref={svg} className="media__svg" viewBox={`${x0} ${y0} ${bw} ${bh}`} preserveAspectRatio="none"
        role="img" aria-label={label} tabIndex={edit ? 0 : undefined}
        style={{ cursor: edit?.adding ? "crosshair" : "default" }}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={endDrag} onPointerCancel={endDrag}
        onKeyDown={onKeyDown}>
        {views && views.length > 1 && views.slice(1).map((v, i) => (
          <line key={i} x1={v[0]} y1={v[1]} x2={v[0]} y2={v[1] + v[3]} stroke="var(--media-line)" strokeWidth={u} strokeDasharray={`${4 * u} ${4 * u}`} />
        ))}
        {dets?.map((d, i) => (
          <rect key={i} x={d[0]} y={d[1]} width={d[2] - d[0]} height={d[3] - d[1]} fill="none"
            stroke="rgba(255,255,255,.55)" strokeWidth={1.5 * u} />
        ))}
        {slots.map((s) => {
          const st = states(s.no);
          const color = lineColor(colorMode, s, st);
          const sel = s.no === selectedNo;
          const [[ax, ay], [bx, by]] = s.line;
          const w = (sel ? 6 : edit ? 4.5 : st == null ? 2.5 : 4) * u;
          const dash = colorMode === "state" && st === false ? FREE_DASH.split(" ").map((n) => Number(n) * u).join(" ") : undefined;
          const mx = (ax + bx) / 2 + 22 * u, my = (ay + by) / 2;
          const tw = (String(s.no).length * 8 + 10) * u, th = 18 * u;
          return (
            <g key={s.no}>
              {sel && <line x1={ax} y1={ay} x2={bx} y2={by} stroke="#fff" strokeWidth={w + 5 * u} strokeLinecap="round" />}
              <line x1={ax} y1={ay} x2={bx} y2={by} stroke={color} strokeWidth={w} strokeLinecap="round" strokeDasharray={dash} />
              {onSelect && (
                <line x1={ax} y1={ay} x2={bx} y2={by} stroke="transparent" strokeWidth={16 * u}
                  style={{ cursor: "pointer" }} onPointerDown={(e) => { if (!edit?.adding) { e.stopPropagation(); onSelect(s.no); } }} />
              )}
              <g style={{ cursor: onSelect ? "pointer" : "default" }}
                onPointerDown={(e) => { if (onSelect && !edit?.adding) { e.stopPropagation(); onSelect(s.no); } }}>
                <rect x={mx - tw / 2} y={my - th / 2} width={tw} height={th} rx={4 * u}
                  fill="rgba(0,0,0,.75)" stroke={sel ? "#fff" : "none"} strokeWidth={u} />
                <text className="slot-tag" x={mx} y={my} fontSize={12 * u} textAnchor="middle" dominantBaseline="central">{s.no}</text>
              </g>
              {edit && !edit.adding && ([0, 1] as const).map((end) => (
                <circle key={end} cx={s.line[end][0]} cy={s.line[end][1]} r={6 * u} fill="#fff" stroke={color} strokeWidth={2.5 * u}
                  style={{ cursor: "grab" }} onPointerDown={grab(s.no, end)} />
              ))}
            </g>
          );
        })}
        {pending && hover && (
          <>
            <line x1={pending[0]} y1={pending[1]} x2={hover[0]} y2={hover[1]} stroke="var(--draft-line)" strokeWidth={3 * u}
              strokeDasharray={`${6 * u} ${4 * u}`} />
            <circle cx={pending[0]} cy={pending[1]} r={6 * u} fill="var(--draft-line)" />
          </>
        )}
      </svg>
      {message && <div className={`media__msg${dimMessage ? " media__msg--dim" : ""}`}>{message}</div>}
      {overlay}
      {edit?.adding && <div className="media__hint">{pending ? "두 번째 점을 클릭하세요 · Esc 취소" : "첫 번째 점을 클릭하세요 · Esc 취소"}</div>}
    </div>
  );
}
