# 평가 task: 최소 수정으로 동작 되돌리기

각 폴더의 `newV`는 `oldV`를 고친 버전입니다. 그 안에는 **유지해야 할 변경**(리팩터링)과 **동작을 바꾼 변경**이 섞여 있습니다.
참가자는 `newV`에서 시작해 `oldV`와 같은 동작이 되도록 고치되, 유지할 변경은 남기고 수정은 최소로 해야 합니다.
그래서 "바뀐 줄을 그냥 되돌리기(rollback)"는 대부분 오답입니다. 유지할 변경을 버리거나, 다른 변경과 얽혀 있어서 새로운 차이를 만들기 때문입니다.

| task | 유지할 변경 | 동작을 바꾼 변경 | 최소 수정 (`fixedV`) | 단순 rollback (`revertedV`) |
|---|---|---|---|---|
| `NamedGrade` | 기준값을 `pass`, `top` 변수로 뺌, 두 번째 등급은 `g = g + 1` | `score > top` (90점이 1등급) | `>` → `>=` | `score >= 90`: 동작은 같지만 이름 붙인 기준값을 버림 |
| `CentsPay` | 금액을 센트 단위(×100)로 | 보너스 기준 `40000` (`405 × 100 = 40500`이어야 함) | `40000` → `40500` | `pay > 405`: 센트와 원 단위를 비교해서 **다른 오답** (`hours = 0`부터 보너스) |
| `StepSum` | 짝수 판정 대신 2씩 증가하는 루프 | `i <= n` (n이 짝수면 n을 더함) | `<=` → `<` | `i++`로 되돌리면 짝수 판정이 없어서 **모든 수를 더하는 오답** |
| `UnitTax` (대조군) | — | 세금을 단가에서 계산 (`price / 10 * qty`, 나머지 손실) | rollback 자체가 정답 | 정답. 유지할 수 있는 형태가 없다는 것을 알아차리는지 봄 |

## 과제 페이지 (`eval.html`)

사이트의 `eval.html`에서 과제를 바로 풀 수 있습니다. old는 고정(읽기 전용)이고 new를 고치면 오른쪽 체크리스트가 실시간으로 바뀝니다.

- **no regression:** 테스트 입력 전부에서 old와 같은 결과인지, ARDiff-lite가 EQUIVALENT인지
- **keep:** 각 폴더 `task.json`의 `keep` 항목. `contains`/`absent`는 주석을 뺀 코드에 정규식이 있는지/없는지, `steps`는 테스트 입력에서 실행한 문장 수가 주어진 new 이하인지(속도 개선 유지)
- **edit size:** 주어진 new에서 바뀐 토큰 수와 참고 수정(`fixedV`)의 토큰 수. 페이지에는 `fixedV` 자체는 들어가지 않고 토큰 수만 들어갑니다.
- 모두 통과하면 `solved`가 뜹니다. 고친 코드는 브라우저에 과제별로 저장되고, `reset`으로 처음 new로 돌아갑니다.
- `eval.html?viz=0`은 시각화를 숨기고 에디터와 체크리스트만 보여줍니다(비교군용). `eval.html#CentsPay`처럼 과제를 바로 열 수 있습니다.

## 참가자에게 주는 지시

> `newV`의 리팩터링(위 표의 "유지할 변경")은 그대로 두고, `oldV`와 모든 입력에서 같은 결과를 내도록 `newV`를 최소한으로 고치세요.
> 리팩터링을 유지한 채로는 같게 만들 수 없다면 그 이유를 쓰고 해당 변경을 되돌리세요.

## 채점

1. **동작:** 고친 코드가 `oldV`와 같은지 확인합니다. 테스트와 ARDiff(-lite)로 EQUIVALENT여야 합니다.
2. **유지:** 표의 "유지할 변경"이 남아 있어야 합니다. `NamedGrade`의 `revertedV`처럼 동작은 같아도 리팩터링을 버리면 감점입니다.
3. **크기:** `fixedV`와 비교한 수정 토큰 수입니다.
4. **(선택) 근거:** 어떤 입력에서 달랐는지(반례) 답하게 하면, 시각화가 반례를 찾는 데 도움이 됐는지 볼 수 있습니다.

`CentsPay`는 일반 테스트 입력(코드의 상수 ±1)으로는 차이가 드러나지 않습니다(`hours = 40`에서만 다름). ARDiff-lite가 반례를 찾아야 보입니다.

검증 결과 (테스트 입력 / ARDiff-lite):

| task | old vs new | old vs fixed | old vs reverted |
|---|---|---|---|
| `NamedGrade` | 1/37 다름 · NOT EQUIVALENT | 같음 · EQUIVALENT | 같음 · EQUIVALENT (리팩터링 손실) |
| `CentsPay` | 0/38 다름 · NOT EQUIVALENT (`hours = 40`) | 같음 · EQUIVALENT | 12/38 다름 · NOT EQUIVALENT |
| `StepSum` | 5/25 다름 · NOT EQUIVALENT | 같음 · EQUIVALENT | 13/25 다름 · NOT EQUIVALENT |
| `UnitTax` | 322/625 다름 · NOT EQUIVALENT | 같음 · EQUIVALENT | 같음 · EQUIVALENT |
