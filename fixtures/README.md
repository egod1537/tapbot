# TapBot Mock Scenario Fixtures

각 directory는 반복 가능한 하나의 UI scenario입니다.

```text
fixtures/
  registry.json
  scenario-id/
    README.md
    graph.json
    state-a.png
    state-b.png
```

## 새 scenario 추가

1. 안정적인 kebab-case ID로 directory를 만듭니다.
2. 합성 또는 비식별 PNG와 `graph.json`, 목적을 설명하는 `README.md`를 추가합니다.
3. `registry.json`의 `scenarios`에 ID와 graph 상대 경로를 한 줄 등록합니다.
4. `npm run validate:fixtures`와 `pytest`를 실행합니다.

코드 수정은 필요하지 않습니다. 등록된 scenario는 `mock:<scenario-id>` Camera source로
자동 노출됩니다.

## graph.json v1

필수 root field:

- `schema_version`: 현재 `1`
- `id`: registry ID와 같은 안정적인 문자열
- `name`: UI 표시 이름
- `description`: scenario 목적
- `screen_width`, `screen_height`: 모든 state PNG의 정확한 pixel 크기
- `initial_state`: 시작 state ID
- `states`: state ID를 key로 하는 object

각 state는 `image`와 `hotspots`를 가집니다. Hotspot의 `x`, `y`, `width`, `height`는
원본 screenshot pixel 좌표이며 logical screen 경계를 벗어날 수 없습니다.
`next_state`는 같은 graph의 state를 참조해야 합니다. `label`은 Vision/Model target과
공유할 수 있도록 snake_case를 사용합니다.

실제 사용자의 이름, 전화번호, 계정, 예약 정보 등 개인정보가 포함된 screenshot은
fixture에 추가하지 않습니다.
