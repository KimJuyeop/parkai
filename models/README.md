# models

모델 패키지 폴더. 바이너리(`.nb`, `.onnx`)는 Git에 올리지 않고 Release로 배포한다.

```
<모델 이름>/
  model.nb     보드 NPU용 (ST Edge AI Core로 생성)
  model.onnx   PC 개발용 (같은 모델)
  model.json   메타 정보
```

`model.json` 예:

```json
{
  "arch": "yolox",
  "input_size": [416, 416],
  "classes": ["car"],
  "color": "rgb",
  "layout": "nhwc",
  "decoded": false,
  "strides": [8, 16, 32],
  "trained_on": "darknet 데이터셋 v1",
  "edgeai_core": "버전 기록"
}
```
