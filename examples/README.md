# examples

ARDiff에 돌릴 입력 쌍을 폴더 하나에 하나씩 넣습니다. push하면 GitHub Actions가 실행되고 Pages 뷰어가 갱신됩니다.

```
examples/<이름>/oldV.java
examples/<이름>/newV.java
```

규칙 (ARDiff 입력 조건):
- 각 파일은 컴파일 가능한 클래스 하나. 클래스 이름은 `oldV`, `newV`
- 첫 번째 메서드가 비교 대상이며, 두 메서드의 이름·파라미터·반환 타입이 같아야 함
- `package` 선언은 있어도 되고 없어도 됨
- 정수/실수 연산 위주의 코드가 잘 동작함 (객체, 컬렉션, 문자열 등은 지원이 제한적)

`Discount/`는 예시입니다. 조건문 `qty > 10` → `qty >= 11`, `total * 0.9` → `(base + tax) * 0.9`로 바뀌었고,
`total = base + tax`가 UF로 추상화돼 있으면 같음을 증명할 수 없어서 ARDiff가 그 줄을 한 번 복원(refine)한 뒤 EQUIVALENT로 판정합니다.
