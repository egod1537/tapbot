# Reservation verification flow

하드웨어와 실제 앱 없이 `home → reservation → verify-photo` 화면 전이를 반복 검증하는
시나리오입니다. `reservation_button`, `verify_photo_button`, `back_button`,
`home_button` label은 Vision/Model target 이름으로 그대로 사용할 수 있습니다.

- Logical screen: 1280 × 720 pixels
- 모든 hotspot 좌표는 원본 PNG pixel 기준입니다.
- 포함된 화면은 OpenCV로 생성된 합성 이미지이며 개인정보나 실제 서비스 화면을
  포함하지 않습니다.
- 이미지를 교체할 때 세 파일을 동일 크기로 유지하고 `graph.json` 좌표도 함께
  검증하세요.
