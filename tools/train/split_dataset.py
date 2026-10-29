"""자동 라벨링 결과(images/, labels/)를 학습/검증/시험 폴더로 나눈다 (ST Model Zoo darknet_yolo 형식).

    python tools/train/split_dataset.py dataset --out dataset_split

결과: dataset_split/{train,val,test}/ 에 사진(.jpg)과 같은 이름의 라벨(.txt)이 함께 들어간다.
--group camera (기본): 파일 이름의 카메라 IP 가 같은 화면(시간대가 다른 사진, 두 렌즈, 조각)은 한 쪽에만 넣는다.
             거의 같은 장면이 학습과 시험에 함께 들어가 점수가 부풀려지는 것을 막는다.
--group folder: 같은 폴더끼리 / image: 화면마다 따로
"""

from __future__ import annotations

import argparse
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="autolabel.py 의 --out 폴더")
    ap.add_argument("--out", type=Path, default=Path("dataset_split"))
    ap.add_argument("--val", type=float, default=0.1)
    ap.add_argument("--test", type=float, default=0.1)
    ap.add_argument("--group", choices=["camera", "folder", "image"], default="camera")
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()

    images = sorted((args.src / "images").glob("*.jpg"))
    rng = random.Random(args.seed)
    # 파일 이름 = <폴더>__<하위 폴더...>__<원본 이름>_v<화면>
    ip_re = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
    groups: dict[str, list[Path]] = defaultdict(list)
    for p in images:
        if args.group == "camera" and (ips := ip_re.findall(p.stem)):
            key = ips[-1]
        elif args.group == "folder":
            key = p.stem.rsplit("__", 1)[0]
        else:
            key = p.stem
        groups[key].append(p)
    keys = sorted(groups)
    rng.shuffle(keys)
    n = len(keys)
    n_test, n_val = round(n * args.test), round(n * args.val)
    split = {"test": keys[:n_test], "val": keys[n_test : n_test + n_val], "train": keys[n_test + n_val :]}

    for name, ks in split.items():
        d = args.out / name
        d.mkdir(parents=True, exist_ok=True)
        count = 0
        for k in ks:
            for img in groups[k]:
                lbl = args.src / "labels" / f"{img.stem}.txt"
                shutil.copy2(img, d / img.name)
                shutil.copy2(lbl, d / lbl.name) if lbl.exists() else (d / lbl.name).write_text("")
                count += 1
        print(f"{name}: 화면 {count}개 ({len(ks)} 묶음)")


if __name__ == "__main__":
    main()
