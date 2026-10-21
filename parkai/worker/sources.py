"""스냅샷 입력: 실제 카메라(HTTP) 또는 재생(폴더)."""

from __future__ import annotations

from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from ..core.config import Camera, CameraProfile

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


class SourceError(Exception):
    pass


URL_FIELDS = "{ip}, {ipaddress}, {port}"


def build_snapshot_url(template: str, cam: Camera) -> str:
    """스냅샷 URL 템플릿 치환. {ip}와 {ipaddress}는 같은 값."""
    try:
        return template.format(ip=cam.ip, ipaddress=cam.ip, port=cam.port)
    except (KeyError, IndexError, ValueError) as e:
        raise SourceError(f"스냅샷 URL 형식 오류 ({e}). 사용할 수 있는 값: {URL_FIELDS}") from e


def _looks_like_image(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"


class HttpSnapshotSource:
    def __init__(self, cam: Camera, profile: CameraProfile, timeout: float, retries: int):
        self.url = build_snapshot_url(profile.snapshot_url, cam)
        user, password = (cam.user, cam.password) if cam.own_account else (profile.user, profile.password)
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        if profile.auth == "basic":
            self.session.auth = HTTPBasicAuth(user, password)
        elif profile.auth == "digest":
            self.session.auth = HTTPDigestAuth(user, password)

    def fetch(self) -> tuple[bytes, str | None]:
        last: Exception | None = None
        for _ in range(self.retries + 1):
            try:
                r = self.session.get(self.url, timeout=self.timeout)
                if r.status_code == 401:
                    raise SourceError("인증 실패 (401): 사용자/비밀번호 또는 인증 방식(basic/digest) 확인")
                r.raise_for_status()
                if not _looks_like_image(r.content):
                    head = r.content[:120].decode("utf-8", "replace")
                    raise SourceError(f"이미지가 아닌 응답 ({r.headers.get('Content-Type')}): {head}")
                return r.content, None
            except requests.RequestException as e:
                last = e
        raise SourceError(f"{self.url} - {last}")


class BrokenSource:
    """설정 오류로 만들 수 없는 입력. fetch할 때마다 같은 오류를 낸다."""

    def __init__(self, error: str):
        self.error = error

    def fetch(self) -> tuple[bytes, str | None]:
        raise SourceError(self.error)


class ReplaySource:
    """replay_dir/<카메라 IP>/ 안의 이미지를 순서대로 반복해서 돌려준다."""

    def __init__(self, folder: Path):
        self.files = sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_EXT)
        self.i = 0

    def fetch(self) -> tuple[bytes, str | None]:
        if not self.files:
            raise SourceError("재생할 이미지 없음")
        p = self.files[self.i % len(self.files)]
        self.i += 1
        return p.read_bytes(), str(p)
