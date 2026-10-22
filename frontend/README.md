# frontend — 웹 화면 (React + TypeScript + Vite)

보드 안 웹 설정 툴의 화면. `npm run build` 결과는 `../parkai/web/static/`으로 나가고 FastAPI가 그대로 서빙한다.
보드에는 빌드 결과만 들어간다 (Node 불필요). 설치 번들(`packaging/build_bundle.sh`)이 빌드까지 한다.

```sh
npm install
npm run dev        # http://localhost:5173  (python tools/dev.py 를 함께 띄우면 /api 가 8080 으로 프록시)
npm run build      # 타입 검사 + 빌드 → ../parkai/web/static
```

## 구조

```
src/
  api/         client.ts (API 호출), types.ts (config.py 와 같은 형태 — 백엔드 스키마가 바뀌면 여기부터)
  state/       AppState.tsx — 설정(저장 전 수정본), 워커 상태 3초 폴링, 시스템 정보 5초 폴링, 저장/되돌리기, 토스트
  lib/         domain.ts — 주차 종류·만공등 색·판정 프리셋, 분석 영역 계산, IP 범위, 판정 여부 규칙
  styles/      tokens.css (색·글꼴·간격 — 모든 값은 여기서), base.css (공통 컨트롤), layout.css (화면 배치)
  components/
    CameraMedia     영상 + SVG 칸 선분 (보기 / 편집: 선 추가·끝점 끌기·선택·삭제)
    LineEditor      도구 줄 + CameraMedia — 모니터링 큰 창과 카메라 설정이 같이 씀
    useCamera       영상 주소(최신 이미지/스냅샷), 칸 편집 동작 (useSlotEditing)
    CameraCard      모니터링 카드
    CameraDialog    모니터링 큰 창 (보기 ↔ 선 편집)
    StatusStrip     상태 줄: 판정 · CCTV · 사이클 · CPU · 메모리 · 서버 전송
    AppHeader, ui   맨 위 줄, Field/TextInput/Check/SlotChip/TypePicker/Dialog …
  settings/    sections.tsx — 기본 정보·서버 전송·판정 방식·만공등 색·카메라 프로필·설정 파일
               (시스템 설정 화면과 모니터링 빠른 설정 패널이 같이 씀)
  pages/       MonitorPage, CameraPage, SettingsPage
```

## 규칙

- 색·글꼴 크기·간격은 `tokens.css` 변수만 쓴다. 글꼴 크기: 제목 18 / 섹션 15 / 본문 14 / 버튼 13 / 라벨 12px, 컨트롤 높이 36px.
- 현장은 인터넷이 없을 수 있어 웹 글꼴·CDN을 쓰지 않는다 (시스템 글꼴).
- 설정 수정은 `edit(draft => …, "저장 바에 보일 설명")` 으로만. 저장 전까지 서버에 보내지 않는다.
- 칸 번호는 서버 전송 `ps01~ps12` 와 맞물리므로 삭제해도 다른 칸 번호를 당기지 않는다 (새 칸은 비어 있는 가장 작은 번호).
- 판정 결과 색: 차량 있음 = 주황 채움/실선, 빈칸 = 초록 테두리/점선, 판정 없음 = 회색 점선.
  주차 종류 색(편집 중 선): 일반 초록, 경차 보라, 장애인 파랑, 전기차 하늘.
