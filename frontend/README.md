# TapBot Web

React, TypeScript, Vite, Palantir Blueprint 기반의 Camera + Vision 디버그
워크스페이스입니다. `/debug` 메인 화면은 카메라 입력을 선택하고 저장한 뒤 Vision
파이프라인 결과를 확인하는 흐름에 집중합니다.

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

Blueprint dark theme가 앱 루트에 적용되며 메인 화면에는 다음 영역만 표시됩니다.

- Backend/Camera 상태 Navbar
- 실제 카메라와 Simulation/Image/Video source selector
- 대형 Camera Preview와 Raw/Overlay 전환
- Rectified Vision Preview와 Detection List
- Saved Frame 선택, Save Frame, Run Detection
- 0~100% Confidence Threshold

Mock graph source에서는 현재 state와 hotspot 수를 간단히 표시하고 hotspot bbox를
Camera overlay로 렌더링합니다. Vision 결과의 좌표계와 Camera frame 크기가 같은
경우에는 실제 detection bbox, label, confidence가 Camera overlay에 표시됩니다.

Robot Control, Model Debug, Timeline, G-code Console, Calibration 편집기, Mock Graph
상세 도구의 소스와 Backend API는 유지하지만 `/debug`에서는 렌더링하지 않습니다.

## Camera / Vision API

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
