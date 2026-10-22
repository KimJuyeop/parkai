# parkai — Claude Code 작업 안내

STM32MP257F(NPU) 보드에서 IP카메라 스냅샷으로 주차면 차량 유무를 판단하고, 서버 전송·만공등 제어를 하는 엣지 프로그램.
보드 안 웹 설정 툴(FastAPI + React)로 카메라, 칸 선분, 서버, 판정 방식을 설정한다.

작업 전에 읽을 것: `README.md`, `docs/design.md`(설계, 결정이 바뀌면 이 문서부터 고친다), `frontend/README.md`(화면 구조).

## 구조

- `parkai/core` 설정 스키마(`config.py`), 판정, 좌표, 화면 검사, 보드 정보(`system.py`)
- `parkai/worker` 수신 → 추론 → 판정 → 출력. `status.json`과 최신 이미지(`/run/parkai/latest`)를 남긴다
- `parkai/web` FastAPI API(`/api/v1`)와 정적 화면 서빙
- `frontend/` 웹 화면 소스 (React 18 + TypeScript + Vite). 빌드 결과는 `parkai/web/static/`으로 나간다
- `packaging/` 오프라인 설치 번들, systemd, 보드 프로필
- `tools/dev.py` PC 개발 실행기 (웹 8080 + 워커)

## 실행과 확인

```sh
pip install -e ".[pc,dev]"
cd frontend && npm install && npm run build && cd ..   # 화면 빌드 (처음 한 번, 화면 고친 뒤)
python tools/dev.py --replay                           # samples/<카메라IP>/*.jpg 재생
cd frontend && npm run dev                             # 화면 개발: http://localhost:5173 (/api 는 8080 프록시)
```

작업을 마치면 아래가 모두 통과해야 한다.

```sh
pytest
ruff check parkai tests tools && ruff format --check parkai tests tools
cd frontend && npm run build      # 타입 검사 포함
```

## 지켜야 할 것

- **보드 제약**: Cortex-A35 ×2, eMMC 4GB. 이미지 인코딩·디스크 쓰기를 늘리지 않는다. 보드에는 Node가 없다(빌드 결과만 설치).
- **현장은 인터넷이 없을 수 있다**: 웹 화면에서 CDN·웹 글꼴을 쓰지 않는다 (시스템 글꼴).
- **칸 번호는 서버 전송 `ps01~ps12`와 맞물린다**: 칸을 지워도 다른 칸 번호를 당기지 않는다. 새 칸은 비어 있는 가장 작은 번호.
- **최신 이미지는 원본**: 워커는 선을 그리지 않은 이미지를 `latest/`에 두고, 검출 박스는 `status.json`의 `dets`로 준다. 화면이 선·박스를 직접 그린다. 선을 그린 이미지는 기록 이미지(`results/`)에만.
- **설정 스키마를 바꾸면** `parkai/core/config.py`와 `frontend/src/api/types.ts`를 같이 고친다.
- **웹 화면**
  - 색·글꼴 크기·간격은 `frontend/src/styles/tokens.css` 변수만 쓴다. 글꼴 크기: 제목 18 / 섹션 15 / 본문 14 / 버튼 13 / 라벨 12px, 컨트롤 높이 36px.
  - 설정 수정은 `edit(draft => …, "저장 바 설명")`으로만 하고, 저장 전까지 서버에 보내지 않는다.
  - 선 편집기(`LineEditor`, `CameraMedia`)는 모니터링 큰 창과 카메라 설정이 함께 쓴다. 한쪽만 고치지 않는다.
  - 판정 색: 차량 있음 = 주황 채움/실선, 빈칸 = 초록 테두리/점선, 판정 없음 = 회색 점선.
  - 주차 종류 색: 일반 초록, 경차 보라, 장애인 파랑, 전기차 파스텔 블루. 만공등 기본 색도 같은 짝(녹색·보라·파랑·하늘색), 만차는 항상 빨강.
  - 모니터링에는 이 보드가 판정하는 카메라만 보인다. "일부 화면 이상" 같은 세부 판단은 화면에 띄우지 않고, 카메라 상태는 정상/응답 없음만 보인다.
- **용어**: 화면 문구는 한국어, 기존 용어를 따른다 (칸, 선분, 만공등, 주차 종류, 판정, 담당 보드, 카메라 프로필, 분석 영역).
- **Git**: 기능 단위 브랜치에서 작업하고, 커밋 메시지는 한국어로 무엇을 왜 바꿨는지 쓴다. `parkai/web/static/`(빌드 결과)은 커밋하지 않는다.
