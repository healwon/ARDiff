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

workflow 이름: **ARDiff commit check**. 기본은 **벤치마크 모드**: push할 때마다 `benchmarks/` 아래 `oldV.java`와 `newV.java`가 있는
폴더 142개 중 **10개**를 목록 전체에 고르게 골라 oldV와 newV를 비교합니다 (매번 같은 10개). 수동 실행(Run workflow)의 `mode`도 기본이 `all`이고, `limit`으로 개수를 정합니다 (기본 10, `0`이면 142개 전부: 수 시간 걸릴 수 있음, 쌍당 제한 300초). `pairs`는 커밋에서 바뀐 폴더만, `methods`는 커밋 이전/이후의 바뀐 메서드를 비교합니다. 커밋에서 바뀐 Java 메서드마다 ARDiff로 EQUIVALENT / NOT EQUIVALENT를 판정하고,
NOT EQUIVALENT면 어떤 입력에서 결과가 달라지는지 보여 주는 보고서를 Pages에 올립니다.

- **자동**: `.java` 파일이나 `refinement/`, workflow 파일이 바뀐 커밋을 main, master, docs에 push하면 실행.
  `benchmarks/` 아래 oldV/newV 쌍 10개를 검사 (methods/pairs 모드를 수동으로 고르면 그 push의 커밋 범위 `before..after` 기준). docs에서 배포하려면 **Settings → Environments → github-pages → Deployment branches and tags**에 `docs` 추가
- **수동**: **Actions → ARDiff commit check → Run workflow**
  - `target_repo`: 검사할 다른 저장소의 git URL (public). 비우면 이 저장소
  - `commit`: 검사할 커밋 (부모 커밋과 비교, 기본 HEAD)
  - `range`: `BASE..HEAD` 범위 (있으면 commit보다 우선)
  - `only`: 메서드 이름 정규식

| 위치 | 내용 |
|---|---|
| `https://<계정>.github.io/ARDiff/` | 커밋 검사 보고서 (메서드별 판정, diff, NEQ 의미 차이) |
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
