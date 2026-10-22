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
  web/         FastAPI API + 웹 화면 서빙 (static/ = frontend 빌드 결과)
frontend/      웹 화면 소스 (React + TypeScript + Vite)
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

cd frontend                        # 웹 화면 (Node 20 이상)
npm install
npm run build                      # → parkai/web/static
```

## 실행 (PC)

```sh
python tools/dev.py            # 웹(8080) + 워커, 실제 카메라에서 스냅샷
python tools/dev.py --replay   # samples/<카메라IP>/*.jpg 재생
```

- 브라우저에서 http://localhost:8080 → 모니터링 / 카메라 설정 / 시스템 설정
- 화면을 고치는 중이면 `cd frontend && npm run dev` → http://localhost:5173 (API는 8080으로 프록시, 저장하면 바로 반영)
- 설정 파일은 `data/config.json` (처음 실행 시 예시를 복사, Git에 올라가지 않음)
- 카메라에 접속할 수 없으면 `samples/<카메라IP>/`의 마지막 이미지를 설정 화면에 보여줌
- 모델이 없을 때는 fixture 검출기를 사용: 이미지 옆 `*.json`의 박스를 검출 결과로 쓰고, 없으면 검출 없음(전부 빈칸)

fixture 박스 형식 (`samples/192.168.13.21/0001.json`, 원본 스냅샷 좌표):

```json
{"boxes": [[x1, y1, x2, y2, score], ...]}
```

## 판정 프리셋

| 프리셋 | 판정 | 안정화 | 용도 |
|---|---|---|---|
| `legacy` | 선분이 박스에 닿으면 점유 | 매 사이클 그대로 (N=1) | 기본값, 기존 Jetson과 동일 조건 비교 |
| `standard` | 덮임 비율 + 옆 칸 배정 규칙 | 연속 2회 일치 | 검증 후 전환 후보 |
