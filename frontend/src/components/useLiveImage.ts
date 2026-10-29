import { useEffect, useRef, useState } from "react";

/**
 * 이미지를 미리 받아 두었다가 다 받으면 바꾼다 (갱신할 때 깜빡이지 않게).
 * url 이 null 이면 받지 않는다. size 는 받은 이미지의 원래 크기 (선·박스 좌표 환산용).
 */
export function useLiveImage(url: string | null) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [size, setSize] = useState<[number, number] | null>(null);
  const current = useRef<string | null>(null);

  useEffect(() => {
    if (!url) return;
    current.current = url;
    setLoading(true);
    const img = new Image();
    img.onload = () => {
      if (current.current !== url) return;
      setSrc(url);
      setSize([img.naturalWidth, img.naturalHeight]);
      setError(null);
      setLoading(false);
    };
    img.onerror = () => {
      if (current.current !== url) return;
      setError("영상을 불러오지 못했습니다");
      setLoading(false);
    };
    img.src = url;
    return () => {
      img.onload = null;
      img.onerror = null;
    };
  }, [url]);

  return { src, error, loading, size };
}
