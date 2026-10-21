"""설정 스키마.

설정의 원본은 SQLite(추후)이며, 내보내기/가져오기와 개발 단계에서는 JSON 파일을 쓴다.
구조는 docs/design.md 3단계 참고.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = 1
MAX_SLOTS_PER_CAMERA = 12  # 서버 전송 ps01~ps12

Point = tuple[float, float]


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

# 만공등 색 선택지 (값: 표시 이름). 실제 지원 색은 카메라 사양 확인 후 조정
INDICATOR_COLORS = {
    "green": "녹색",
    "blue": "파란색",
    "yellow": "노란색",
    "white": "흰색",
    "purple": "보라색",
    "cyan": "하늘색",
}


class SlotType(BaseModel):
    id: str
    name: str
    color_available: str = "green"  # 이 종류의 빈칸이 있을 때 만공등 색


# 주차 종류는 고정 (순서도 이대로 표시). 바꿀 수 있는 것은 색뿐이다.
FIXED_SLOT_TYPES = [("normal", "일반"), ("compact", "경차"), ("disabled", "장애인"), ("ev", "전기차")]
DEFAULT_SLOT_TYPES = [SlotType(id=i, name=n) for i, n in FIXED_SLOT_TYPES]


class CameraProfile(BaseModel):
    snapshot_url: str  # {ip}, {port} 치환
    auth: Literal["none", "basic", "digest"] = "digest"
    ref_size: tuple[int, int] = (1280, 960)
    # 추론할 화면 영역 [x, y, w, h] (ref_size 기준)
    views: list[tuple[int, int, int, int]] = [(0, 0, 640, 480), (640, 0, 640, 480)]


class JudgeOverride(BaseModel):
    cover_ratio: float | None = None


class Slot(BaseModel):
    no: int = Field(ge=1, le=MAX_SLOTS_PER_CAMERA)
    type: str = "normal"
    line: tuple[Point, Point]  # 카메라 ref_size 기준 픽셀 좌표
    name: str = ""  # 선택 메모
    judge: JudgeOverride | None = None


class Camera(BaseModel):
    ip: str
    port: int = 80
    profile: str
    user: str = ""
    password: str = ""
    controller_ip: str | None = None  # 용도 확인 필요 (만공등 제어 대상일 가능성)
    board: str | None = None  # 담당 보드명. None이면 어느 보드든 처리
    ref_size: tuple[int, int] | None = None  # None이면 프로필 값
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
    protocol: str | None = None  # 카메라 사양 확인 후 결정


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
        return [SlotType(id=i, name=n, color_available=colors.get(i, "green")) for i, n in FIXED_SLOT_TYPES]

    camera_profiles: dict[str, CameraProfile] = {}
    cameras: list[Camera] = []
    server: ServerCfg = ServerCfg()
    indicator: IndicatorCfg = IndicatorCfg()

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
            for s in cam.slots:
                if s.type not in type_ids:
                    raise ValueError(f"카메라 {cam.ip} {s.no}번 칸: 없는 주차 종류 '{s.type}'")
        return self

    def camera_ref_size(self, cam: Camera) -> tuple[int, int]:
        return cam.ref_size or self.camera_profiles[cam.profile].ref_size

    def cameras_for_board(self) -> list[Camera]:
        """이 보드가 담당할 카메라. board가 비어 있으면 모두 담당."""
        me = self.site.board_name
        return [c for c in self.cameras if c.enabled and (c.board is None or not me or c.board == me)]


def load_config(path: str | Path) -> AppConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


def save_config(cfg: AppConfig, path: str | Path, include_passwords: bool = True) -> None:
    data = cfg.model_dump(mode="json")
    if not include_passwords:
        for cam in data["cameras"]:
            cam["password"] = ""
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
