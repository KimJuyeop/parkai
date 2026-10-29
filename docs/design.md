# parkai 설계

진행하면서 계속 보정한다. 결정이 바뀌면 이 문서를 먼저 고친다.

## 0. 목표

- STM32MP257F 보드 한 대가 IP카메라 여러 대의 스냅샷으로 주차면 차량 유무를 판단한다.
- 판단 결과를 서버로 보내고, 카메라 만공등을 제어한다.
- 기존 Jetson 시스템(YOLOv4 + 칸별 선분)과 같은 방식에서 출발해, 모델과 운영 방식을 개선한다.
- 목표 처리량: **보드당 카메라 30대, 사이클 10초 이내** (벤치마크로 최대 대수 확정)

## 1. 개발 환경과 버전

| 항목 | 결정 |
|---|---|
| 보드 OS | Starter package (OpenSTLinux 6.6) + X-LINUX-AI (apt) |
| 크로스컴파일 SDK | 사용 안 함 (Python). C++ 전환 시에만 |
| Yocto 빌드 | 양산 골든 이미지 단계에서 |
| 모델 | ST st_yoloxn 을 현장 사진으로 추가 학습 (라벨은 기존 YOLOv4 자동). [training.md](training.md) |
| 모델 변환 | ST Edge AI Core → NBG (`.nb`) |
| 보드 추론 | X-LINUX-AI `stai_mpu` Python API |
| 언어 | Python 3.12 (보드와 동일) |
| 에디터 | VS Code (+ 보드 배포 task) |

버전은 [VERSIONS.md](../VERSIONS.md)에 고정한다.

## 2. 시스템 구성

```
보드
├ parkai-web     FastAPI :80  웹 설정 툴, 설정 API, 상태 조회
├ parkai-worker  추론 워커    수신 → 분할 → NPU 추론 → 판정 → 안정화 → 출력
├ 설정/상태       SQLite (1차 골격은 JSON 파일)
├ /run/parkai     최신 결과 이미지, status.json (RAM, eMMC 쓰기 없음)
└ /var/lib/parkai 설정, 기록 이미지(용량 상한), 모델
```

- 웹과 워커는 별도 systemd 서비스. 한쪽이 죽어도 다른 쪽은 동작.
- 워커는 systemd watchdog으로 감시.
- 즉시 응답이 필요한 명령(테스트 판정 등)은 워커의 내부 유닉스 소켓으로 전달 (예정).
- 웹 포트 80은 `CAP_NET_BIND_SERVICE`로 열고 root로 실행하지 않는다.

### 하드웨어 (STM32MP257F-EV1)

| 항목 | 영향 |
|---|---|
| Cortex-A35 ×2 | CPU가 약함 → JPEG 디코딩/이미지 저장 최소화 |
| NPU 1.35 TOPS | 추론은 여유 |
| DDR4 4GB | 여유 |
| eMMC 4GB | 빠듯함 → 기록 이미지 상한, 쓰기 최소화 |
| 이더넷 | 1포트 기준 설계 |
| User LED/버튼 | 상태 표시, 네트워크 초기화 (보드 프로필) |

양산 보드는 칩이 같고 보드만 다르다. LED/버튼/NIC/저장공간 차이는 `packaging/board_profiles/`로 흡수한다.

## 3. 설정 구조

`parkai/core/config.py` 참고. 예시: `examples/config.example.json`

- **보드**: device_id(자동, 불변), 현장명·보드명(표시용), 보드 IP
- **카메라**: IP, 포트, 기종 프로필, 인증, 담당 보드명
- **카메라 → 렌즈 → 분석 영역** (설정 버전 2)
  - 렌즈: 카메라 하나에 1~4개. 렌즈마다 사진을 따로 받는다 (스냅샷 주소의 `{channel}` = 렌즈 번호 1부터).
    현장 카메라는 렌즈 1개 또는 2개.
  - 분석 영역(views): 렌즈 사진 안의 영역 `[x, y, w, h]`, 렌즈 사진 대비 비율(0~1). 기본은 사진 전체 하나.
    사진 한 장에 두 화면이 합쳐져 오는 카메라는 렌즈 1개 + 분석 영역 2개로 쓴다.
  - 좌표를 비율로 저장하므로 카메라 해상도(640×360, 1280×720, 1920×1080 …)를 바꿔도 선분이 그대로 맞는다.
