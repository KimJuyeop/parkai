# parkai

STM32MP257F(NPU) 보드에서 IP카메라 스냅샷으로 주차면 차량 유무를 판단하고,
서버 전송과 만공등 제어를 하는 엣지 프로그램.

- 카메라 스냅샷(HTTP) → 화면 분할 → NPU 차량 검출 → 칸별 선분 판정 → 서버 전송 / 만공등
- 보드 안의 웹 설정 툴(포트 80)에서 카메라, 칸 선분, 서버, 모델을 설정
- 인터넷 없는 현장을 위해 오프라인 번들 하나로 설치·업데이트

설계는 [docs/design.md](docs/design.md), 서버 전송 규격은 [docs/protocol.md](docs/protocol.md),
고정 버전은 [VERSIONS.md](VERSIONS.md) 참고.

## 구조

```
parkai/
  core/        설정, 좌표 계산, 판정, 안정화, 화면 검사
  worker/      수신 → 추론 → 판정 → 출력 파이프라인
  backends/    stai (보드 NPU), onnx (PC), fixture (모델 없이 개발)
  postprocess/ 모델 구조별 후처리 (yolox ...)
  outputs/     서버 전송, 만공등 제어
  web/         FastAPI (API + 웹 툴 정적 파일)
frontend/      웹 설정 툴 (React + Vite, 빌드 결과만 번들에 포함)
packaging/     번들 빌드, install.sh, systemd, 보드 프로필
tools/         판정 규칙 비교, 벤치마크 등
tests/
```

## PC 개발 환경

Python 3.12 기준.

```sh
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[pc,dev]"
pytest
```

## 실행 (PC, 재생 모드)

현장 스냅샷을 `samples/<카메라IP>/*.jpg`에 넣고 실행한다.
모델이 없을 때는 `--backend fixture`로, 이미지 옆 `*.json`의 박스를 검출 결과로 사용한다.

```sh
# 워커
python -m parkai.worker --config examples/config.example.json \
    --replay samples --backend fixture --run-dir run --data-dir data --cycles 3

# 웹 (다른 터미널)
PARKAI_CONFIG=examples/config.example.json PARKAI_RUN_DIR=run python -m parkai.web --port 8080
# http://localhost:8080/api/v1/status
```

fixture 박스 형식 (`samples/192.168.13.21/0001.json`, 원본 스냅샷 좌표):

```json
{"boxes": [[x1, y1, x2, y2, score], ...]}
```

## 판정 프리셋

| 프리셋 | 판정 | 안정화 | 용도 |
|---|---|---|---|
| `legacy` | 선분이 박스에 닿으면 점유 | 매 사이클 그대로 (N=1) | 기본값, 기존 Jetson과 동일 조건 비교 |
| `standard` | 덮임 비율 + 옆 칸 배정 규칙 | 연속 2회 일치 | 검증 후 전환 후보 |
