"""보드 부하 시험: 재생 사진으로 카메라 N대를 쉬지 않고 돌리며 사이클 시간·CPU·메모리·온도를 기록한다.

    systemctl stop parkai-worker              # 같은 GPU/NPU 를 쓰므로 먼저 멈춘다
    cd /opt/parkai/current
    ./venv/bin/python tools/load_test.py --config /tmp/load/config.json --replay /tmp/load/samples \\
        --models-dir /var/lib/parkai/models --minutes 60
    systemctl start parkai-worker

- 워커 코드(parkai.worker.pipeline.Worker)를 그대로 쓴다. 사진만 카메라 대신 재생 폴더에서 읽는다
  (<폴더>/<카메라IP>/ch<렌즈>/*.jpg). 그래서 카메라 응답 시간은 들어가지 않는다
- 기본은 쉬지 않고 돌린다 → 사이클 시간 = 최소 갱신 간격. --cycle-sec 를 주면 워커처럼 그 주기마다 돈다
  (실제 운영의 CPU·온도 확인용. CPU 는 쉬는 시간까지 포함해 잰다)
- 기록 이미지는 --work(기본 /tmp/parkai_load) 아래, 최신 이미지·상태는 --run-dir(기본 /tmp, RAM) 에 쓴다.
  운영 워커도 최신 이미지는 RAM 디스크(/run/parkai)에 둔다
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
    ap.add_argument("--work", type=Path, default=Path("/tmp/parkai_load"), help="기록 이미지·CSV")
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=Path("/tmp/parkai_load_run"),
        help="최신 이미지·status.json (운영처럼 RAM 에. 저장 장치에 두면 사이클마다 사진 60장을 씀)",
    )
    ap.add_argument(
        "--switch-interval", type=float, help="파이썬 스레드 전환 간격(초, 기본 0.005). 추론 대기 시험용"
    )
    ap.add_argument("--cycle-sec", type=float, default=0, help="사이클 주기(초). 0 이면 쉬지 않고")
    args = ap.parse_args()
    if args.switch_interval:
        sys.setswitchinterval(args.switch_interval)
    sys.stdout.reconfigure(line_buffering=True)  # nohup 으로 파일에 쓸 때도 줄마다 바로 보이게
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    model = cfg.detection.model
    detector = load_detector(args.backend, args.models_dir / model if model else None)
    args.run_dir.mkdir(parents=True, exist_ok=True)
    worker = Worker(args.config, detector, args.run_dir, args.work / "data", args.replay)
    cams = worker.cfg.cameras_for_board()
    n_img = sum(worker.cfg.camera_lenses(c) for c in cams)
    print(
        f"카메라 {len(cams)}대, 사진 {n_img}장/사이클, 모델 {model} ({detector.name}), {args.minutes:g}분, "
        f"주기 {args.cycle_sec:g}초(0=쉬지 않음), 스레드 전환 {sys.getswitchinterval() * 1000:g}ms"
    )

    # 기록은 사이클마다 CSV 에 바로 쓴다 (메모리에 쌓으면 시험 도구 자체가 시간당 약 0.8MB 씩 늘어
    # 워커의 메모리 누수와 구분이 안 된다 — 15시간 시험에서 실제로 섞였음)
    stage_keys = ["fetch", "decode", "check", "infer", "judge", "output"]
    fields = ["t", "cycle", "cycle_sec", "cpu_pct", "temp_c", "rss_mb", "avail_mb"]
    fields += ["bad_cams", "flips", "occupied"]
    fields += [f"{k}_sec" for k in stage_keys]
    out = args.work / "load.csv"
    args.work.mkdir(parents=True, exist_ok=True)
    f_csv = out.open("w", newline="", encoding="utf-8")
    writer = csv.DictWriter(f_csv, fieldnames=fields)
    writer.writeheader()

    recent: list[float] = []
    end = time.monotonic() + args.minutes * 60
    c0, i0 = cpu_times()
    last_print = time.monotonic()
    n = 0
    prev_states: dict[str, dict] = {}
    try:
        while time.monotonic() < end:
            n += 1
            started = time.monotonic()
            st = worker.run_cycle(n)
            wait = args.cycle_sec - (time.monotonic() - started)
            if wait > 0:
                time.sleep(wait)
            c1, i1 = cpu_times()
            cpu = 100 * (1 - (i1 - i0) / max(c1 - c0, 1))
            c0, i0 = c1, i1
            stages = dict.fromkeys(stage_keys, 0.0)
            for c in st["cameras"].values():
                for k, v in (c.get("timings") or {}).items():
                    stages[k] = stages.get(k, 0.0) + v
            bad = sum(1 for c in st["cameras"].values() if c.get("status") != "ok")
            # 같은 사진을 반복하므로, 안정화(연속 확인)가 끝난 뒤에는 칸 상태가 바뀌면 안 된다
            states = {ip: c.get("states") or {} for ip, c in st["cameras"].items()}
            flips = sum(
                1
                for ip, now in states.items()
                for no, v in now.items()
                if prev_states.get(ip, {}).get(no, v) != v
            )
            prev_states = states
            occupied = sum(1 for now in states.values() for v in now.values() if v)
            r = {
                "t": round(time.time(), 1),
                "cycle": n,
                "cycle_sec": st["cycle_sec"],
                "cpu_pct": round(cpu, 1),
                "temp_c": max_temp(),
                "rss_mb": round(rss_mb(), 1),
                "avail_mb": round(mem_avail_mb(), 1),
                "bad_cams": bad,
                "flips": flips,
                "occupied": occupied,
                **{f"{k}_sec": round(stages.get(k, 0.0), 3) for k in stage_keys},
            }
            writer.writerow(r)
            f_csv.flush()
            recent = (recent + [st["cycle_sec"]])[-20:]
            if time.monotonic() - last_print >= 60 or n == 1:
                last_print = time.monotonic()
                print(
                    f"[{time.strftime('%H:%M:%S')}] 사이클 {n}: 최근 평균 "
                    f"{np.mean(recent):.2f}s, CPU {r['cpu_pct']}%, "
                    f"온도 {r['temp_c']}°C, 메모리 {r['rss_mb']}MB (남은 {r['avail_mb']}MB), "
                    f"이상 카메라 {bad}"
                )
    except KeyboardInterrupt:
        print("중단")
    finally:
        worker.stop()
        f_csv.close()
    summarize(out, len(cams), n_img, args.cycle_sec, stage_keys)


def summarize(path: Path, n_cams: int, n_img: int, cycle_sec: float, stage_keys: list[str]) -> None:
    """CSV 를 다시 읽어 요약한다."""
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return

    def col(k: str) -> np.ndarray:
        return np.array([float(r[k]) for r in rows if r.get(k) not in (None, "")])

    cyc = col("cycle_sec")[1:] if len(rows) > 1 else col("cycle_sec")
    temps, rss, t = col("temp_c"), col("rss_mb"), col("t")
    print()
    print(f"== 요약: 카메라 {n_cams}대, 사진 {n_img}장, 사이클 {len(rows)}회")
    print(
        f"처리 시간: 평균 {cyc.mean():.2f}s, 중앙 {np.median(cyc):.2f}s, "
        f"95% {np.percentile(cyc, 95):.2f}s, 99% {np.percentile(cyc, 99):.2f}s, 최대 {cyc.max():.2f}s"
    )
    if cycle_sec:
        over = cyc > cycle_sec
        print(f"주기 {cycle_sec:g}초를 넘긴 사이클: {int(over.sum())}회 ({over.mean():.1%})")
    print(f"사진 1장당: {cyc.mean() / max(n_img, 1) * 1000:.0f}ms")
    cpus = col("cpu_pct")
    print(f"CPU: 평균 {cpus.mean():.0f}%, 최대 {cpus.max():.0f}%")
    if len(temps):
        print(f"온도: 시작 {temps[0]:.1f}°C, 끝 {temps[-1]:.1f}°C, 최대 {temps.max():.1f}°C")
    print(f"메모리: 프로그램 최대 {rss.max():.0f}MB, 남은 메모리 최소 {col('avail_mb').min():.0f}MB")
    hours = (t - t[0]) / 3600
    if hours[-1] >= 2:  # 첫 1시간(올라가는 구간)을 빼고 시간당 최솟값의 기울기
        hs = np.arange(1, int(hours[-1]))
        mins = [rss[(hours >= h) & (hours < h + 1)].min() for h in hs]
        slope = np.polyfit(hs, mins, 1)[0] if len(hs) > 1 else 0.0
        print(
            f"메모리 추세(2시간째부터 시간당 최솟값): {mins[0]:.0f} → {mins[-1]:.0f}MB, 시간당 {slope:+.2f}MB"
        )
    parts = ", ".join(f"{k} {col(f'{k}_sec').mean():.2f}s" for k in stage_keys)
    print(f"단계 합계(사이클당 평균, 카메라 전체): {parts}")
    print(f"이상 카메라가 있던 사이클: {int((col('bad_cams') > 0).sum())}회")
    late = rows[3:]  # 처음 몇 사이클은 안정화(연속 확인) 중
    flips = sum(int(r["flips"]) for r in late)
    occupied = sorted({int(r["occupied"]) for r in late})
    print(
        f"칸 상태가 바뀐 횟수(4번째 사이클부터, 같은 사진이라 0 이어야 함): {flips}, 차 있는 칸: {occupied}"
    )
    print(f"CSV: {path}")


if __name__ == "__main__":
    main()