- **칸**: 카메라당 최대 12개 (ps01~ps12, 렌즈와 상관없이 카메라 안에서 하나로 이어짐),
  렌즈 번호 + 선분 2점(그 렌즈 사진 대비 비율), 주차 종류, 칸별 판정 예외값
- **주차 종류**: 일반/경차/장애인/전기차 고정 + 만공등 색
- **카메라 프로필**: 스냅샷 URL, 인증 방식, 렌즈 수, 분석 영역
- **설정 버전 1 → 2 자동 변환**: 기준 해상도(ref_size) 픽셀 좌표를 비율로 바꾸고 렌즈 1개로 둔다
- **현장 파일**: 카메라 전체를 파일 하나로 관리하고, 각 보드는 `board`가 자기 보드명인 카메라만 처리

## 4. 추론 파이프라인과 판정

```
수신+디코딩+화면검사 (스레드 풀)  →  NPU 추론 (순차)  →  판정  →  안정화  →  출력
```

- **수신**: 카메라마다 렌즈 사진을 따로 받는다. 받은 원본을 그대로 최신 이미지로 둔다 (다시 인코딩하지 않음).
- **화면 분할**: 렌즈 사진을 분석 영역별로 잘라 각각 추론하고, 박스는 그 렌즈 사진 좌표로 되돌린다.
  판정은 렌즈별로 (그 렌즈의 칸과 그 렌즈의 박스만) 하고, 결과는 카메라 단위로 합친다.
- **학습과 판정의 화면이 같아야 한다**: 학습 사진도 렌즈 원본을 같은 분석 영역으로 잘라 만든다.
  (이전 Jetson 은 렌즈 두 장을 640×480 으로 줄여 1280×960 한 장으로 합쳐 썼다. 이 합친 사진은 원본보다 흐리고 비율이 바뀐다)
- **화면 이상** (검은 화면, 흐림, 정지): 해당 화면의 칸은 판정하지 않고 마지막 상태 유지. 모든 화면이 이상이면 전송하지 않음.
- **판정 프리셋**
  - `legacy`: 선분이 박스에 닿으면 점유, 매 사이클 그대로 (기존 Jetson과 동일) ← 기본값
  - `standard`: 덮임 비율(0.6) + 한 박스가 여러 칸에 걸치면 가장 잘 맞는 칸에 배정, 연속 2회 일치
- **모델**: ST st_yoloxn 을 현장 사진으로 추가 학습. 보드 NPU 용은 TFLite per-tensor 로 변환 ([training.md](training.md))
- **출력**: 매 사이클 서버 전송, 최신 이미지는 RAM, 기록 이미지는 상태 변경 시 + 5분마다.

**보정 필요 (현장 데이터로)**: 화면 이상 기준값, 신뢰도 임계값, 판정 기준, N.

## 5. 웹 설정 툴

PC(노트북) 화면 기준, 화면 시안을 보면서 수정해 나간다.

| 화면 | 내용 |
|---|---|
| 대시보드 | 보드 정보, 사이클 시간, 카메라 상태, 최신 결과 이미지 |
| 카메라 설정 | 스냅샷 + 선분 그리기/수정 + 주차 종류 선택, 칸 목록, 테스트 판정, 만공등 테스트 |
| 카메라 일괄 관리 | IP 범위 추가, 현장 파일 가져오기/내보내기 |
| 판정·모델 | 프리셋, 검출 객체/신뢰도, N, 모델 업로드·교체 |
| 네트워크·서버 | 보드 IP(적용 후 확인 방식), 서버 주소, 전송 테스트 |
| 시스템 | 버전, 업데이트, 로그, 처리 시간, 설정 백업/복원, 결과 이미지 |

API는 `/api/v1` 아래 REST. 화면은 React + TypeScript(`frontend/`)이고, PC에서 빌드한 결과만
`parkai/web/static/`에 넣어 FastAPI가 서빙한다 (보드에 Node 불필요). 구성은 [frontend/README.md](../frontend/README.md).

- 워커의 최신 이미지(`/run/parkai/latest`)는 선을 그리지 않은 원본이고, 화면이 칸 선분·검출 박스(`status.json`의 `dets`)를 직접 그린다.
  선·박스를 그린 이미지는 기록 이미지(`results/`)에만 저장한다.
