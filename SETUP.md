# GitHub Pages로 ARDiff refinement 뷰어 배포하기

push하거나 Actions 화면에서 실행하면 GitHub Actions가 ARDiff를 돌리고, 결과 뷰어를 GitHub Pages에 올립니다.

```
.github/workflows/refinement-pages.yml   Actions workflow
refinement/                              실행·렌더링 스크립트 (README.md 참고)
examples/                                직접 넣는 입력 쌍 (oldV.java / newV.java)
```

## 1. fork 준비

1. GitHub에서 https://github.com/resess/ARDiff 를 본인 계정으로 **Fork** (public 권장, private에서 Pages를 쓰려면 유료 플랜 필요)
2. fork를 clone하고 이 폴더의 파일을 repo 루트에 복사

```bash
git clone https://github.com/<계정>/ARDiff.git ardiff-fork
cp -r ~/ardiff-pages/.github ~/ardiff-pages/refinement ~/ardiff-pages/examples ~/ardiff-pages/SETUP.md ardiff-fork/
cd ardiff-fork
git add .github refinement examples SETUP.md
git commit -m "Add refinement viewer workflow"
git push
```

## 2. Pages 켜기

repo의 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 선택.

## 3. 실행

workflow 이름: **ARDiff commit check**. 기본은 **벤치마크 모드**: push할 때마다 `examples/same-old` 아래 oldV/newV 쌍(10개)을 비교하고,
메인 페이지에 Software Regression Visualization(`unified_report.py`)을 올립니다. 수동 실행(Run workflow)에서 `pairs_root`를 `benchmarks`로 바꾸면 원래 벤치마크를,
`limit`으로 개수(기본 `0` = 전부)를 정합니다. `pairs`는 커밋에서 바뀐 폴더만, `methods`는 커밋 이전/이후의 바뀐 메서드를 비교합니다.
NOT EQUIVALENT면 어떤 입력에서 결과가 달라지는지 보여 주는 보고서를 Pages에 올립니다.

- **자동**: `.java` 파일이나 `refinement/`, workflow 파일이 바뀐 커밋을 main에 push하면 실행.
  `examples/same-old` 아래 oldV/newV 쌍을 검사 (methods/pairs 모드를 수동으로 고르면 그 push의 커밋 범위 `before..after` 기준).
- **수동**: **Actions → ARDiff commit check → Run workflow**
  - `target_repo`: 검사할 다른 저장소의 git URL (public). 비우면 이 저장소
  - `commit`: 검사할 커밋 (부모 커밋과 비교, 기본 HEAD)
  - `range`: `BASE..HEAD` 범위 (있으면 commit보다 우선)
  - `only`: 메서드 이름 정규식

| 위치 | 내용 |
|---|---|
| `https://<계정>.github.io/ARDiff/` | Software Regression Visualization (변경별 역할, 근거, 실행 흐름, refinement) |
| `https://<계정>.github.io/ARDiff/report.html` | 메서드별 보고서 (판정, diff, 실행 흐름) |
| `https://<계정>.github.io/ARDiff/viewers/<쌍>.html` | 쌍별 refinement 과정 뷰어 (보고서에서 링크) |
| `https://<계정>.github.io/ARDiff/report.md`, `report.json` | 같은 내용의 Markdown / JSON |
| `https://<계정>.github.io/ARDiff/pairs/<메서드>/` | ARDiff 입력(oldV/newV.java)과 debug.log |
| Actions 실행 화면의 Summary | report.md 내용 |

NOT EQUIVALENT가 나와도 job은 성공으로 끝납니다 (판정 결과일 뿐 오류가 아니므로).
벤치마크 refinement 뷰어만 만들려면 로컬에서 `refinement/ardiff-workflow.sh all`을 쓰세요.

## 러너 환경 메모

- `ubuntu-24.04` 러너 (public repo 기준 4 vCPU / 16GB). 코어 전체를 쓰고 예제 2개씩 병렬, JVM 힙 5GB
- JDK는 `actions/setup-java`의 Zulu 8 `jdk+fx`(JavaFX 포함)를 사용
- 예제 하나의 제한 시간 600초, job 전체 120분. 무거운 예제는 `UNKNOWN`이나 `TIMEOUT/ERROR`가 나올 수 있음
- 실패한 예제가 있어도 나머지로 뷰어를 만듦. 하나도 성공하지 못하면 job이 실패함

## 플레이그라운드와 ARDiff-lite

`https://<계정>.github.io/ARDiff/playground.html` 에서 old/new 코드를 고치면 오른쪽 분석이 바로 바뀝니다.

- **변경별 역할, 실행 흐름**: 브라우저 안의 인터프리터로 old/new를 직접 실행해서 계산 (`refinement/playground/engine.js`)
- **ARDiff-lite**: ARDiff의 추상화-refinement 루프를 브라우저에서 다시 구현한 것 (`ardifflite.js`). 공통 문장을 UF로 추상화하고,
  z3(WebAssembly)로 old와 new의 결과가 다를 수 있는지 묻고, 반례가 나오면 원래 코드로 실행해서 진짜인지 확인하고, 가짜면 문장 하나를
  구체화해서 반복합니다. 원래 ARDiff가 아니라 재구현이므로 판정이 다를 수 있습니다
- z3 WebAssembly는 페이지가 cross-origin isolated여야 해서, Pages에 `coi-serviceworker`를 함께 올립니다 (처음 열면 한 번 새로고침됨)
- **Run ARDiff on GitHub**: 진짜 ARDiff는 이슈를 통해 GitHub Actions에서 돌립니다 (`ardiff-issue.yml`, 저장소 Settings에서 Issues를 켜야 함)
