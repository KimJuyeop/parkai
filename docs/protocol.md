# 서버 전송 규격

## 주차면 상태

```
POST http://[서버주소]:[서버포트]/api/camerastatuses
Content-Type: application/json
```

```json
{
  "data": {
    "ipaddress": "192.168.11.3",
    "boardip": "192.168.20.1",
    "ps01": "1",
    "ps02": "2",
    "ps03": "unknown",
    "ps04": "unknown",
    "ps05": "unknown",
    "ps06": "unknown",
    "ps07": "unknown",
    "ps08": "unknown",
    "ps09": "unknown",
    "ps10": "unknown",
    "ps11": "unknown",
    "ps12": "unknown"
  }
}
```

| 필드 | 의미 |
|---|---|
| `ipaddress` | 카메라 IP |
| `boardip` | 판정한 보드 IP |
| `ps01`~`ps12` | 칸별 상태. `"1"` 차량 있음 / `"2"` 차량 없음 / `"unknown"` 설정 안 된 칸 |

## 동작 규칙

- 카메라 1대당 메시지 1개, **매 사이클** 전송 (대기열 없음)
- 서버가 응답하지 않으면 그 사이클 전송은 버린다. 다음 사이클에 최신 상태가 다시 간다.
- 판정할 수 없는 카메라(응답 없음, 화면 이상)는 **전송하지 않는다.**
- 화면 하나만 이상하면 그 화면의 칸은 마지막 상태를 보낸다.
- 타임아웃 2초, 연결 재사용.
