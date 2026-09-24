# TapBot Android Agent

ADB에 런타임 의존하지 않는 Android 화면/입력 Agent입니다. Android 앱은 화면을
제공하고 primitive 입력만 실행합니다. Vision, VLM, 매크로, 앱별 상태 머신은 이
모듈에 포함하지 않습니다.

## 빌드와 설치

Android Studio에서 `android-agent` 디렉터리를 열거나 JDK 17로 다음을 실행합니다.

```powershell
./gradlew.bat test assembleDebug
```

생성된 `app/build/outputs/apk/debug/app-debug.apk`를 기기에 한 번 설치합니다. APK를
설치한 뒤의 서버 실행과 원격 제어에는 ADB가 필요하지 않습니다.

앱을 열면 foreground Agent server가 자동 시작됩니다.

1. `Enable Accessibility`에서 `TapBot Input Service`를 활성화합니다.
2. `Grant Screen Capture`를 누르고 MediaProjection 권한을 허용합니다.
3. 화면에 표시된 LAN endpoint와 Bearer token을 PC에서 사용합니다.

초기 구현은 portrait 고정이며, 캡처 JPEG 크기와 logical screen 좌표가 1:1입니다.
물리/논리 해상도, density, rotation, system inset은 status 응답에 별도로 표시됩니다.

## API

기본 포트는 `8765`입니다. 모든 API 요청은 앱이 최초 실행 때 생성한 256-bit token을
요구합니다. token은 Android private SharedPreferences에 저장되며 앱 화면에서 복사할
수 있습니다.

```http
Authorization: Bearer <token>
```

| Method | Path                    | 설명                         |
| ------ | ----------------------- | ---------------------------- |
| GET    | `/api/v1/status`        | 권한, display, 연결 상태     |
| GET    | `/api/v1/screen`        | 최신 화면 JPEG               |
| GET    | `/api/v1/screen/stream` | latest-frame MJPEG stream    |
| POST   | `/api/v1/input/tap`     | 절대 logical 좌표 tap        |
| POST   | `/api/v1/input/swipe`   | 절대 logical 좌표 swipe      |
| POST   | `/api/v1/input/back`    | Android global back          |
| POST   | `/api/v1/input/home`    | Android global home          |
| POST   | `/api/v1/input/recents` | Android global recents       |

PC Macro Engine용 canonical primitive 경로는 다음과 같습니다. 위 `/api/v1/...`
경로도 기존 호환성을 위해 유지합니다.

| Method | Path              | 설명                         |
| ------ | ----------------- | ---------------------------- |
| GET    | `/api/status`     | Agent/display/control 상태   |
| GET    | `/api/screenshot` | 최신 JPEG                    |
| POST   | `/api/tap`        | 완료 callback까지 기다림     |
| POST   | `/api/swipe`      | 완료 callback까지 기다림     |
| POST   | `/api/back`       | global action dispatch       |
| POST   | `/api/home`       | global action dispatch       |
| GET    | `/api/ui-tree`    | 현재 build에서는 명시적 501  |
| GET    | `/api/stream`     | 인증된 MJPEG live stream     |

Screen capture/stream 전용 별칭도 제공합니다.

| Method | Path                       | 설명                              |
| ------ | -------------------------- | --------------------------------- |
| GET    | `/api/screenshot`          | 최신 JPEG와 frame metadata header |
| GET    | `/api/screenshot/metadata` | 최신 frame metadata JSON          |
| GET    | `/api/stream`              | MJPEG live stream                 |
| GET    | `/api/stream/status`       | FPS/bitrate/latency/client 상태   |
| GET    | `/viewer`                  | token 입력형 PC browser viewer    |

`/viewer` 자체에는 화면이나 token이 포함되지 않습니다. 사용자가 token을 입력하면 Bearer
인증으로 읽기 전용 HttpOnly viewer session을 발급하고, 그 세션으로 MJPEG를 표시합니다.
token을 URL query에 넣지 않습니다.

모든 JSON 응답은 아래 envelope를 사용합니다.

```json
{
  "ok": true,
  "request_id": "...",
  "error": null
}
```

입력 성공 응답에는 `action_id`, `command`, `state`,
`retry_policy: "do_not_retry_automatically"`가 추가됩니다. tap/swipe의 `state`는
Accessibility gesture callback이 도착한 뒤 `completed`가 됩니다. Android가 취소하면
`gesture_cancelled`, callback 제한 시간을 넘기면 `gesture_result_timeout`이며 후자는
실행 여부가 불명확하므로 자동 재시도하면 안 됩니다. back/home은 완료 callback을
제공하지 않는 Android global action이라 접수 성공 시 HTTP 202와 `state=dispatched`를
반환합니다.

