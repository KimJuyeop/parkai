"""보드 NPU 백엔드 (X-LINUX-AI stai_mpu Python API).

참고: https://wiki.st.com/stm32mpu/wiki/STAI_MPU_Python_Reference
보드에서 미검증 - X-LINUX-AI 설치 후 입출력 텐서 정보(양자화 포함) 확인 필요.
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
        # API 이름은 X-LINUX-AI 버전 확인 후 정리
        infos = getattr(self.net, "get_output_infos", None) or self.net.get_output_info
        self.n_outputs = len(infos())

    def _run(self, tensor: np.ndarray) -> list[np.ndarray]:
        self.net.set_input(0, np.expand_dims(tensor, 0))
        self.net.run()
        return [self.net.get_output(i) for i in range(self.n_outputs)]
