# 평가 task: 리팩터링에서 생긴 회귀 고치기

각 폴더의 `newV`는 `oldV`를 **읽기 쉽게 리팩터링하려다 실수로 동작이 바뀐 버전**입니다. 참가자의 목표는 **모든 입력에서 old와 같은 결과를 내도록 `newV`를 고치는 것**이고, old를 그대로 복사해 넣지 말고 new를 최소한으로 고쳐야 합니다.

| task | 리팩터링 (의도) | 생긴 회귀 | 참고 수정 (`fixedV`) |
|---|---|---|---|
| `Tutorial1` (T1, 시각화) | a에서 시작해 b가 더 크면 바꾸기 | 바꿀 때 `r = a`를 다시 넣음 | `r = b` |
| `Tutorial2` (T2, 줄 diff만) | 더 작은 값을 `smaller` 변수에 담기 | 비교가 뒤집힘 `b > smaller` | `<` |
| `DigitSum` | `while`을 `for` 루프로, 마지막 자리는 루프 뒤에서 더함 | `m > 10`(10, 100 …에서 틀림), 음수면 마지막 자리를 부호째 더함 | `m > 9`, 양수일 때만 마지막 자리 더함 |
| `MemberDiscount` | 할인을 하나의 퍼센트 `pct`로 모음 | `total * pct / 100`: 합계에서 한 번에 내림(old는 단가에서 할인마다) | 마지막 줄: 단가에서 할인마다 내림 |
| `OvertimeRate` | 일반·초과 시간을 `Math.min` / `Math.max`로 나눔 | 1.5배를 한 번에 내림(old는 시간마다) | `over * (rate * 3 / 2)` |
| `Shipping` | 배송비를 이름 붙인 부분으로 조립 | `total > 100`(100은 무료가 아니게 됨) | `>=` |
| `AgeDiscount` | 조건에 이름을 붙여 할인 규칙 하나로 합침 | `senior = age > 65`(65세가 빠짐) | `>=` |
| `LeapYear` | 중첩 if를 조건 하나로 합침 | `(year % 4 == 0 \|\| year % 400 == 0) && year % 100 != 0`: 400의 배수(2000 등)가 윤년이 아니게 됨 | `year % 4 == 0 && year % 100 != 0 \|\| year % 400 == 0` |

**난이도(`task.json`의 `difficulty`):** 하 `Shipping`, `AgeDiscount` · 중 `OvertimeRate`, `LeapYear` · 상 `DigitSum`, `MemberDiscount`. 시각화 배정은 난이도마다 둘 중 하나를 무작위로 시각화, 다른 하나를 줄 diff로 해서 3:3으로 맞춥니다. 난이도는 참가자에게 보이지 않고 결과(이슈 표, JSON)에만 기록됩니다.

검증 (old와 비교, 넓은 범위 전수 실행 / ARDiff-lite):

| task | new (주어진 것) | fixed |
|---|---|---|
| `Tutorial1` | 28920/58081 다름 · NOT EQUIVALENT | 0 다름 · EQUIVALENT |
| `Tutorial2` | 57840/58081 다름 · NOT EQUIVALENT | 0 다름 · EQUIVALENT |
| `DigitSum` | 2111/4001 다름 · NOT EQUIVALENT | 0 다름 · EQUIVALENT |
| `MemberDiscount` | 8455/12558 다름 · NOT EQUIVALENT | 0 다름 · ARDiff-lite 판정 불가(테스트로 판단) |
| `OvertimeRate` | 2340/11193 다름 · NOT EQUIVALENT | 0 다름 · EQUIVALENT |
| `Shipping` | 243/41553 다름 · NOT EQUIVALENT | 0 다름 · EQUIVALENT |
| `AgeDiscount` | 90/13741 다름 · NOT EQUIVALENT | 0 다름 · EQUIVALENT |
| `LeapYear` | 13/5001 다름 · NOT EQUIVALENT | 0 다름 · EQUIVALENT |

## 과제 페이지 (`eval.html`)

