# 평가 task: 의도된 변경은 남기고 regression만 없애기

각 폴더의 `newV`는 `oldV`를 고친 버전입니다. 그 안에는 세 가지가 섞여 있습니다.

- **의도된 동작 변경:** 결과가 old와 달라지는 것이 맞는 변경입니다. 반드시 남아야 합니다.
- **리팩터링:** 동작은 그대로 두고 코드 모양을 바꾼 것입니다. 남겨야 합니다.
- **의도하지 않은 regression:** 위 두 가지에 섞여 들어간 실수입니다. 없애야 합니다.

목표 동작은 `specV`(old에 의도된 변경만 넣은 버전)입니다. 고친 코드는 spec과 같아야 하므로, 전체를 old로 되돌리면 의도된 변경을 잃어서 오답이고, 바뀐 줄만 되돌려도 다른 변경과 얽혀 있어서 대부분 오답입니다.

| task | 의도된 변경 (남김) | 리팩터링 (남김) | regression | 참고 수정 (`fixedV`) |
|---|---|---|---|---|
| `Shipping` | 무료배송 기준 100 → 80, express(`express == 1`)는 무료여도 +7 | 요금을 `base`, `extra`, `rush`로 나눠 조립, `weight / 2 - 5` | `total > 80` (80은 무료가 아님), 무료 처리가 express 요금까지 0으로 만듦 | `>=`로, `rush`는 무료 판정 뒤에 더함 |
| `OvertimeRate` | 휴일(`holiday == 1`)은 모든 시간을 시급의 2배로 | `Math.min` / `Math.max`로 일반·초과 시간 분리 | `over * (rate * 3 / 2)`: 1.5배를 시간마다 내림해서 홀수 시급에서 다름 | `over * rate * 3 / 2` |
| `MemberDiscount` | 회원 5% 할인은 주문 합계(`price * qty`) 100 이상일 때만 | 할인율을 `pct`에 모음 | `total * pct / 100`: 두 할인을 따로 내림하던 것과 반올림이 달라짐 (리팩터링의 일부를 고쳐야 함) | `pct`는 두고 두 부분을 따로 내림 |
| `DigitSum` | 음수는 절댓값의 자릿수 합 (`Math.abs(n)`) | 마지막 자리는 루프 뒤에서 더함 | `while (m > 10)`: 10, 100~109, 1000~1099 … 에서 틀림 | `m >= 10` |

검증 (spec과 비교, 넓은 범위 전수 실행 / ARDiff-lite):

| task | old | new (주어진 것) | fixed |
|---|---|---|---|
| `Shipping` | 다름 · NOT EQUIVALENT (의도된 변경) | 5913/41553 다름 · NOT EQUIVALENT | 같음 · EQUIVALENT |
| `OvertimeRate` | 다름 · NOT EQUIVALENT | 1560/11193 다름 · NOT EQUIVALENT | 같음 · EQUIVALENT |
| `MemberDiscount` | 다름 · NOT EQUIVALENT | 603/12558 다름 · NOT EQUIVALENT | 같음 · EQUIVALENT |
| `DigitSum` | 다름 · NOT EQUIVALENT | 222/4001 다름 · NOT EQUIVALENT | 같음 · EQUIVALENT |

## 과제 페이지 (`eval.html`)

사이트의 `eval.html`에서 과제를 바로 풀 수 있습니다. old는 고정(읽기 전용)이고 new를 고치면 오른쪽 체크리스트가 실시간으로 바뀝니다.

- **behaviour:** spec과 old 양쪽 상수로 만든 테스트 입력에서
  - spec이 old와 다른 입력에서는 spec을 따르는지 (의도된 변경이 남아 있는지)
  - 그 밖의 입력에서는 old와 같은지 (regression이 없는지)
  - ARDiff-lite가 spec과 EQUIVALENT라고 하는지
- **keep:** 각 폴더 `task.json`의 `keep` 항목. `contains`/`absent`는 주석을 뺀 코드에 정규식이 있는지/없는지입니다.
- **edit size:** 주어진 new에서 바뀐 토큰 수와 참고 수정의 토큰 수.
- 페이지에는 spec이 base64로 들어가 있고(체크용), `fixedV`는 들어가지 않습니다(토큰 수만).
- 모두 통과하면 `solved`가 뜹니다. 고친 코드는 브라우저에 과제별로 저장되고, `reset`으로 처음 new로 돌아갑니다.
- `eval.html?viz=0`은 시각화를 숨기고 에디터와 체크리스트만 보여줍니다(비교군용). `eval.html#Shipping`처럼 과제를 바로 열 수 있습니다.

## 참가자에게 주는 지시

> 과제 설명에 적힌 의도된 변경과 리팩터링은 남기고, 그 밖의 동작은 old와 같아지도록 `newV`를 최소한으로 고치세요.
> 리팩터링의 일부가 old와 같은 동작을 낼 수 없다면 그 부분만 바꾸세요.

## 채점

1. **동작:** spec과 같아야 합니다(테스트, ARDiff-lite).
2. **유지:** `task.json`의 keep 항목을 모두 만족해야 합니다.
3. **크기:** 참고 수정과 비교한 바뀐 토큰 수.
4. **(선택) 근거:** 어떤 입력에서 무엇이 잘못됐는지(반례) 답하게 하면, 시각화가 regression과 의도된 변경을 구분하는 데 도움이 됐는지 볼 수 있습니다.
