"""설정 스키마.

설정의 원본은 SQLite(추후)이며, 내보내기/가져오기와 개발 단계에서는 JSON 파일을 쓴다.
구조는 docs/design.md 3단계 참고.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = 2  # 2: 렌즈(lenses), 좌표를 렌즈 사진 대비 비율로
MAX_SLOTS_PER_CAMERA = 12  # 서버 전송 ps01~ps12
MAX_LENSES = 4

Point = tuple[float, float]  # 렌즈 사진 대비 비율 (0~1)
Rect = tuple[float, float, float, float]  # x, y, w, h (렌즈 사진 대비 비율)


class SiteInfo(BaseModel):
    name: str = ""  # 현장명 (표시용)
    board_name: str = ""  # 보드명 (표시용, 카메라 배정 기준)


class NetworkCfg(BaseModel):
    interface: str | None = None  # 보드 IP를 읽을 인터페이스. None이면 자동
    board_ip: str | None = None  # 지정하면 전송 시 이 값을 사용


class ResultsCfg(BaseModel):
    max_mb: int = 300  # 기록 이미지 저장 상한
    save_interval_sec: int = 300  # 상태 변화가 없어도 이 주기마다 1장 저장


class RuntimeCfg(BaseModel):
    cycle_target_sec: float = 10.0
    fetch_concurrency: int = 8
    fetch_timeout_sec: float = 3.0
    fetch_retries: int = 1
    results: ResultsCfg = ResultsCfg()


class ClassCfg(BaseModel):
    enabled: bool = True
    conf: float = 0.45


class JudgeCfg(BaseModel):
    # intersect: 선분이 박스에 닿으면 점유 (기존 Jetson 방식)
    # cover_ratio: 선분이 박스에 덮인 비율 + 옆 칸 배정 규칙
    mode: Literal["intersect", "cover_ratio"] = "intersect"
    cover_ratio: float = 0.6
    cover_ratio_shared: float = 0.9  # 한 박스가 여러 칸에 걸칠 때 추가 칸 인정 기준


class StabilizeCfg(BaseModel):
    count: int = Field(1, ge=1)  # 연속 N회 일치 시 상태 변경. 1 = 매 사이클 그대로


class ImageCheckCfg(BaseModel):
    black_mean: float = 8.0  # 평균 밝기가 이보다 낮으면 검은 화면
    blur_var: float = 10.0  # 라플라시안 분산이 이보다 낮으면 흐림
    frozen_cycles: int = 6  # 이 사이클 수만큼 이미지가 완전히 같으면 정지


PRESETS: dict[str, tuple[JudgeCfg, StabilizeCfg]] = {
    "legacy": (JudgeCfg(mode="intersect"), StabilizeCfg(count=1)),
    "standard": (JudgeCfg(mode="cover_ratio"), StabilizeCfg(count=2)),
}


class DetectionCfg(BaseModel):
    preset: Literal["legacy", "standard", "custom"] = "legacy"
    model: str | None = None  # models/ 아래 모델 패키지 이름
    classes: dict[str, ClassCfg] = {"car": ClassCfg()}
    nms_iou: float = 0.45
    judge: JudgeCfg = JudgeCfg()
    stabilize: StabilizeCfg = StabilizeCfg()
    image_check: ImageCheckCfg = ImageCheckCfg()

    def effective(self) -> tuple[JudgeCfg, StabilizeCfg]:
        """프리셋을 반영한 실제 판정/안정화 설정."""
        if self.preset == "custom":
            return self.judge, self.stabilize
        return PRESETS[self.preset]


FULL_COLOR = "red"  # 모두 차면 만공등은 항상 빨간색

# 만공등 색 선택지 (값: 표시 이름)
INDICATOR_COLORS = {
    "green": "녹색",
    "blue": "파란색",
    "yellow": "노란색",
    "white": "흰색",
    "purple": "보라색",
    "cyan": "하늘색",
}
# 카메라로 보내는 실제 LED 색 (IDIS ledControl color=0xRRGGBB)
LED_RGB = {
    "red": 0xFF0000,
    "green": 0x00FF00,
    "blue": 0x0000FF,
    "yellow": 0xFFFF00,
    "white": 0xFFFFFF,
    "purple": 0x8000FF,
    "cyan": 0x00FFFF,
}


class SlotType(BaseModel):
    id: str
    name: str
    color_available: str = "green"  # 이 종류의 빈칸이 있을 때 만공등 색


# 주차 종류는 고정 (순서도 이대로 표시). 바꿀 수 있는 것은 색뿐이다.
FIXED_SLOT_TYPES = [("normal", "일반"), ("compact", "경차"), ("disabled", "장애인"), ("ev", "전기차")]
# 빈칸일 때 만공등 기본 색 (현장 관례: 일반 녹색, 경차 보라, 장애인 파랑, 전기차 하늘색)
DEFAULT_SLOT_COLORS = {"normal": "green", "compact": "purple", "disabled": "blue", "ev": "cyan"}
DEFAULT_SLOT_TYPES = [
    SlotType(id=i, name=n, color_available=DEFAULT_SLOT_COLORS[i]) for i, n in FIXED_SLOT_TYPES
]


# IDIS 카메라 스냅샷 (Web API v1.6). streamIndex 1 은 동영상 전용이라 스냅샷이 안 된다
IDIS_SNAPSHOT_URL = "http://{ip}:{port}/cgi-bin/webSetup.cgi?action=videoStreamSnapshot&mode=1&streamIndex=2&channel={channel}"


class CameraProfile(BaseModel):
    snapshot_url: str  # {ip}, {port}, {channel}(렌즈 번호, 1부터) 치환
    auth: Literal["none", "basic", "digest"] = "digest"
    user: str = ""  # 이 프로필을 쓰는 카메라 공통 계정
    password: str = ""
    lenses: int = Field(1, ge=1, le=MAX_LENSES)  # 렌즈(영상 채널) 수. 렌즈마다 사진을 따로 받는다
    # 추론할 화면 영역 [x, y, w, h] (렌즈 사진 대비 비율). 모든 렌즈에 같게 적용
    views: list[Rect] = [(0.0, 0.0, 1.0, 1.0)]

    @field_validator("views")
    @classmethod
    def _views_in_range(cls, v: list[Rect]) -> list[Rect]:
        if not v:
            raise ValueError("분석 영역이 하나 이상 있어야 합니다")
        for x, y, w, h in v:
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 1.0001 or y + h > 1.0001:
                raise ValueError(f"분석 영역은 사진 안의 비율(0~1)이어야 합니다: {[x, y, w, h]}")
        return v


class JudgeOverride(BaseModel):
    cover_ratio: float | None = None


class Slot(BaseModel):
    no: int = Field(ge=1, le=MAX_SLOTS_PER_CAMERA)
    type: str = "normal"
    lens: int = Field(0, ge=0, lt=MAX_LENSES)  # 렌즈 번호 (0부터)
    line: tuple[Point, Point]  # 렌즈 사진 대비 비율 (0~1)
    name: str = ""  # 선택 메모
    judge: JudgeOverride | None = None

    @field_validator("line")
    @classmethod
    def _line_in_range(cls, v: tuple[Point, Point]) -> tuple[Point, Point]:
        if any(not -0.001 <= c <= 1.001 for p in v for c in p):
            raise ValueError("선분 좌표는 렌즈 사진 대비 비율(0~1)이어야 합니다")
        return v


class Camera(BaseModel):
    ip: str
    port: int = 80
    profile: str
    own_account: bool = False  # True면 아래 계정 사용, False면 프로필 공통 계정
    user: str = ""
    password: str = ""
    controller_ip: str | None = None  # 용도 확인 필요 (Jetson 설정에서 옮겨 온 값)
    board: str | None = None  # 담당 보드명. None이면 어느 보드든 처리
    enabled: bool = True
    slots: list[Slot] = []

    @field_validator("slots")
    @classmethod
    def _unique_slot_no(cls, v: list[Slot]) -> list[Slot]:
        nos = [s.no for s in v]
        if len(nos) != len(set(nos)):
            raise ValueError("칸 번호가 중복되었습니다")
        if len(v) > MAX_SLOTS_PER_CAMERA:
            raise ValueError(f"카메라당 최대 {MAX_SLOTS_PER_CAMERA}칸까지 설정할 수 있습니다")
        return sorted(v, key=lambda s: s.no)


class ServerCfg(BaseModel):
    enabled: bool = False
    base_url: str = ""  # 예: http://192.168.0.197:8000
    path: str = "/api/camerastatuses"
    timeout_sec: float = 2.0

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + self.path


class IndicatorCfg(BaseModel):
    enabled: bool = False
    protocol: Literal["idis"] = "idis"  # IDIS 카메라 Web API ledControl
    led_type: Literal["internal", "external"] = "internal"  # 카메라 내장 LED / 카메라에 연결한 외부 등
    resend_sec: float = 60.0  # 색이 같아도 이 주기마다 다시 보낸다 (카메라 재부팅 대비)


class AppConfig(BaseModel):
    schema_version: int = SCHEMA_VERSION
    site: SiteInfo = SiteInfo()
    network: NetworkCfg = NetworkCfg()
    runtime: RuntimeCfg = RuntimeCfg()
    detection: DetectionCfg = DetectionCfg()
    slot_types: list[SlotType] = DEFAULT_SLOT_TYPES

    @field_validator("slot_types", mode="before")
    @classmethod
    def _fixed_slot_types(cls, v) -> list[SlotType]:
        """종류와 이름은 고정, 입력에서는 색만 가져온다 (예전 설정 파일도 자동 정리)."""
        colors = {}
        for t in v or []:
            d = t.model_dump() if isinstance(t, SlotType) else dict(t)
            if d.get("color_available") in INDICATOR_COLORS:
                colors[d.get("id")] = d["color_available"]
        return [
            SlotType(id=i, name=n, color_available=colors.get(i, DEFAULT_SLOT_COLORS[i]))
            for i, n in FIXED_SLOT_TYPES
        ]

    camera_profiles: dict[str, CameraProfile] = {}
    cameras: list[Camera] = []
    server: ServerCfg = ServerCfg()
    indicator: IndicatorCfg = IndicatorCfg()

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data):
        """예전 설정 파일 자동 변환.
        - 카메라마다 비밀번호가 있었으면 개별 계정으로 유지
        - 버전 1: 기준 해상도(ref_size) 픽셀 좌표 → 렌즈 사진 대비 비율, 렌즈 1개
        """
        if not isinstance(data, dict):
            return data
        for cam in data.get("cameras") or []:
            if isinstance(cam, dict) and "own_account" not in cam and cam.get("password"):
                cam["own_account"] = True
        if int(data.get("schema_version") or 1) < 2:
            _migrate_v1(data)
        data["schema_version"] = SCHEMA_VERSION
        return data

    @model_validator(mode="after")
    def _check_refs(self) -> AppConfig:
        type_ids = {t.id for t in self.slot_types}
        seen_ips: set[str] = set()
        for cam in self.cameras:
            if cam.profile not in self.camera_profiles:
                raise ValueError(f"카메라 {cam.ip}: 없는 프로필 '{cam.profile}'")
            if cam.ip in seen_ips:
                raise ValueError(f"카메라 IP 중복: {cam.ip}")
            seen_ips.add(cam.ip)
            lenses = self.camera_profiles[cam.profile].lenses
            for s in cam.slots:
                if s.type not in type_ids:
                    raise ValueError(f"카메라 {cam.ip} {s.no}번 칸: 없는 주차 종류 '{s.type}'")
                if s.lens >= lenses:
                    raise ValueError(
                        f"카메라 {cam.ip} {s.no}번 칸: 렌즈 {s.lens + 1}이 없습니다 (렌즈 {lenses}개)"
                    )
        return self

    def camera_account(self, cam: Camera) -> tuple[str, str]:
        if cam.own_account:
            return cam.user, cam.password
        p = self.camera_profiles[cam.profile]
        return p.user, p.password

    def camera_lenses(self, cam: Camera) -> int:
        return self.camera_profiles[cam.profile].lenses

    def cameras_for_board(self) -> list[Camera]:
        """이 보드가 담당할 카메라. board가 비어 있으면 모두 담당."""
        me = self.site.board_name
        return [c for c in self.cameras if c.enabled and (c.board is None or not me or c.board == me)]


def _migrate_v1(data: dict) -> None:
    """설정 버전 1 (기준 해상도 픽셀 좌표, 사진 주소 하나) → 2."""
    refs: dict[str, tuple[float, float]] = {}
    for name, prof in (data.get("camera_profiles") or {}).items():
        if not isinstance(prof, dict):
            continue
        rw, rh = prof.pop("ref_size", None) or (1280, 960)
        refs[name] = (rw, rh)
        prof.setdefault("lenses", 1)
        if "views" in prof:
            prof["views"] = [[x / rw, y / rh, w / rw, h / rh] for x, y, w, h in prof["views"]]
        else:  # 예전 기본값: 1280x960 위 절반의 두 화면
            prof["views"] = [[0, 0, 0.5, 0.5], [0.5, 0, 0.5, 0.5]]
    for cam in data.get("cameras") or []:
        if not isinstance(cam, dict):
            continue
        rw, rh = cam.pop("ref_size", None) or refs.get(cam.get("profile"), (1280, 960))
        for s in cam.get("slots") or []:
            if isinstance(s, dict) and "line" in s:
                s["line"] = [[x / rw, y / rh] for x, y in s["line"]]
                s.setdefault("lens", 0)


def load_config(path: str | Path) -> AppConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


def save_config(cfg: AppConfig, path: str | Path, include_passwords: bool = True) -> None:
    data = cfg.model_dump(mode="json")
    if not include_passwords:
        for cam in data["cameras"]:
            cam["password"] = ""
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