사이트의 `eval.html`에서 과제를 바로 풀 수 있습니다. old는 고정(읽기 전용)이고 new를 고치면 체크리스트가 실시간으로 바뀝니다.

- **흐름:** 시작 페이지 → 과제 전 설문 → 튜토리얼 T1(시각화), T2(줄 diff만) → 과제 1~6 → finish → 과제 후 설문 → 결과(이슈 제출 / JSON 다운로드)
- **체크리스트:** old와 new의 상수로 만든 테스트 입력에서 old와 같은 결과인지, ARDiff-lite가 old와 EQUIVALENT라고 하는지(판정 못 하면 "–", 테스트로 판단). 모두 통과하면 `solved`.
- **edit size:** 주어진 new에서 바뀐 토큰 수와 참고 수정의 토큰 수. 페이지에는 `fixedV` 자체는 들어가지 않습니다(토큰 수만).
- 과제 **순서**와 **화면**(과제 1~6 중 난이도별로 하나씩, 3개는 시각화, 3개는 줄 diff만)은 브라우저마다 무작위로 정해지고 유지됩니다. 튜토리얼은 항상 맨 앞이고 각자 `task.json`의 `"view"`를 따릅니다.
- **시각화 없는 화면:** 에디터에 표시한 줄 diff(old의 삭제·변경 줄은 빨강, new의 추가·변경 줄은 초록)만 보입니다. ARDiff-lite는 체크리스트 판정용으로 보이지 않게 돌아갑니다.
- 고친 코드는 과제별로 브라우저에 저장되고, `reset`으로 처음 new로 돌아갑니다.
- 헤더의 **restart**: 새 참가자용. 한 번 더 눌러 확인하면 순서·배정을 새로 뽑고 저장된 수정·측정·설문을 모두 지운 뒤 시작 페이지로 돌아갑니다.
- **측정:** 과제마다 화면, 활동 시간(그 과제가 화면에 있고 탭이 보이는 동안), 처음 solved가 된 활동 시간, 수정 횟수, 마지막 solved 여부, 마지막 코드. **finish** 후 결과 표에서 **Submit as a GitHub issue**(이 저장소에 `[eval] results <참가자 ID> <시각>` 제목의 **공개** 이슈가 미리 채워진 채 열림; 링크가 길면 코드는 클립보드로 복사해 붙여 넣음) 또는 **download JSON**.
- **설문**(`survey.json`): 질문 형식은 `number`, `choice`(`options` / `options_ko`), `scale`(1–5, `low` / `high`), `text`. 답은 이슈와 JSON(`survey.pre`, `survey.post`)에 들어갑니다. 답하지 않아도 넘어갈 수 있습니다.
- **언어:** 헤더의 **EN / 한국어**(또는 `?lang=ko` / `?lang=en`). 과제 설명은 `task.json`의 `title_ko`, `goal_ko`. 코드와 raw output은 번역하지 않고, 이슈와 JSON은 영어로 남기되 사용한 언어를 기록합니다.
- `eval.html?viz=1` / `?viz=0`은 과제 1~6를 모두 시각화 / 줄 diff만으로 고정합니다. `eval.html#Shipping`처럼 과제를 바로 열 수 있습니다.
- 과제에 `specV.java`(old에 의도된 변경을 넣은 버전)를 두면 old 대신 그 spec이 기준이 되고, `task.json`의 `keep`에 제약 검사를 넣을 수 있습니다. 지금 과제들은 쓰지 않습니다.

## 참가자에게 주는 지시

> 새 버전을 고쳐서, 모든 입력에서 기존 버전과 똑같은 결과를 내게 하세요. 기존 버전을 그대로 복사해 넣지 말고, 새 버전을 최소한으로 고치세요.

## 채점

1. **동작:** old와 같아야 합니다(테스트, ARDiff-lite).
2. **크기:** 참고 수정과 비교한 바뀐 토큰 수.
3. **시간:** 처음 solved가 된 활동 시간.
