"""PC 확인용 TFLite 백엔드 (ai-edge-litert).

보드 .nb 의 원본(TFLite per-tensor int8)을 PC 에서 같은 조건으로 돌린다.

    pip install ai-edge-litert
"""

from __future__ import annotations

import numpy as np

from .base import ModelDetector, ModelPackage


class TfliteDetector(ModelDetector):
    name = "tflite"

    def __init__(self, pkg: ModelPackage):
        super().__init__(pkg)
        from ai_edge_litert.interpreter import Interpreter

        self.it = Interpreter(model_path=str(pkg.path / "model.tflite"))
        self.it.allocate_tensors()
        self.inp = self.it.get_input_details()[0]
        self.outs = self.it.get_output_details()

    def _run(self, tensor: np.ndarray) -> list[np.ndarray]:
        x = np.expand_dims(tensor, 0)
        if self.inp["dtype"] == np.float32:
            x = x.astype(np.float32) / float(self.pkg.extra.get("input_scale", 255.0))
        else:  # uint8 입력: 1/255 는 모델 안에 들어 있다
            x = x.astype(self.inp["dtype"])
        self.it.set_tensor(self.inp["index"], x)
        self.it.invoke()
        return [self.it.get_tensor(o["index"]) for o in self.outs]