Android callback timeout은 gesture duration + 2초입니다. Python/PC client timeout은
최소 gesture duration + 3초를 권장합니다.

기본 입력 guard:

- tap: 최대 10회/초
- swipe: 최대 4회/초
- back/home/recents: 최대 6회/초
- 동시 gesture는 queue에 넣지 않고 `gesture_busy`로 거부

앱의 `Remote Control`은 최초 설치 시 OFF입니다. 입력을 보내기 전에 앱에서 켜야 하며,
비상 시 이 토글을 끄면 screenshot/stream은 유지하면서 모든 input endpoint를 즉시
차단합니다. `Stop Agent`와 notification의 `Stop`은 server까지 종료합니다.

Screenshot 응답 header:

- `X-Frame-Id`
- `X-Screen-Width`, `X-Screen-Height`
- `X-Rotation`
- `X-Captured-At` (ISO-8601)
- `X-Captured-At-Ms`

예시:

```powershell
$headers = @{ Authorization = "Bearer <token>" }
Invoke-RestMethod http://192.168.0.20:8765/api/v1/status -Headers $headers

Invoke-RestMethod http://192.168.0.20:8765/api/v1/input/tap `
  -Method Post -Headers $headers -ContentType application/json `
  -Body '{"x":540,"y":1800,"duration_ms":75}'

Invoke-RestMethod http://192.168.0.20:8765/api/v1/input/swipe `
  -Method Post -Headers $headers -ContentType application/json `
  -Body '{"x1":540,"y1":1800,"x2":540,"y2":600,"duration_ms":350}'
```

Python client:

```python
from tapbot.android import AndroidAgentClient

client = AndroidAgentClient("http://192.168.0.20:8765", "<token>")
status = client.status()
frame = client.screenshot()
result = client.tap(540, 1800)
```

`AndroidAgentClient`는 자동 retry를 하지 않습니다. 특히 tap/swipe/back/home 전송 중
network timeout이 발생하면 `AndroidAgentTransportError.outcome_unknown=True`로
보고하여 Macro Engine이 같은 입력을 무조건 재전송하지 않게 합니다.

좌표가 logical display 범위를 벗어나거나 Accessibility/MediaProjection이 비활성화된
경우, API는 서로 다른 `error.code`를 반환합니다. 화면 픽셀이나 token은 logcat에
기록하지 않습니다.

## 수명 주기와 backpressure

- `ScreenStreamService`가 HTTP server와 MediaProjection을 foreground에서 유지합니다.
- 캡처는 최대 20 FPS로 최신 JPEG 하나만 보관합니다.
- MJPEG client는 최신 frame만 가져가므로 느린 client를 위한 frame queue가 쌓이지
  않습니다.
- 앱의 `Stop Agent` 또는 notification의 `Stop`은 server, stream client, virtual
  display, ImageReader, MediaProjection thread를 정리합니다.
- 프로세스가 재시작되면 server는 복구되지만 Android 보안 정책상 MediaProjection
  권한은 다시 받아야 하며 status에 `capture_ready=false`로 표시됩니다.

현재 browser transport는 명세가 허용한 초기 MJPEG 구현입니다. `ScreenCaptureProvider`
가 screenshot/stream에 동일 `ScreenFrame`을 공급하므로 두 경로의 width, height,
rotation과 tap logical coordinate가 일치합니다. H.264 + WebSocket 또는 WebRTC는 이
provider 위에 별도 encoder/transport로 추가할 수 있습니다.

상태별 동작:

- 앱 전환: MediaProjection session과 stream을 그대로 유지합니다.
- rotation/해상도 변경: Agent를 재시작하지 않고 VirtualDisplay와 ImageReader surface를
  새 logical geometry로 교체하며 이전 frame을 즉시 폐기합니다.
- 화면 꺼짐/잠금: 기기 정책에 따라 black frame 또는 frame 정지가 발생할 수 있습니다.
  stream server는 유지되고 `/api/stream/status`의 FPS가 0으로 내려갑니다.
- `FLAG_SECURE` 화면: Android 정책에 따라 검은 화면이며 우회하지 않습니다.
- Wi-Fi/브라우저 연결 끊김: 해당 stream client만 정리됩니다. viewer는 1초 뒤 stream
  URL을 다시 열며 Agent/capture session은 재시작하지 않습니다.

현재 LAN 전송은 HTTP이므로 신뢰할 수 있는 개발 Wi-Fi에서만 사용하세요. 모든 control
endpoint는 token 인증을 강제하지만 TLS/pairing/mDNS는 후속 범위입니다.
