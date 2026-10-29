# same old, two news

다섯 개의 old마다 같은 동작인 new(`Eq`)와 다른 동작인 new(`NEq`)가 하나씩 있습니다. 같은 old에서 어떤 수정은 괜찮고 어떤 수정은 동작을 바꾸는지 나란히 볼 수 있습니다.

| old | `Eq` new | `NEq` new |
|---|---|---|
| `Grade` | 기준을 `pass = 59` 변수로 빼고 `score > pass`, `score > pass + 30`; 두 번째 등급은 `g = g + 1` | `score >= 90` → `score > 90` (90점에서 다름) |
| `EvenSum` | 짝수 판정을 `(i / 2) * 2 == i`로, 더하는 값을 `2 * (i / 2)`로 (조건 안에서만 같음) | `i < n` → `i <= n` (n이 짝수면 n을 더함) |
| `Avg3` | `avg = a + b; avg = avg + c; avg = avg / 3;` 세 단계로 | `a / 3 + b / 3 + c / 3` (나머지 손실) |
| `TaxQty` | `qty * price`, `tax = price * qty / 10`, `total = tax + total` | `tax = price / 10 * qty` (나머지 손실) |
| `AbsDiff` | `d = -b + a`, `0 > d`, `d = 0 - d` (경로는 그대로, 식만 바꿈) | `d < 0` → `d < -1` (차이가 -1일 때 다름) |