- `/api/v1/system`의 `resources`: CPU·메모리·온도·저장공간 (모니터링 상태 줄)

## 6. 서버 전송과 만공등

- 서버: [protocol.md](protocol.md)
- 만공등: 카메라마다 하나 (렌즈가 2개여도 하나). 설정된 칸 중 빈칸이 있으면 빈칸 색, 모두 차면 빨강. 주차 종류별 색 지정.
  판정할 수 없을 때는 명령을 보내지 않아 마지막 상태 유지.
- IDIS 카메라 Web API (v1.6, `/cgi-bin/webSetup.cgi`, 카메라 계정 HTTP 인증)
  - 스냅샷: `action=videoStreamSnapshot&mode=1&streamIndex=N&channel=K`.
    streamIndex 1 은 동영상 전용(스냅샷 안 됨, returnCode=301), 2 는 해상도를 바꿀 수 있는 스트림, 3 은 고화질(1920×1080).
    기종마다 다르므로 프로필 주소에 적는다 (기본 2)
  - 만공등: `action=ledControl&mode=0&type=internal&color=0xRRGGBB`. 성공은 응답 `returnCode=0`.
    `type=external` 은 외부 등이 연결된 경우만 (없으면 returnCode=9999). 색이 바뀔 때 + 주기적으로 다시 보낸다

## 7. 패키징과 배포

- 오프라인 번들 하나: 앱 + Python wheel(cp312, aarch64) + 모델 + systemd + `install.sh`
- 사무실: 사내 서버에서 한 줄 설치 / 현장: USB·scp 또는 웹 툴 업로드
- `/opt/parkai/<버전>` + `current` 링크로 업데이트와 롤백
- 설정은 업데이트해도 유지 (`/var/lib/parkai`)
- 보안: root 비밀번호, 서비스 전용 계정 `parkai`, SSH 제한
- 대량 출고는 골든 이미지

## 8. 처리량 측정

- 워커가 카메라별 단계 시간(수신/디코딩/검사/추론/판정/출력)을 기록
- 재생 모드로 카메라 1/5/10/20/30대 부하 테스트, 1시간 이상 (온도 포함)
- 기준: 사이클 ≤ 목표, CPU ≤ 70%, 온도 여유 → 최대 대수 × 0.7
- 최종 대수는 양산 보드에서 다시 측정

## 미정 사항

- 컨트롤러 IP(Jetson 설정의 controller_ip_address)의 역할
- 교통약자 주차 종류 (Jetson parking_sector 3) 추가 여부
- 렌즈 사진을 모델에 넣는 방식 (통째 / 정사각형 조각): 학습 후 비교해서 결정
- X-LINUX-AI / ST Edge AI Core 정확한 버전
- X-LINUX-AI 6.2용 apt 저장소 주소 (아래 '보드 준비' 참고)
- 사내 배포 서버

## 보드 준비 (평가보드에서 확인한 것)

OpenSTLinux 6.6 (scarthgap, `mpu-v26.06.10`), 저장소 `packages.openstlinux.st.com/6.2.1`, Python 3.12.12.

- 기본 이미지에는 OpenCV·pip·Python 표준 모듈 일부가 없다. 아래로 설치:
  `apt-get install python3-opencv python3-pip python3-requests python3-pydantic python3-modules`
  - `python3-modules`가 없으면 pydantic이 `zoneinfo`를 못 찾는다 (Yocto는 표준 모듈을 패키지별로 쪼갬).
  - FastAPI·uvicorn은 저장소에 없어 pip로 설치 (`--break-system-packages` 필요할 수 있음).
- NPU 드라이버(`galcore`, `/dev/galcore`)는 기본으로 올라와 있다. OpenVX·`stai_mpu`는 X-LINUX-AI 설치가 필요.
- X-LINUX-AI 저장소 설정이 이미지에 없다. `extra.packages.openstlinux.st.com/AI/6.0`은 있으나
  6.0.0 데모 패키지뿐이고 `stai-mpu-ovx`·`python3-stai-mpu`가 없어 설치되지 않는다. 6.2용 주소는 ST 위키에서 확인 필요.
- 보드 시계는 UTC. 화면과 주고받는 시각은 항상 시간대를 붙인다.
- 카메라 1대 기준 사이클(수신·판정·기록, 검출 제외) 약 0.1초, CPU 3%.
