"""보드 부하 시험: 재생 사진으로 카메라 N대를 쉬지 않고 돌리며 사이클 시간·CPU·메모리·온도를 기록한다.

    systemctl stop parkai-worker              # 같은 GPU/NPU 를 쓰므로 먼저 멈춘다
    cd /opt/parkai/current
    ./venv/bin/python tools/load_test.py --config /tmp/load/config.json --replay /tmp/load/samples \\
        --models-dir /var/lib/parkai/models --minutes 60
    systemctl start parkai-worker

- 워커 코드(parkai.worker.pipeline.Worker)를 그대로 쓴다. 사진만 카메라 대신 재생 폴더에서 읽는다
  (<폴더>/<카메라IP>/ch<렌즈>/*.jpg). 그래서 카메라 응답 시간은 들어가지 않는다
- 사이클 주기(cycle_target_sec)를 무시하고 쉬지 않고 돌린다 → 사이클 시간 = 카메라당 갱신 간격
- 기록 파일과 최신 이미지는 --work(기본 /tmp/parkai_load) 아래에 쓴다 (설치된 서비스 폴더와 분리)
- 1분마다 한 줄 요약, 끝나면 전체 요약과 CSV(<work>/load.csv)
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parkai.backends import load_detector  # noqa: E402
from parkai.core.config import load_config  # noqa: E402
from parkai.worker.pipeline import Worker  # noqa: E402


def cpu_times() -> tuple[int, int]:
    """(전체, 쉰 시간) /proc/stat 첫 줄."""
    v = [int(x) for x in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
    return sum(v), v[3] + v[4]


def max_temp() -> float | None:
    temps = []
    for p in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            temps.append(int(p.read_text()) / 1000)
        except (OSError, ValueError):
            pass
    return max(temps) if temps else None


def rss_mb() -> float:
    for line in Path(f"/proc/{os.getpid()}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def mem_avail_mb() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--replay", type=Path, required=True)
    ap.add_argument("--models-dir", type=Path, default=Path("/var/lib/parkai/models"))
    ap.add_argument("--backend", default="auto")
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--work", type=Path, default=Path("/tmp/parkai_load"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    model = cfg.detection.model
    detector = load_detector(args.backend, args.models_dir / model if model else None)
    (args.work / "run").mkdir(parents=True, exist_ok=True)
    worker = Worker(args.config, detector, args.work / "run", args.work / "data", args.replay)
    cams = worker.cfg.cameras_for_board()
    n_img = sum(worker.cfg.camera_lenses(c) for c in cams)
    print(f"카메라 {len(cams)}대, 사진 {n_img}장/사이클, 모델 {model} ({detector.name}), {args.minutes:g}분")

    rows: list[dict] = []
    end = time.monotonic() + args.minutes * 60
    c0, i0 = cpu_times()
    last_print = time.monotonic()
    n = 0
    try:
        while time.monotonic() < end:
            n += 1
            st = worker.run_cycle(n)
            c1, i1 = cpu_times()
            cpu = 100 * (1 - (i1 - i0) / max(c1 - c0, 1))
            c0, i0 = c1, i1
            stages: dict[str, float] = {}
            for c in st["cameras"].values():
                for k, v in (c.get("timings") or {}).items():
                    stages[k] = stages.get(k, 0.0) + v
            bad = sum(1 for c in st["cameras"].values() if c.get("status") != "ok")
            rows.append(
                {
                    "t": round(time.time(), 1),
                    "cycle": n,
                    "cycle_sec": st["cycle_sec"],
                    "cpu_pct": round(cpu, 1),
                    "temp_c": max_temp(),
                    "rss_mb": round(rss_mb(), 1),
                    "avail_mb": round(mem_avail_mb(), 1),
                    "bad_cams": bad,
                    **{f"{k}_sec": round(v, 3) for k, v in stages.items()},
                }
            )
            if time.monotonic() - last_print >= 60 or n == 1:
                last_print = time.monotonic()
                recent = rows[-20:]
                r = rows[-1]
                print(
                    f"[{time.strftime('%H:%M:%S')}] 사이클 {n}: 최근 평균 "
                    f"{np.mean([x['cycle_sec'] for x in recent]):.2f}s, CPU {r['cpu_pct']}%, "
                    f"온도 {r['temp_c']}°C, 메모리 {r['rss_mb']}MB (남은 {r['avail_mb']}MB), "
                    f"이상 카메라 {bad}"
                )
    except KeyboardInterrupt:
        print("중단")
    finally:
        worker.stop()

    if not rows:
        return
    out = args.work / "load.csv"
    keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    cyc = np.array([r["cycle_sec"] for r in rows[1:] or rows])
    temps = [r["temp_c"] for r in rows if r["temp_c"] is not None]
    print()
    print(f"== 요약: 카메라 {len(cams)}대, 사진 {n_img}장, 사이클 {len(rows)}회")
    print(
        f"사이클(= 카메라당 갱신 간격): 평균 {cyc.mean():.2f}s, 중앙 {np.median(cyc):.2f}s, "
        f"95% {np.percentile(cyc, 95):.2f}s, 최대 {cyc.max():.2f}s"
    )
    print(f"사진 1장당: {cyc.mean() / max(n_img, 1) * 1000:.0f}ms")
    cpus = [r["cpu_pct"] for r in rows]
    print(f"CPU: 평균 {np.mean(cpus):.0f}%, 최대 {max(cpus):.0f}%")
    if temps:
        print(f"온도: 시작 {temps[0]:.1f}°C, 끝 {temps[-1]:.1f}°C, 최대 {max(temps):.1f}°C")
    print(
        f"메모리: 프로그램 최대 {max(r['rss_mb'] for r in rows):.0f}MB, 남은 메모리 최소 "
        f"{min(r['avail_mb'] for r in rows):.0f}MB"
    )
    stage_keys = [k for k in rows[-1] if k.endswith("_sec") and k != "cycle_sec"]
    print(
        "단계 합계(사이클당 평균, 카메라 전체): "
        + ", ".join(f"{k[:-4]} {np.mean([r.get(k, 0) for r in rows]):.2f}s" for k in stage_keys)
    )
    print(f"이상 카메라가 있던 사이클: {sum(1 for r in rows if r['bad_cams'])}회")
    print(f"CSV: {out}")


if __name__ == "__main__":
    main()
