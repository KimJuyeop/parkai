"""PC 개발용 백엔드 (onnxruntime, CPU)."""

from __future__ import annotations

import numpy as np

from .base import ModelDetector, ModelPackage


class OnnxDetector(ModelDetector):
    name = "onnx"

    def __init__(self, pkg: ModelPackage):
        super().__init__(pkg)
        import onnxruntime as ort

        self.sess = ort.InferenceSession(str(pkg.path / "model.onnx"), providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0]

    def _run(self, tensor: np.ndarray) -> list[np.ndarray]:
        x = np.expand_dims(tensor, 0)
        if self.pkg.extra.get("layout", "nhwc") == "nchw":
            x = x.transpose(0, 3, 1, 2)
        if "float" in self.inp.type:
            x = x.astype(np.float32) / float(self.pkg.extra.get("input_scale", 255.0))
        return self.sess.run(None, {self.inp.name: x})
