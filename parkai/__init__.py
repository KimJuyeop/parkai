"""parkai - STM32MP2 기반 주차면 차량 유무 판단 엣지 프로그램."""

__version__ = "0.1.0"

# 번들마다 다른 빌드 이름 (packaging/build_bundle.sh 가 _build.py 를 만든다). 현장에서 어떤 번들이
# 설치됐는지 화면·status.json 으로 확인하고, 설치 폴더를 빌드마다 따로 두어 되돌릴 수 있게 한다.
try:
    from ._build import BUILD
except ImportError:  # 저장소에서 바로 실행 (PC 개발)
    BUILD = f"{__version__}-dev"
