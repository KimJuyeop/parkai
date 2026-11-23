#!/bin/sh
# parkai 설치 스크립트 (초안)
#
# 번들 안에서 실행:   sudo ./install.sh [--board 보드명]
# 네트워크 없이 번들 안의 파일만으로 설치한다.
#
# TODO
#  - 보드 판별 후 보드 프로필 선택
#  - X-LINUX-AI 설치 여부 확인 (오프라인 .deb 포함 여부 결정 후)
#  - 고정 IP 설정, root 비밀번호/SSH 정책
#  - sha256 검증
set -eu

APP=parkai
PREFIX=/opt/$APP
DATA=/var/lib/$APP
HERE=$(cd "$(dirname "$0")" && pwd)
VERSION=$(cat "$HERE/VERSION")
BOARD=""

while [ $# -gt 0 ]; do
  case "$1" in
    --board) BOARD="$2"; shift 2 ;;
    *) echo "알 수 없는 옵션: $1"; exit 1 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "root로 실행하세요 (su -)"; exit 1; }

echo "[1/5] 계정과 폴더"
id $APP >/dev/null 2>&1 || useradd --system --no-create-home --shell /sbin/nologin $APP
mkdir -p "$PREFIX" "$DATA/models" "$DATA/results"

echo "[2/5] 프로그램 복사 ($VERSION)"
DEST="$PREFIX/$VERSION"
rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$HERE/app/." "$DEST/"

echo "[3/5] Python 환경 (오프라인 wheel)"
# 시스템 패키지(OpenCV, numpy, stai_mpu)를 그대로 쓰기 위해 --system-site-packages
python3 -m venv --system-site-packages "$DEST/venv"
# 소스 폴더가 아니라 미리 만든 wheel 을 설치한다 (소스 설치는 setuptools 가 필요한데 오프라인 번들에 없음)
"$DEST/venv/bin/pip" install --no-index --find-links "$HERE/wheels" parkai

echo "[4/5] 설정"
if [ ! -f "$DATA/config.json" ]; then
  cp "$HERE/app/examples/config.default.json" "$DATA/config.json"
fi
if [ -n "$BOARD" ]; then
  "$DEST/venv/bin/python" - "$DATA/config.json" "$BOARD" <<'EOF'
import json, sys
p, board = sys.argv[1:]
c = json.load(open(p, encoding="utf-8"))
c.setdefault("site", {})["board_name"] = board
json.dump(c, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
EOF
fi
chown -R $APP:$APP "$DATA"
chmod 600 "$DATA/config.json"

echo "[5/5] 서비스"
PREV=$(readlink "$PREFIX/current" 2>/dev/null || true)
# 시스템 로그는 RAM 에만, 50MB 까지 (SD카드에 쓰지 않음)
mkdir -p /etc/systemd/journald.conf.d
cp "$HERE/journald/parkai.conf" /etc/systemd/journald.conf.d/parkai.conf
systemctl restart systemd-journald || true
if [ -n "$PREV" ] && [ "$PREV" != "$DEST" ]; then ln -sfn "$PREV" "$PREFIX/previous"; fi
ln -sfn "$DEST" "$PREFIX/current"
# SD 용량: 지금 것과 최근 2개만 남긴다 (current·previous 가 가리키는 폴더는 남김).
# 빌드 폴더(숫자로 시작: 0.1.0, 0.1.0-20261123-ed076b4)만 지운다. dev 처럼 손으로 만든 폴더는 건드리지 않는다
for d in $(ls -1dt $(find "$PREFIX" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*') | tail -n +4); do
  [ "$d" = "$DEST" ] || [ "$d" = "$PREV" ] || rm -rf "$d"
done
cp "$HERE/systemd/"*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now parkai-worker parkai-web
systemctl restart parkai-worker parkai-web

echo "설치 완료: $VERSION  (웹: http://<보드 IP>/)"
if [ -n "$PREV" ] && [ "$PREV" != "$DEST" ]; then
  echo "이전 빌드: $(basename "$PREV")"
  echo "되돌리기: ln -sfn \$(readlink $PREFIX/previous) $PREFIX/current && systemctl restart parkai-worker parkai-web"
fi
