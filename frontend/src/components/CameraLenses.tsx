import type { ReactNode } from "react";
import type { Camera, Det, Rect, Slot } from "../api/types";
import { lensName } from "../lib/domain";
import { CameraMedia, type MediaProps } from "./CameraMedia";
import { useLiveImage } from "./useLiveImage";

/** 이미지를 받기 전 화면 비율 (받으면 실제 크기로 바뀐다) */
const DEFAULT_SIZE: [number, number] = [1280, 720];

type Shared = Omit<MediaProps, "size" | "bbox" | "lens" | "slots" | "imageSrc" | "dets" | "views" | "message" | "overlay" | "lensTag" | "label">;

interface Props extends Shared {
  cam: Camera;
  /** 렌즈별 영상 주소 (useCameraImages) */
  urls: (string | null)[];
  bbox: Rect;
  views: Rect[];
  dets?: Det[];
  /** 영상을 받은 뒤에도 보여 줄 안내 (예: 응답 없음) */
  loadedMessage?: string | null;
  /** 영상을 받지 못했을 때 안내 */
  errorMessage?: string;
  loadingMessage?: string;
  /** 첫 렌즈에만 보여 줄 안내 (예: 아직 칸 없음) — 있으면 위 안내보다 먼저 */
  firstMessage?: string | null;
  /** 렌즈 전체 위에 겹치는 것 (IP, 시각 등) */
  overlay?: ReactNode;
  label: string;
}

/**
 * 카메라 영상: 렌즈마다 사진을 따로 받아 나란히 보여 주고, 그 렌즈의 칸 선분과 박스를 그린다.
 * 모니터링 카드, 큰 창, 선 편집기가 같이 쓴다.
 */
export function CameraLenses({ cam, urls, bbox, views, dets, loadedMessage, errorMessage, loadingMessage, firstMessage, overlay, label, ...shared }: Props) {
  const many = urls.length > 1;
  return (
    <div className="lenses">
      {urls.map((url, lens) => (
        <LensPane
          key={lens} lens={lens} url={url} bbox={bbox} views={views}
          slots={cam.slots.filter((s) => s.lens === lens)}
          dets={dets?.filter((d) => d[0] === lens).map((d) => d.slice(1) as [number, number, number, number, number])}
          message={lens === 0 && firstMessage ? firstMessage : undefined}
          loadedMessage={loadedMessage} errorMessage={errorMessage} loadingMessage={loadingMessage}
          lensTag={many ? lensName(lens) : null}
          label={many ? `${label} · ${lensName(lens)}` : label}
          {...shared}
        />
      ))}
      {overlay}
    </div>
  );
}

function LensPane({ url, message, loadedMessage, errorMessage = "영상을 불러오지 못했습니다", loadingMessage = "불러오는 중…", ...rest }: Shared & {
  lens: number; url: string | null; bbox: Rect; views: Rect[]; slots: Slot[];
  dets?: [number, number, number, number, number][];
  message?: string; loadedMessage?: string | null; errorMessage?: string; loadingMessage?: string;
  lensTag: string | null; label: string;
}) {
  const img = useLiveImage(url);
  const msg = message ?? (!img.src ? (!url || img.error ? errorMessage : loadingMessage) : loadedMessage ?? null);
  return <CameraMedia {...rest} size={img.size ?? DEFAULT_SIZE} imageSrc={img.src} message={msg} />;
}
