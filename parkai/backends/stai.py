"""보드 NPU 백엔드 (X-LINUX-AI 6.2 stai_mpu Python API, .nb 모델).

API 는 X-LINUX-AI 6.2 의 ST 예제(object-detection/ssd_mobilenet_pp.py)와 같은 방식으로 쓴다:
    stai_mpu_network(model_path, use_hw_acceleration) · get_input_infos() · get_num_outputs()
    set_input(0, x) · run() · get_output(index=i)
보드 설치: apt 저장소 extra.packages.openstlinux.st.com/AINPU/6.2 의 stai-mpu-ovx, python3-stai-mpu.
"""

from __future__ import annotations

import numpy as np

from .base import ModelDetector, ModelPackage


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

    def _run(self, tensor: np.ndarray) -> list[np.ndarray]:
        x = np.expand_dims(tensor, 0)
        if self.pkg.extra.get("layout", "nhwc") == "nchw":
            x = x.transpose(0, 3, 1, 2)
        if self.float_input:
            x = x.astype(np.float32) / float(self.pkg.extra.get("input_scale", 255.0))
        self.net.set_input(0, x)
        self.net.run()
        return [np.asarray(self.net.get_output(index=i)) for i in range(self.n_outputs)]
