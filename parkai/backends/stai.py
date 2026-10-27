"""보드 NPU 백엔드 (X-LINUX-AI 6.2 stai_mpu Python API, .nb 모델).

API 는 X-LINUX-AI 6.2 의 ST 예제(object-detection/ssd_mobilenet_pp.py)와 같은 방식으로 쓴다:
    stai_mpu_network(model_path, use_hw_acceleration) · get_input_infos() · get_num_outputs()
    set_input(0, x) · run() · get_output(index=i)
모델: TFLite per-tensor int8 → ST Edge AI Core 2.2 로 만든 .nb (per-channel 은 대부분 GPU 로 넘어가 느리다)
보드 설치: apt 저장소 extra.packages.openstlinux.st.com/AINPU/6.2 의 stai-mpu-ovx, python3-stai-mpu.
"""

from __future__ import annotations

import logging

import numpy as np

from .base import ModelDetector, ModelPackage

log = logging.getLogger(__name__)


def _qparams(info) -> tuple[float, int] | None:
    """정수 텐서의 (scale, zero_point). 없거나 읽을 수 없으면 None."""
    try:
        scale, zp = float(info.get_scale()), int(info.get_zero_point())
    except Exception:
        return None
    return (scale, zp) if scale > 0 else None


def _describe(info) -> str:
    return f"{tuple(info.get_shape())} {np.dtype(info.get_dtype()).name} q={_qparams(info)}"


class StaiDetector(ModelDetector):
    name = "stai"

    def __init__(self, pkg: ModelPackage):
        super().__init__(pkg)
        from stai_mpu import stai_mpu_network  # 보드에만 존재

        self.net = stai_mpu_network(model_path=str(pkg.path / "model.nb"), use_hw_acceleration=True)
        self.in_info = self.net.get_input_infos()[0]
        self.out_infos = self.net.get_output_infos()
        self.n_outputs = self.net.get_num_outputs()
        self.float_input = self.in_info.get_dtype() == np.float32
        # 입력 배치는 .nb 자체에서 읽는다: TFLite 에서 만든 .nb 는 NHWC, ONNX 에서 만든 것은 NCHW 일 수 있어
        # 같은 모델 폴더의 model.onnx(PC용)와 다를 수 있다
        shape = tuple(self.in_info.get_shape())
        self.nchw = len(shape) == 4 and shape[1] == 3 and shape[3] != 3
        self.in_dtype = np.dtype(self.in_info.get_dtype())
        self.in_q = _qparams(self.in_info) if self.in_dtype.kind in "iu" else None
        self.out_q = [_qparams(i) if np.dtype(i.get_dtype()).kind in "iu" else None for i in self.out_infos]
        log.info(
            "NPU 모델 %s: 입력 %s, 출력 %s",
            pkg.path.name,
            _describe(self.in_info),
            ", ".join(_describe(i) for i in self.out_infos),
        )

    def _run(self, tensor: np.ndarray) -> list[np.ndarray]:
        x = np.expand_dims(tensor, 0)
        if self.nchw:
            x = x.transpose(0, 3, 1, 2)
        if self.float_input:
            x = x.astype(np.float32) / float(self.pkg.extra.get("input_scale", 255.0))
        elif self.in_q is not None and self.in_q != (1 / 255, 0):
            # 정수 입력의 눈금이 '픽셀/255' 와 다르면 (예: int8, zero_point -128) 그 눈금으로 바꾼다
            scale, zp = self.in_q
            info = np.iinfo(self.in_dtype)
            v = x.astype(np.float32) / float(self.pkg.extra.get("input_scale", 255.0))
            x = np.clip(np.round(v / scale + zp), info.min, info.max).astype(self.in_dtype)
        else:
            x = x.astype(self.in_dtype)
        self.net.set_input(0, np.ascontiguousarray(x))
        self.net.run()
        outs = []
        for i in range(self.n_outputs):
            o = np.asarray(self.net.get_output(index=i))
            q = self.out_q[i]
            if q is not None and o.dtype.kind in "iu":  # 정수 출력이면 실수로 되돌린다
                o = (o.astype(np.float32) - q[1]) * q[0]
            outs.append(o)
        return outs
