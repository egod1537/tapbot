# TapBot Web

React + TypeScript 기반의 TapBot 디버깅 대시보드입니다.

## 시작하기

먼저 저장소 루트에서 Mock Backend를 실행합니다.

```bash
tapbot-ui --robot mock
```

그다음 별도 터미널에서 프론트엔드를 실행합니다.

```bash
npm install
npm run dev
```

개발 서버에서 `/debug`와 `/settings` 경로를 사용할 수 있습니다.

`/debug`는 실제 연결 없이도 전체 레이아웃을 검토할 수 있도록 명시적인 mock
상태와 이벤트를 표시합니다. Camera, Robot, Vision/Model, Timeline 패널은 각각
독립 컴포넌트이며 980px 이하 화면에서는 한 열로 배치됩니다.

## 환경 변수

Vite는 실행 모드에 맞춰 `.env.development` 또는 `.env.production`을 읽습니다.
로컬 설정은 `.env.example`을 참고해 `.env.local`에 작성하세요.

| 변수                  | 기본값 (development)        | 설명                |
| --------------------- | --------------------------- | ------------------- |
| `VITE_API_BASE_URL`   | `http://localhost:8000/api` | 백엔드 API 기본 URL |
| `VITE_API_TIMEOUT_MS` | `10000`                     | 요청 제한 시간(ms)  |

## 확인 명령

```bash
npm run lint
npm run typecheck
npm run build
npm run format:check
```

공통 API 클라이언트는 `src/lib/api-client.ts`에 있으며 timeout, HTTP 오류,
네트워크 오류, JSON 파싱 오류를 `ApiError`로 통일합니다.

Robot Control 패널은 `GET /api/robot/status`로 workspace 및 controller 상태를
조회하고, 좌표나 명령 의미만 Robot API에 전달합니다. 일반 제어 UI는 G-code를
생성하거나 전송하지 않습니다.

G-code Console은 별도의 개발자 도구입니다. `GET /api/gcode/capabilities`가
제공하는 firmware capability와 preset만 표시하며, 입력은
`POST /api/gcode/command`로 전달합니다. 허용 명령, workspace 범위, 단일 행 여부는
Backend가 최종 검증합니다. 모션 명령은 전송 직전에 절대 좌표 모드로 고정되며,
Emergency Stop은 항상 전용 `POST /api/robot/stop` endpoint를 사용합니다.

장비 없이 콘솔의 validation과 dry-run 응답을 확인하려면 Backend를 다음과 같이
실행할 수 있습니다.

```bash
tapbot-ui --robot grbl --dry-run
```

Camera Preview는 `GET /api/camera/frame`에서 JPEG를 주기적으로 가져옵니다.
Backend frame ID와 원본 해상도를 응답 헤더로 받아 SVG `viewBox` 좌표계와
스크린샷 파일명에 사용합니다. 표시되는 overlay는 추론 결과가 아닌 교체 가능한
debug fixture입니다.

Calibration은 `/api/camera/freeze`로 선택용 프레임을 고정한 뒤 TL/TR/BR/BL
camera corner와 robot reference point를 `/api/calibration/preview`에서 먼저
검증합니다. Preview와 현재 입력이 일치하는 경우에만 profile 저장이 활성화됩니다.

Vision Debug 패널은 Backend에 보관된 camera frame을 선택해
`POST /api/vision/run`으로 다시 처리합니다. Detector 목록은
`GET /api/vision/capabilities`에서 가져오며, 활성 detector와 confidence threshold가
매 실행 요청에 포함됩니다. Raw/rectified frame, SVG detection overlay, detection 목록과
상세 정보가 동일한 result ID를 사용하고 직전 결과는 비교용으로 유지됩니다.

Local Model Debug 패널은 현재 또는 저장 frame을 `POST /api/model/run`으로 다시
분석합니다. 입력 screenshot과 context, raw response, structured decision, target/action
resolution 및 각 gate 결과를 하나의 run ID로 추적합니다. 이 endpoint는 Action을
생성할 수는 있지만 Robot dispatcher를 호출하지 않으며, 모든 요청에서
`requested: false`, `executed: false` 경계를 유지합니다.

Timeline은 `GET /api/events/stream`의 SSE를 구독하며 camera, vision, model,
action, robot/G-code event를 correlation ID로 연결합니다. 연결이 끊기면 SSE
`Last-Event-ID`를 사용해 누락 구간을 이어 받고, Pause 중에도 수신은 계속하면서
화면 snapshot만 고정합니다. 표시 중인 event는 payload 상세 확인과 JSON export가
가능합니다.

통합 Dashboard는 공통 System Status Context에서 Backend, Robot, Model 상태와
MOCK/DRY-RUN/REAL mode를 동기화합니다. Camera frame state는 별도 subtree에 격리해
영상 갱신이 다른 panel을 다시 렌더하지 않으며, Calibration과 G-code Console은
격리된 developer tool tab을 열었을 때만 mount됩니다. REAL mode와 Emergency Stop은
화면 상단 safety bar에서 항상 노출됩니다.
