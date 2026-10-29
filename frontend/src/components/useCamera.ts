import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AppConfig, Camera, Point, SlotTypeId } from "../api/types";
import { handledHere, lensCount, nextSlotNo, slotState, slotType, viewsBBox } from "../lib/domain";
import { useCfg } from "../state/AppState";
import type { EditHandlers } from "./CameraMedia";

/**
 * 렌즈별 영상 주소: 이 보드가 판정 중이면 워커의 최신 원본(매 사이클 갱신),
 * 아니면 카메라 스냅샷을 한 번 (refresh() 로 다시). 저장하지 않은 카메라는 주소가 없다.
 */
export function useCameraImages(cam: Camera | undefined) {
  const { cfg, alive, status, savedIps } = useCfg();
  const [nonce, setNonce] = useState(() => Date.now());
  const live = !!cam && alive && handledHere(cfg, cam) && !!status.cameras[cam.ip];
  const unsaved = !!cam && !savedIps.has(cam.ip);
  const t = live ? new Date(status.cameras[cam!.ip]?.updated_at ?? 0).getTime() || nonce : nonce;
  const urls = !cam ? [] : Array.from({ length: lensCount(cfg, cam) }, (_, i) =>
    unsaved ? null : live ? api.latestUrl(cam.ip, i, t) : api.snapshotUrl(cam.ip, i, t));
  return {
    urls,
    live,
    unsavedError: unsaved ? "저장한 뒤 스냅샷을 불러올 수 있습니다" : null,
    refresh: () => setNonce(Date.now()),
  };
}

/** 한 카메라의 화면 표시 값 */
export function useCameraView(cam: Camera | undefined) {
  const { cfg, alive, status } = useCfg();
  return useMemo(() => {
    if (!cam) return null;
    const cs = alive ? status.cameras[cam.ip] : undefined;
    const views = cfg.camera_profiles[cam.profile]?.views ?? [];
    return {
      bbox: viewsBBox(views),
      views,
      lenses: lensCount(cfg, cam),
      cs,
      offline: cs?.status === "no_response",
      states: (no: number) => slotState(cs, no),
    };
  }, [cfg, cam, alive, status]);
}

function findCam(d: AppConfig, ip: string) {
  return d.cameras.find((c) => c.ip === ip);
}

/** 칸 선분 편집: 추가·끝점 이동·종류 변경·삭제 (모두 저장 전 설정에 반영) */
export function useSlotEditing(ip: string | undefined) {
  const { cfg, edit, editQuiet, countChange, toast } = useCfg();
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  // 새 선은 마지막으로 고른 종류로 긋는다 (종류는 칸을 선택해 옆 패널에서 바꾼다).
  // 같은 종류 칸을 연달아 그을 때 매번 바꾸지 않아도 된다.
  const [newType, setNewType] = useState<SlotTypeId>("normal");
  const cam = ip ? cfg.cameras.find((c) => c.ip === ip) : undefined;

  const setType = useCallback((no: number, t: SlotTypeId) => {
    if (!ip) return;
    edit((d) => {
      const s = findCam(d, ip)?.slots.find((x) => x.no === no);
      if (s) s.type = t;
    }, `${no}번 칸 → ${slotType(t).name}`);
    setNewType(t);
  }, [ip, edit]);

  const remove = useCallback((no: number) => {
    if (!ip) return;
    edit((d) => {
      const c = findCam(d, ip);
      if (c) c.slots = c.slots.filter((s) => s.no !== no);
    }, `${no}번 칸 삭제`);
    setSelected(null);
  }, [ip, edit]);

  const handlers: EditHandlers = {
    adding,
    onAdd: (lens: number, a: Point, b: Point) => {
      if (!ip || !cam) return;
      const no = nextSlotNo(cam);
      if (no == null) {
        toast("카메라당 최대 12칸입니다");
        setAdding(false);
        return;
      }
      edit((d) => {
        const c = findCam(d, ip);
        if (!c) return;
        c.slots.push({ no, type: newType, lens, line: [a, b], name: "", judge: null });
        c.slots.sort((x, y) => x.no - y.no);
      }, `${no}번 칸 추가 (${slotType(newType).name})`);
      setSelected(no);
      setAdding(false);
    },
    onMove: (no, end, p) => {
      if (!ip) return;
      editQuiet((d) => {
        const s = findCam(d, ip)?.slots.find((x) => x.no === no);
        if (s) s.line[end] = p;
      });
    },
    onMoveEnd: (no) => countChange(`${no}번 칸 위치 수정`),
    onDelete: remove,
    onCancelAdd: () => setAdding(false),
  };

  return {
    cam, handlers, selected, setSelected, setType, remove, adding,
    toggleAdd: () => setAdding((v) => !v),
    full: !!cam && nextSlotNo(cam) == null,
  };
}
