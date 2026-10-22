import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AppConfig, Camera, Point, SlotTypeId } from "../api/types";
import { handledHere, nextSlotNo, slotState, slotType, viewsBBox } from "../lib/domain";
import { useCfg } from "../state/AppState";
import type { EditHandlers } from "./CameraMedia";
import { useLiveImage } from "./useLiveImage";

/**
 * 카메라 영상 주소: 이 보드가 판정 중이면 워커의 최신 이미지(매 사이클 갱신),
 * 아니면 카메라 스냅샷을 한 번 (refresh() 로 다시).
 */
export function useCameraImage(cam: Camera | undefined) {
  const { cfg, alive, status, savedIps } = useCfg();
  const [nonce, setNonce] = useState(() => Date.now());
  const live = !!cam && alive && handledHere(cfg, cam) && !!status.cameras[cam.ip];
  const unsaved = !!cam && !savedIps.has(cam.ip);
  const url = !cam || unsaved ? null : live
    ? api.latestUrl(cam.ip, new Date(status.cameras[cam.ip]?.updated_at ?? 0).getTime() || nonce)
    : api.snapshotUrl(cam.ip, nonce);
  const img = useLiveImage(url);
  return {
    ...img,
    error: unsaved ? "저장한 뒤 스냅샷을 불러올 수 있습니다" : img.error,
    src: unsaved ? null : img.src,
    live,
    refresh: () => setNonce(Date.now()),
  };
}

/** 한 카메라의 화면 표시 값 */
export function useCameraView(cam: Camera | undefined) {
  const { cfg, alive, status } = useCfg();
  return useMemo(() => {
    if (!cam) return null;
    const cs = alive ? status.cameras[cam.ip] : undefined;
    return {
      bbox: viewsBBox(cfg, cam),
      views: cfg.camera_profiles[cam.profile]?.views ?? [],
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
export function useSlotEditing(ip: string | undefined, newType: SlotTypeId) {
  const { cfg, edit, editQuiet, countChange, toast } = useCfg();
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const cam = ip ? cfg.cameras.find((c) => c.ip === ip) : undefined;

  const setType = useCallback((no: number, t: SlotTypeId) => {
    if (!ip) return;
    edit((d) => {
      const s = findCam(d, ip)?.slots.find((x) => x.no === no);
      if (s) s.type = t;
    }, `${no}번 칸 → ${slotType(t).name}`);
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
    onAdd: (a: Point, b: Point) => {
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
        c.slots.push({ no, type: newType, line: [a, b], name: "", judge: null });
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
