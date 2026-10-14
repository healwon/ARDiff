# ARDiff refinement 분석 워크플로

ARDiff를 debug 모드로 실행해 **iteration별 refinement 과정**을 남기고, 이를 **interactive HTML 뷰어**로 만드는 도구 모음입니다.
ARDiff 원본 코드와 jar는 수정하지 않습니다. 이 폴더(`refinement/`)를 ARDiff repo 루트에 두면 repo 위치를 자동으로 찾습니다.

## 빠른 시작

```bash
cd refinement
./ardiff-workflow.sh all          # setup → 기본 예제 5개 실행 → refinement-viewer.html 생성
```

브라우저에서 `refinement-viewer.html`을 열면 됩니다.

## 요구 사항

- Linux x86_64, `python3`, `curl`, `taskset`, `cpio`, `column`
- ARDiff repo: 이 폴더의 상위 폴더 (아니면 `~/workspace/ARDiff`, 다른 위치면 `ARDIFF_REPO=...`)
- sudo 불필요 (JDK는 홈 디렉터리에 설치)

## 명령

| 명령 | 설명 |
|---|---|
| `setup` | 환경 준비 (아래 참고). 여러 번 실행해도 안전 |
| `run [예제...]` | 예제를 debug 모드로 실행. 인자가 없으면 기본 5개 |
| `render [예제...]` | 실행 결과로 HTML 뷰어 생성 |
| `scan` | 전체 143개 벤치마크를 원본 jar로 실행해 iteration 수 순위를 `scan.txt`에 저장 |
| `all [예제...]` | `setup` + `run` + `render` |

예제 이름은 `bench/` 기준 상대 경로입니다(예: `Ran/ran/NEq`, `Bess/bessj0/Eq`).
`examples`를 주면 repo 루트 `examples/` 아래의 모든 입력 쌍을, 인자가 없으면 기본 5개 + `examples/` 전체를 실행합니다.
`--top N`을 주면 `scan.txt`에서 iteration이 가장 많은 N개를 고릅니다.

```bash
./ardiff-workflow.sh run Ran/ran/NEq Bess/bessk/NEq
./ardiff-workflow.sh render Ran/ran/NEq Bess/bessk/NEq

./ardiff-workflow.sh scan                 # 예제당 최대 120초, JOBS개씩 병렬
./ardiff-workflow.sh run --top 5
./ardiff-workflow.sh render --top 5
```

## 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `CORES` | `120-159` | 사용할 CPU 코어 (`taskset -c`) |
| `JOBS` | `4` | 동시에 실행할 예제 수 (예제 1개 = JVM 1개) |
| `TIMEOUT` | `300` | 예제 하나의 제한 시간(초). `scan`은 120초 고정 |
| `HEAP` | `8G` | JVM 최대 힙 (`-Xmx`) |
| `TOOL_ARGS` | `--tool A --H H123` | ARDiff 옵션. 예: `--tool A --H R`, `--b 3` |
| `OUT_HTML` | `./refinement-viewer.html` | 뷰어 출력 경로 |
| `ARDIFF_REPO` | 상위 폴더 또는 `~/workspace/ARDiff` | ARDiff repo 위치 |
| `EXAMPLES_DIR` | `$ARDIFF_REPO/examples` | 사용자 입력 쌍 폴더 |
| `ARDIFF_JAVA_HOME` | (없음) | JavaFX 포함 JDK 8을 직접 지정 (GitHub Actions에서 사용). 없으면 Zulu 8 FX를 내려받음 |
| `WORK` | 스크립트 위치 | 작업 폴더 (`bench/`, `classes/` 등이 생김) |

```bash
JOBS=8 TOOL_ARGS="--tool A --H R" OUT_HTML=random.html ./ardiff-workflow.sh all
```

## setup이 하는 일

