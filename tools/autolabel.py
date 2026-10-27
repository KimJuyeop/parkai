"""자동 라벨링: 기존 현장 YOLOv4(darknet)로 사진에 차량 박스를 붙인다.

ST 모델(st_yoloxn) 추가 학습용 데이터를 만든다. 사람은 결과를 Label Studio에서 훑어보고 틀린 것만 고친다.

    python tools/autolabel.py <사진 폴더> --cfg yolo.cfg --weights yolov4_best.weights --out dataset

- 사진 폴더 아래를 모두 찾는다 (현장별 하위 폴더 권장: 사진폴더/현장이름/*.jpg)
- 판정과 같은 단위로 자른다: 1280x960 은 위 절반의 640x480 두 화면, 그 밖의 크기는 사진 전체가 한 화면
  (작은 모델은 큰 사진을 통째로 넣으면 차를 못 알아본다. 학습 화면이 판정 화면과 같아야 한다)
- Jetson 이 저장한 *.jpgleft.jpg / *.jpgright.jpg 는 640x480 화면을 1280x720 으로 늘린 사본이라
  판정 화면과 비율이 달라 건너뛴다 (원본 1280x960 을 쓴다. --keep-presplit 로 끌 수 있음)
- 같은 카메라의 거의 같은 사진은 건너뛴다 (--dedupe 로 기준 조정, 0이면 끔)

결과 (YOLO 형식, Label Studio로 가져올 수 있음):
    dataset/images/*.jpg      잘라낸 화면
    dataset/labels/*.txt      class cx cy w h (0~1, class 0 = car)
    dataset/classes.txt
    dataset/review.txt        사람이 꼭 봐야 할 화면 (애매한 박스가 있거나 차가 하나도 없는 것)
    dataset/preview/*.jpg     박스를 그린 미리보기 (--preview)

Label Studio로 가져오기 (예전과 같은 방식, 박스가 미리 채워짐):
    pip install label-studio-converter
    label-studio-converter import yolo -i dataset -o dataset/ls_tasks.json \\
        --image-root-url "/data/local-files/?d=dataset/images"

주의: darknet 모델은 OpenCV 4.x 에서만 읽힌다 (5.x 에서 빠짐). 별도 가상환경에서
    pip install "opencv-python-headless<5" numpy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def views_for(w: int, h: int, mode: str) -> list[tuple[int, int, int, int]]:
    """잘라낼 화면 (x, y, w, h). parkai 카메라 프로필의 views 와 같아야 한다."""
    if mode == "full":
        return [(0, 0, w, h)]
    if mode == "auto" and w * 3 == h * 4:  # 4:3 (1280x960 등): 위 절반에 두 화면이 들어 있는 카메라
        return [(0, 0, w // 2, h // 2), (w // 2, 0, w - w // 2, h // 2)]
    if mode == "split":
        half = w // 2
        return [(0, 0, half, h), (half, 0, w - half, h)]
    return [(0, 0, w, h)]


def is_presplit(p: Path) -> bool:
    """Jetson 이 화면 하나를 1280x720 으로 늘려 저장한 사본 (*.jpgleft.jpg, *.jpgright.jpg)."""
    return p.stem.endswith(("jpgleft", "jpgright"))


def thumb(img: np.ndarray) -> np.ndarray:
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (32, 24), interpolation=cv2.INTER_AREA).astype(
        np.float32
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path, help="사진 폴더")
    ap.add_argument("--cfg", type=Path, required=True)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("dataset"))
    ap.add_argument("--size", type=int, default=416, help="YOLOv4 입력 크기 (cfg 와 같게)")
    ap.add_argument("--conf", type=float, default=0.5, help="이 점수 이상만 라벨로 저장")
    ap.add_argument("--low", type=float, default=0.25, help="이 점수~conf 는 애매함 (검토 목록)")
    ap.add_argument("--views", choices=["auto", "full", "split"], default="auto")
    ap.add_argument("--dedupe", type=float, default=4.0, help="직전 사진과 차이가 이보다 작으면 건너뜀")
    ap.add_argument("--preview", action="store_true", help="박스를 그린 미리보기 저장")
    ap.add_argument("--keep-presplit", action="store_true", help="*.jpgleft/*.jpgright 도 쓴다")
    args = ap.parse_args()

    if not hasattr(cv2.dnn, "readNetFromDarknet"):
        sys.exit(
            f'OpenCV {cv2.__version__} 은 darknet 을 읽지 못합니다: pip install "opencv-python-headless<5"'
        )
    net = cv2.dnn.readNetFromDarknet(str(args.cfg), str(args.weights))
    model = cv2.dnn.DetectionModel(net)
    model.setInputParams(size=(args.size, args.size), scale=1 / 255, swapRB=True)

    out_img, out_lbl, out_prev = args.out / "images", args.out / "labels", args.out / "preview"
    for d in (out_img, out_lbl) + ((out_prev,) if args.preview else ()):
        d.mkdir(parents=True, exist_ok=True)
    (args.out / "classes.txt").write_text("car\n", encoding="utf-8")

    files = sorted(p for p in args.src.rglob("*") if p.suffix.lower() in IMAGE_EXT)
    if not args.keep_presplit:
        skipped = [p for p in files if is_presplit(p)]
        files = [p for p in files if not is_presplit(p)]
        if skipped:
            print(f"Jetson 화면 사본(*.jpgleft/*.jpgright) {len(skipped)}장 건너뜀 (원본 사진을 쓴다)")
    last: dict[tuple[Path, int], np.ndarray] = {}
    review: list[str] = []
    n_views = n_boxes = n_skip = n_dark = 0
    for i, f in enumerate(files, 1):
        img = cv2.imread(str(f))
        if img is None:
            print(f"읽기 실패: {f}")
            continue
        h, w = img.shape[:2]
        rel = f.relative_to(args.src)
        stem = "__".join(rel.with_suffix("").parts)
        for vi, (x, y, vw, vh) in enumerate(views_for(w, h, args.views)):
            v = img[y : y + vh, x : x + vw]
            if v.mean() < 10:  # 검은 화면 (카메라 없음/꺼짐)
                n_dark += 1
                continue
            t = thumb(v)
            key = (f.parent, vi)
            if args.dedupe > 0 and key in last and float(np.abs(t - last[key]).mean()) < args.dedupe:
                n_skip += 1
                continue
            last[key] = t

            _, scores, boxes = model.detect(v, confThreshold=args.low, nmsThreshold=0.45)
            scores = np.ravel(scores) if len(scores) else np.zeros(0)
            keep = [(s, b) for s, b in zip(scores, boxes, strict=False) if s >= args.conf]
            unsure = [s for s in scores if s < args.conf]

            name = f"{stem}_v{vi}"
            cv2.imwrite(str(out_img / f"{name}.jpg"), v, [cv2.IMWRITE_JPEG_QUALITY, 95])
            lines = []
            for _, (bx, by, bw, bh) in keep:
                bx, by = max(0, bx), max(0, by)
                bw, bh = min(bw, vw - bx), min(bh, vh - by)
                cx, cy = (bx + bw / 2) / vw, (by + bh / 2) / vh
                lines.append(f"0 {cx:.6f} {cy:.6f} {bw / vw:.6f} {bh / vh:.6f}")
            (out_lbl / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            if unsure or not keep:
                why = f"애매한 박스 {len(unsure)}개" if unsure else "차 없음"
                review.append(f"{name}.jpg\t{why}")
            if args.preview:
                p = v.copy()
                for s, (bx, by, bw, bh) in keep:
                    cv2.rectangle(p, (bx, by), (bx + bw, by + bh), (0, 200, 0), 2)
                    cv2.putText(p, f"{s:.2f}", (bx + 2, by + 16), 0, 0.5, (0, 200, 0), 2)
                for s, (bx, by, bw, bh) in zip(scores, boxes, strict=False):
                    if s < args.conf:
                        cv2.rectangle(p, (bx, by), (bx + bw, by + bh), (0, 165, 255), 2)
                cv2.imwrite(str(out_prev / f"{name}.jpg"), p, [cv2.IMWRITE_JPEG_QUALITY, 85])
            n_views += 1
            n_boxes += len(keep)
        if i % 50 == 0 or i == len(files):
            print(f"{i}/{len(files)} 사진, 화면 {n_views}, 박스 {n_boxes}, 비슷해서 건너뜀 {n_skip}")

    (args.out / "review.txt").write_text("\n".join(review) + ("\n" if review else ""), encoding="utf-8")
    print(
        f"완료: 화면 {n_views}개, 차량 박스 {n_boxes}개, 검토 필요 {len(review)}개 (review.txt), "
        f"비슷해서 건너뜀 {n_skip}, 검은 화면 {n_dark}"
    )


if __name__ == "__main__":
    main()
