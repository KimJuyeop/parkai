"""스냅샷 입력: 실제 카메라(HTTP) 또는 재생(폴더)."""

from __future__ import annotations

from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from ..core.config import Camera, CameraProfile

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


class SourceError(Exception):
    pass


class HttpSnapshotSource:
    def __init__(self, cam: Camera, profile: CameraProfile, timeout: float, retries: int):
        self.url = profile.snapshot_url.format(ip=cam.ip, port=cam.port)
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        if profile.auth == "basic":
            self.session.auth = HTTPBasicAuth(cam.user, cam.password)
        elif profile.auth == "digest":
            self.session.auth = HTTPDigestAuth(cam.user, cam.password)

    def fetch(self) -> tuple[bytes, str | None]:
        last: Exception | None = None
        for _ in range(self.retries + 1):
            try:
                r = self.session.get(self.url, timeout=self.timeout)
                r.raise_for_status()
                return r.content, None
            except requests.RequestException as e:
                last = e
        raise SourceError(str(last))


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