1. **JDK 8 + JavaFX**: Azul Zulu 8 FX를 `~/.local/jdk8/`에 설치 (ARDiff가 `javafx.util.Pair`를 사용하므로 JavaFX가 없는 JDK 8은 동작하지 않음).
   환경변수 파일: `~/.local/jdk8/ardiff-env.sh`
2. **JPF 설정**: `~/.jpf/site.properties`를 repo의 `Implementation/jpf-git`으로 지정 (기존 파일 내용이 다르면 `.bak.<시각>`으로 백업)
3. **벤치마크 복사**: repo의 `benchmarks/`를 `bench/`로 복사. ARDiff는 입력 파일 옆에 결과를 쓰기 때문에 repo를 깨끗하게 유지하기 위함
4. **debug 클래스 빌드**: repo 소스에서 두 파일만 패치해 `classes/`에 컴파일
   - `DSE.java`: `debug = true` → refinement 판단 과정(H1/H2/H3)이 로그로 출력됨
   - `GradDiff.java`: 매 iteration마다 중간 파일을 `iterations/iter_NN/`에 저장
5. **동작 확인**: `Airy/MAX/Eq`를 실행해 `EQUIVALENT`가 나오는지 확인

## 실행 결과 위치

```
bench/<예제>/
├── debug.log                  전체 로그 (H1·H2·H3 판단, 선택된 줄)
├── iterations/iter_NN/        iteration별 스냅샷
│   ├── IoldVARDiff.java       이번 iteration의 추상화된 코드 (UF_* = 추상화된 공통 코드)
│   ├── InewVARDiff.java
│   ├── IoldVARDiffJPFOutput.txt   JPF-Symbc 심볼릭 실행 로그
│   ├── z3summary.txt          old/new 요약 수식과 Z3 쿼리
│   ├── *ToSolve.txt           Z3에 넘긴 SMT 쿼리
│   ├── H1Checking.smt2        H1 휴리스틱의 Z3 쿼리
│   ├── gumtree.txt            old/new AST 매칭
│   └── result.txt             이번 iteration의 판정
├── outputs/ARDiffH123.txt     iteration별 결과 요약 (ARDiff 기본 출력)
└── z3models/ARDiff.txt        마지막 iteration의 Z3 수식
```

`debug.log`와 뷰어의 줄 번호는 `iterations/iter_00/oldV.java`(package 줄이 추가된 파일) 기준입니다.

## iteration 간 비교

