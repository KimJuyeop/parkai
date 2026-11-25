#!/bin/sh
# 오프라인 설치 번들 생성 (초안). PC(Linux/WSL)에서 실행.
#
#   ./packaging/build_bundle.sh
#   -> packaging/out/parkai-<버전>-stm32mp25.tar.gz
#
# 보드용 wheel은 aarch64 / cp312 기준으로 받는다.
# OpenCV, numpy, stai_mpu는 보드 시스템 패키지(X-LINUX-AI)를 사용하므로 제외.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(python3 -c "import tomllib;print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])")
NAME="parkai-$VERSION-stm32mp25"
# 빌드 이름: 버전-날짜-커밋 (고친 파일이 커밋 전이면 -dirty). 보드에는 /opt/parkai/<빌드 이름> 으로 따로 설치돼
# 이전 빌드로 되돌릴 수 있다. 파일 이름(NAME)은 그대로 두어 설치 명령이 바뀌지 않게 한다
COMMIT=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)
git -C "$ROOT" diff --quiet HEAD -- 2>/dev/null || COMMIT="$COMMIT-dirty"
BUILD="$VERSION-$(date +%Y%m%d)-$COMMIT"
OUT="$ROOT/packaging/out"
STAGE="$OUT/$NAME"

rm -rf "$STAGE"
mkdir -p "$STAGE/app" "$STAGE/wheels" "$STAGE/systemd"

# 웹 화면 빌드 (React → parkai/web/static). 보드에는 빌드 결과만 들어가고 Node는 필요 없다.
(cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
test -f "$ROOT/parkai/web/static/index.html" || { echo "웹 화면 빌드 실패" >&2; exit 1; }

# 앱
cp -r "$ROOT/parkai" "$ROOT/pyproject.toml" "$ROOT/README.md" "$STAGE/app/"
find "$STAGE/app" -name __pycache__ -type d -prune -exec rm -rf {} +
echo "BUILD = \"$BUILD\"" > "$STAGE/app/parkai/_build.py"
# 보드에서 쓰는 점검 도구 (모델 비교 등). 설치 후 /opt/parkai/current/tools
mkdir -p "$STAGE/app/tools"
cp "$ROOT/tools/compare_judge.py" "$ROOT/tools/bench_model.py" "$ROOT/tools/load_test.py" \
  "$ROOT/tools/collect_snapshots.py" "$ROOT/tools/fake_server.py" "$STAGE/app/tools/"
mkdir -p "$STAGE/app/examples"
cp "$ROOT/examples/config.example.json" "$STAGE/app/examples/config.default.json"

# 보드용 wheel (numpy는 시스템 패키지 사용). 버전은 requirements-board.txt 로 고정
python3 -m pip download --dest "$STAGE/wheels" \
  --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 \
  --python-version 3.12 --implementation cp --only-binary=:all: \
  -r "$ROOT/packaging/requirements-board.txt"
python3 -m pip wheel --no-deps --wheel-dir "$STAGE/wheels" "$STAGE/app"
# wheel 을 만들며 생긴 중간 파일은 번들에 넣지 않는다
rm -rf "$STAGE/app/build" "$STAGE/app/"*.egg-info

cp "$ROOT/packaging/install.sh" "$STAGE/"
cp "$ROOT/packaging/requirements-board.txt" "$STAGE/"
cp "$ROOT/packaging/systemd/"*.service "$STAGE/systemd/"
mkdir -p "$STAGE/journald"
cp "$ROOT/packaging/journald/parkai.conf" "$STAGE/journald/"
echo "$BUILD" > "$STAGE/VERSION"
chmod +x "$STAGE/install.sh"

tar -C "$OUT" -czf "$OUT/$NAME.tar.gz" "$NAME"
sha256sum "$OUT/$NAME.tar.gz" > "$OUT/$NAME.tar.gz.sha256"
echo "생성: $OUT/$NAME.tar.gz  (빌드 $BUILD)"
