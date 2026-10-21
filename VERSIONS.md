# 고정 버전

보드, 런타임, 모델 변환 도구의 버전이 서로 맞아야 한다.
특히 NBG(`.nb`)를 만든 ST Edge AI Core 버전과 보드의 NPU 드라이버 버전이 다르면 모델이 로드되지 않을 수 있다.

| 항목 | 버전 | 상태 |
|---|---|---|
| 칩 | STM32MP257F (개발: STM32MP257F-EV1, 양산 보드는 칩 동일) | 확정 |
| STM32MPU Ecosystem | v6.2.1 | 확정 |
| OpenSTLinux | 6.6 scarthgap, `openstlinux-6.6-yocto-scarthgap-mpu-v26.06.10` | 확정 (보드 확인) |
| Python (보드) | 3.12.12 | 확정 (보드 확인) |
| Python (PC 개발) | 3.12.x | 보드와 맞춤 |
| X-LINUX-AI | v6.2.x 예상 | 설치 후 `x-linux-ai -v`로 확정 |
| ST Edge AI Core (PC) | X-LINUX-AI 릴리스 노트의 대응 버전 | X-LINUX-AI 확정 후 |
| NPU 드라이버 (galcore) | - | `dmesg \| grep -i galcore`로 확인 |

## 보드에서 확인하는 명령

```sh
cat /etc/os-release
uname -r
cat /proc/device-tree/model; echo
cat /proc/device-tree/compatible | tr '\0' '\n'
dmesg | grep -i galcore
x-linux-ai -v
ip link
df -h
```