UF 이름의 번호(`UF_AM_1` → `UF_AM_2`) 변경을 무시하고 실제 변화만 봅니다 ([difftastic](https://github.com/Wilfred/difftastic) `difft` 필요).

```bash
cd bench/Ran/ran/NEq/iterations
../../../../../iterdiff.sh iter_00/IoldVARDiff.java iter_01/IoldVARDiff.java
```

## HTML 뷰어 사용법

- **iteration 이동**: 슬라이더, 번호 버튼, `←` `→` 키. `Space` = 자동 재생
- **벤치마크 선택**: 상단 드롭다운
- **왼쪽 탭**
  - *원본 줄 상태*: 각 줄이 변경된 줄 / UF로 추상화 / 복원됨 / 다음 복원 대상 중 무엇인지
  - *IoldVARDiff / InewVARDiff.java*: 이번 iteration의 추상화된 코드, 이전 iteration 대비 바뀐 줄 표시
  - *Z3 수식*, *JPF 출력*: 해당 iteration의 원본 파일
- **오른쪽 패널**: Z3 판정 흐름, 남은 UF와 H1 결과, H3 순위(줄을 누르면 코드로 이동), 선택된 문장

### refinement 읽는 법

1. 변경되지 않은 공통 코드는 UF(uninterpreted function)로 추상화된 상태로 시작
2. Z3로 "old ≠ new 가 가능한가?"를 검사
   - `UNSAT` → **EQUIVALENT**
   - `SAT` → 반례가 UF 때문일 수 있으므로 "old = new 가 가능하긴 한가?"를 추가 검사. `UNSAT`이면 **NOT EQUIVALENT**
   - 결론이 안 나면(`UNKNOWN` 등) 3으로
3. H1·H2로 결과에 영향을 주는 UF 후보를 고르고, H3가 후보 문장에 순위(R, 낮을수록 먼저)를 매겨 하나를 원래 코드로 복원
4. 2로 돌아가 반복

## 커밋 단위 EQ/NEQ 판정 (`commit`)

커밋(또는 diff)에서 **바뀐 메서드마다** ARDiff를 돌려 EQUIVALENT / NOT EQUIVALENT를 판정하고,
NOT EQUIVALENT면 ARDiff 로그로 **어떤 입력에서 어떻게 달라지는지** 보여줍니다.

```bash
./ardiff-workflow.sh commit                         # 현재 repo의 HEAD vs HEAD^
./ardiff-workflow.sh commit --repo ~/proj --commit abc123
./ardiff-workflow.sh commit --repo ~/proj --range main..feature
./ardiff-workflow.sh commit --repo ~/proj --worktree   # 커밋 전 변경 사항
./ardiff-workflow.sh commit --repo ~/proj --patch fix.diff --base HEAD
./ardiff-workflow.sh commit --old A.java --new B.java  # git 없이 파일 두 개
./ardiff-workflow.sh commit ... --no-run            # 메서드 쌍만 만들고 실행하지 않음
```

| 옵션 | 설명 |
|---|---|
| `--out DIR` | 결과 폴더 (기본 `./ardiff-commit-report`) |
| `--only REGEX` | `Class.method(타입,...)`에 맞는 메서드만 |
| `--no-z3` / `--no-exec` | 차이 영역 분석 / 실제 실행 검증 생략 |
| `--cores --jobs --timeout --heap` | `ardiff-workflow.sh`와 같은 실행 설정 (기본 코어 120-159) |

결과 폴더:

```
report.html   메서드별 판정, 코드 diff, NEQ면 의미 차이 (브라우저로 열기)
report.md     같은 내용의 Markdown (PR 코멘트용)
report.json   전체 데이터
viewer.html   refinement 과정 뷰어 (report.html에서 링크)
pairs/NNN_<Class.method>/   ARDiff 입력(oldV/newV.java)과 실행 결과 전체
```

종료 코드: NOT EQUIVALENT가 하나라도 있으면 `2`, 아니면 `0` (CI에서 사용 가능).

### 처리 과정

1. **바뀐 메서드 찾기**: 두 버전의 `.java`에서 메서드를 `Class.name(파라미터 타입)`으로 맞추고, 주석·공백을 뺀 코드가 다르면 대상.
   주석·공백만 바뀐 메서드는 실행 없이 EQUIVALENT, 추가·삭제된 메서드는 건너뜀
2. **입력 쌍 만들기**: 메서드를 `oldV`/`newV` 클래스로 감쌈. 같은 클래스에서 호출하는 메서드(재귀적으로)와 쓰는 필드, import를 함께 넣음.
   `void` 반환이나 원시 타입이 아닌 파라미터는 ARDiff가 다루지 못해 건너뛰고, 감싼 코드가 컴파일되지 않으면(다른 클래스에 의존 등) 건너뜀
3. **ARDiff 실행**: `ardiff-workflow.sh rundir`로 debug 모드 + iteration 스냅샷
4. **NOT EQUIVALENT 설명** (`commitcheck/semdiff.py`, 마지막 iteration 기준)
   - **ARDiff 반례**: `z3summary.txt`의 Z3 모델 (입력값과 old 반환값). 추상화된 공통 코드(UF)가 남아 있으면 그 값에 기대는 반례라고 표시
   - **차이 영역**: old/new 요약 수식(`*ToSolve.txt`)을 경로별로 나눠, old 경로 i와 new 경로 j의 조건이 동시에 성립하면서 반환값이 다를 수 있는 쌍을 z3로 찾음.
     각 쌍마다 예시 입력과, JPF 출력의 경로 조건·반환식(소스 줄 포함)을 보여 줌
   - **실제 실행 검증**: 원래 old/new 메서드를 컴파일해 반례, 차이 영역 예시, JPF가 만든 테스트 입력으로 직접 실행하고 결과가 다른 입력을 표로 보여 줌.
     추상화 때문에 생긴 가짜 차이를 걸러 내는 단계

ARDiff 실행 결과 하나만 분석하려면: `python3 commitcheck/semdiff.py bench/Ran/ran/NEq`

### 한계

- Java 파서가 아니라 가벼운 스캐너로 메서드를 찾음. 일반적인 코드는 되지만 익명 클래스·람다가 많은 파일은 놓칠 수 있음
- 다른 클래스의 메서드나 인스턴스 상태에 의존하는 메서드는 감싼 코드가 컴파일되지 않아 건너뜀
- 정수/실수 연산 위주의 메서드가 대상. 루프는 ARDiff의 loop bound(`--b`) 안에서만 분석됨
- 차이 영역 분석은 경로 쌍이 많으면 최대 900쌍까지만 검사(`report.json`의 `truncated`)

## 파일 구성

| 파일 | 역할 |
|---|---|
| `ardiff-workflow.sh` | 메인 스크립트 |
| `build_viewer.py` | `debug.log` + `iterations/`를 파싱해 HTML 생성 |
| `viewer_template.html` | 뷰어 템플릿 |
| `iterdiff.sh` | UF 번호를 무시하는 iteration 간 diff |
| `commitcheck/commit_check.py` | 커밋 단위 EQ/NEQ 판정 (`commit` 명령) |
| `commitcheck/semdiff.py` | ARDiff 결과 해석: NEQ의 의미 차이 분석 |
| `commitcheck/javasrc.py` | 메서드 추출용 가벼운 Java 스캐너 |
| `scan.txt` | `scan` 결과 (`iteration 수\|판정\|경로`), git에서 제외 |

GitHub Actions/Pages 연동은 repo 루트의 `SETUP.md`와 `.github/workflows/refinement-pages.yml`을 참고하세요.

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `NoClassDefFoundError: javafx/util/Pair` | JavaFX가 없는 JDK 사용 중. `source ~/.local/jdk8/ardiff-env.sh` 확인 |
| `no libz3java in java.library.path` | `LD_LIBRARY_PATH` 미설정. 위와 동일하게 env 파일을 source |
| `NoClassDefFoundError: org/apache/commons/...` | `-jar` 대신 `-cp "classes:target/artifacts/Implementation_jar/*"`로 실행해야 함 (스크립트는 이미 그렇게 함) |
| `GradDiff.java no longer matches the snapshot patch` | ARDiff 소스가 바뀌어 패치 위치를 못 찾음. `setup_debug_classes`의 패치 부분 수정 필요 |
| 판정이 `TIMEOUT/ERROR` | `TIMEOUT`을 늘리거나 `bench/<예제>/debug.log` 확인 |
| 결과가 `UNKNOWN` | 정상일 수 있음 (ARDiff가 결론을 못 낸 경우). `--b`(loop bound)나 `HEAP` 조정 |

## 참고

- 같은 예제를 다시 `run`하면 이전 결과(`instrumented/`, `outputs/`, `z3models/`, `iterations/`, `debug.log`)는 지워집니다.
- `TOOL_ARGS`의 `--H`를 바꾸면 `outputs/` 파일 이름이 `ARDiff<H>.txt`로 바뀝니다. `--tool D`/`I`(DSE, IMP-S)는 refinement가 없으므로 `iterations/`가 생기지 않고 뷰어에도 나오지 않습니다.
- 논문: *ARDiff: Scaling Program Equivalence Checking via Iterative Abstraction and Refinement of Common Code* (ESEC/FSE 2020)
