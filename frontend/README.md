# TapBot Web

React, TypeScript, Vite, Palantir Blueprint 기반의 Android Remote 디버그
워크스페이스입니다. `/debug`는 Android Agent가 제공하는 canonical screen을 PC에서
보고 직접 조작하면서 Vision, state classifier, macro 상태를 확인하는 흐름입니다.

## 시작하기

저장소 루트에서 아래 명령을 실행하면 FastAPI Backend와 React 개발 서버가 함께
실행됩니다. 최초 실행 시 누락된 의존성도 자동으로 설치합니다.

```bash
npm run dev
```

터미널에 표시되는 Dashboard 주소의 `/debug`로 접속하세요. 기본 주소는
`http://localhost:5173/debug`이며, 포트가 사용 중이면 다음 빈 포트를 자동으로
선택합니다. `Ctrl+C`를 누르면 두 서버가 함께 종료됩니다.

Backend와 Frontend를 따로 실행하려면 다음 명령을 사용합니다.

```bash
tapbot-ui --camera mock:reservation-flow --robot mock
cd frontend
npm ci
npm run dev
```

## Debug 화면

Android Agent 연결값은 Backend 환경변수로 설정합니다. token은 React/Vite 환경으로
전달되지 않으며 PC FastAPI가 인증 proxy 역할을 합니다.

```powershell
$env:TAPBOT_ANDROID_AGENT_URL="http://192.168.0.20:8765"
$env:TAPBOT_ANDROID_AGENT_TOKEN="ANDROID_AGENT_TOKEN"
npm run dev
```

Blueprint dark theme가 앱 루트에 적용되며 `/debug`에는 다음 영역이 표시됩니다.

- Android/Stream/Macro 상태 Navbar
- MJPEG live stream과 screenshot fallback
- PC Vision detection overlay와 planned tap point
- 명시적으로 켜야 하는 manual Tap Mode
- Screenshot, Back, Home control
- Macro Start/Stop/Pause/Reset/Step
- State, detection, decision, action result, event log

Android screenshot은 이미 canonical screen이므로 기본 경로에서는 YOLO phone bbox,
screen corner detection, perspective transform을 실행하지 않습니다.

기존 도구는 삭제하지 않고 라우트를 분리했습니다.

- `/tools/webcam`: 기존 Camera Source / phone detection / homography
- `/tools/simulation`: Mock Screen Graph

Robot Control, Model Debug, G-code Console, Calibration 편집기는 `/debug`에서
렌더링하지 않습니다.

## Android Debug API

브라우저는 아래 PC FastAPI endpoint만 사용합니다.

- `GET /api/android/status`
- `GET /api/android/screenshot`
- `GET /api/android/stream`
- `POST /api/android/screenshot/save`
- `POST /api/android/tap`, `/back`, `/home`
- `POST /api/android/vision/run`
- `GET /api/android/debug/state`
- `POST /api/android/macro/start`, `/pause`, `/stop`, `/reset`, `/step`

저장 screenshot과 macro trace 기본 위치는 `tapbot-captures/android`입니다.
`TAPBOT_ANDROID_CAPTURE_DIR`로 변경할 수 있습니다.

## Legacy Camera / Vision API

Camera Preview는 `GET /api/camera/frame`의 JPEG를 주기적으로 가져옵니다. Source
Selector는 다음 API를 사용합니다.

- `GET /api/camera/sources`
- `GET /api/camera/status`
- `POST /api/camera/select`
- `POST /api/camera/reconnect`

물리 카메라, 이미지, 비디오, Mock Screen Graph는 같은 source 목록에 표시됩니다.
Windows의 물리 카메라는 환경변수 없이 MSMF와 DirectShow를 순서대로 검사하고 실제
유효 frame을 반환하는 장치만 discovery 결과에 포함합니다. 비활성 IR interface처럼
열리지만 검은 frame만 반환하는 source는 목록에서 제외됩니다.
새 Mock scenario는 `fixtures/<scenario-id>`를 추가하고 `fixtures/registry.json`에
등록하면 코드 변경 없이 selector에 노출됩니다.

Vision control은 저장과 실행을 분리합니다.

- Save Frame: `POST /api/vision/frames`
- Run Detection: `POST /api/vision/run`
- Detector 정보: `GET /api/vision/capabilities`
- 저장 frame 목록: `GET /api/vision/frames`

Confidence Threshold는 화면에서 0~100%로 표시하고 Backend 요청에는 0~1 값으로
전달합니다.

Raw Preview와 Vision inference는 서로 독립적으로 동작합니다. Camera worker는 최신
프레임을 계속 교체하고, live Vision worker는 queue를 만들지 않고 inference가 끝난
시점의 최신 프레임만 처리합니다.

- `GET /api/vision/live/status`: live worker 상태와 dropped frame 수
- `GET /api/vision/live/result`: 최신 Screen Pipeline 결과
- `GET /api/vision/live/canonical`: 최신 canonical JPEG
- `POST /api/vision/live/start`: background detection 시작
- `POST /api/vision/live/stop`: background detection 중지
- `POST /api/vision/screen-pipeline/run`: 수동 회귀/디버그 실행

Backend live detection 설정은 서버 프로세스 환경변수로 조정합니다.

| 변수                                 | 기본값  | 설명                        |
| ------------------------------------ | ------- | --------------------------- |
| `TAPBOT_VISION_LIVE_ENABLED`         | `true`* | 서버 시작 시 live detection |
| `TAPBOT_VISION_LIVE_TARGET_FPS`      | `10`    | Vision worker 목표 FPS      |
| `TAPBOT_VISION_LIVE_MIN_INTERVAL_MS` | `0`     | inference 간 최소 간격(ms)  |

\* Android Agent가 설정된 기본 workflow에서는 legacy webcam inference가 자동으로
`false`가 됩니다. `/tools/webcam`에서 필요하면 명시적으로 `true`를 설정하세요.

## 환경 변수

Vite는 실행 모드에 맞춰 `.env.development` 또는 `.env.production`을 읽습니다.
로컬 설정은 `.env.example`을 참고해 `.env.local`에 작성하세요.

| 변수                  | 기본값 (development)        | 설명                |
| --------------------- | --------------------------- | ------------------- |
| `VITE_API_BASE_URL`   | `http://localhost:8000/api` | 백엔드 API 기본 URL |
| `VITE_API_TIMEOUT_MS` | `10000`                     | 요청 제한 시간(ms)  |

공통 API 클라이언트는 `src/lib/api-client.ts`에 있으며 timeout, HTTP 오류, 네트워크
오류, JSON 파싱 오류를 `ApiError`로 통일합니다.

## 확인 명령

```bash
npm run lint
npm run typecheck
npm run build
npm run format:check
```

Fixture schema와 이미지/hotspot 참조는 저장소 루트에서 다음 명령으로 검증합니다.

```bash
npm run validate:fixtures
```
