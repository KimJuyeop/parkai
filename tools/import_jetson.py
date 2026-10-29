"""기존 Jetson 시스템의 카메라 설정(JSON, 카메라마다 한 파일)을 parkai 설정으로 옮긴다.

    python tools/import_jetson.py <Jetson 설정 폴더 또는 파일들> --out config.json [--base 기존설정.json]

Jetson 파일 형식 (파일 이름 = 카메라 IP):
    {"camera_ip_address": "...", "camera_id": "...", "camera_password": "...",
     "controller_ip_address": "0.0.0.0",
     "detect_line_infos": [{"number": 1, "parking_sector": 1,
                            "start_x": .., "start_y": .., "end_x": .., "end_y": ..}, ...]}

- Jetson 선분 좌표는 두 렌즈 사진을 640x480 으로 줄여 붙인 1280x960 합친 사진 기준이다.
  parkai 는 렌즈별 원본을 받으므로 렌즈 번호 + 렌즈 사진 대비 비율로 바꾼다:
  선분 가운데가 x < 640 이면 렌즈 1(왼쪽), 아니면 렌즈 2. 비율 = ((x - 640 x 렌즈) / 640, y / 480)
  (합친 사진의 각 칸은 렌즈 원본을 640x480 으로 늘리고 줄인 것이라 이 변환이 정확하다)
- 프로필(기본 "IDIS 렌즈 2개")이 없으면 IDIS 스냅샷 주소로 만든다
- 칸 번호(number)는 그대로 쓴다 (서버 전송 ps01~ps12 와 맞물림)
- parking_sector(주차 종류): 1 일반, 2 장애인, 4 전기차, 6 경차.
  3(교통약자)은 parkai 에 아직 없어 일반으로 두고 알려 준다
- 카메라 계정은 카메라별 계정(own_account)으로 옮긴다. 결과 파일에 비밀번호가 들어가므로 저장소에 넣지 않는다
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parkai.core.config import IDIS_SNAPSHOT_URL, MAX_SLOTS_PER_CAMERA, AppConfig, CameraProfile  # noqa: E402

DEFAULT_PROFILE = "IDIS 렌즈 2개"
TILE_W, TILE_H = 640, 480  # Jetson 합친 사진에서 렌즈 하나가 차지하는 크기
# Jetson parking_sector → parkai 주차 종류. 3(교통약자)은 parkai 종류가 정해지면 추가
SECTOR_TYPES = {1: "normal", 2: "disabled", 4: "ev", 6: "compact"}


def to_lens(x1: float, y1: float, x2: float, y2: float) -> tuple[int, list[list[float]]]:
    """합친 사진 좌표 → (렌즈 번호, 렌즈 사진 대비 비율 선분)."""
    lens = 0 if (x1 + x2) / 2 < TILE_W else 1

    def norm(x: float, y: float) -> list[float]:
        nx = (x - TILE_W * lens) / TILE_W
        return [round(min(1.0, max(0.0, nx)), 4), round(min(1.0, max(0.0, y / TILE_H)), 4)]

    return lens, [norm(x1, y1), norm(x2, y2)]


def convert(data: dict, profile: str) -> tuple[dict, Counter]:
    sectors: Counter = Counter()
    slots = []
    for li in sorted(data.get("detect_line_infos") or [], key=lambda x: x["number"]):
        no = int(li["number"])
        if not 1 <= no <= MAX_SLOTS_PER_CAMERA:
            print(f"  {data['camera_ip_address']}: {no}번 칸은 1~{MAX_SLOTS_PER_CAMERA} 범위 밖이라 건너뜀")
            continue
        sectors[li.get("parking_sector")] += 1
        lens, line = to_lens(li["start_x"], li["start_y"], li["end_x"], li["end_y"])
        slot_type = SECTOR_TYPES.get(li.get("parking_sector"), "normal")
        slots.append({"no": no, "type": slot_type, "lens": lens, "line": line})
    ctrl = data.get("controller_ip_address")
    cam = {
        "ip": data["camera_ip_address"],
        "profile": profile,
        "own_account": True,
        "user": data.get("camera_id", ""),
        "password": data.get("camera_password", ""),
        "controller_ip": None if ctrl in (None, "", "0.0.0.0") else ctrl,
        "slots": slots,
    }
    return cam, sectors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path, nargs="+", help="Jetson 카메라 설정 파일 또는 그 폴더")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base", type=Path, help="이 설정에 카메라를 더한다 (같은 IP 는 바꿈)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="카메라에 붙일 프로필 이름")
    args = ap.parse_args()

    files = []
    for s in args.src:
        files += sorted(p for p in s.iterdir() if p.is_file()) if s.is_dir() else [s]

    # 기존 설정은 먼저 현재 버전으로 (버전 1 이면 자동 변환)
    base = json.loads(args.base.read_text(encoding="utf-8")) if args.base else {}
    cfg = AppConfig.model_validate(base).model_dump(mode="json")
    if args.profile not in cfg["camera_profiles"]:
        prof = CameraProfile(snapshot_url=IDIS_SNAPSHOT_URL, lenses=2)
        cfg["camera_profiles"][args.profile] = prof.model_dump(mode="json")
    cams = {c["ip"]: c for c in cfg.get("cameras", [])}
    sectors: Counter = Counter()
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cam, sec = convert(data, args.profile)
        except (ValueError, KeyError) as e:
            print(f"{f.name}: Jetson 설정이 아님 ({e})")
            continue
        cams[cam["ip"]] = cam
        sectors += sec
    cfg["cameras"] = list(cams.values())
    AppConfig.model_validate(cfg)  # 형식 확인
    args.out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    n_slots = sum(len(c["slots"]) for c in cfg["cameras"])
    print(f"카메라 {len(cfg['cameras'])}대, 칸 {n_slots}개 → {args.out}")
    print(f"parking_sector 값별 칸 수: {dict(sectors)}")
    unknown = {k: v for k, v in sectors.items() if k not in SECTOR_TYPES}
    if unknown:
        print(f"  parkai 에 없는 종류라 일반으로 둔 칸: {unknown} (3 = 교통약자)")


if __name__ == "__main__":
    main()
