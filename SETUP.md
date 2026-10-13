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

- **자동**: `examples/`, `refinement/`, workflow 파일이 바뀐 커밋을 main(또는 master)에 push하면 실행
- **수동**: **Actions → ARDiff refinement viewer → Run workflow**
  - `benchmarks`: 공백으로 구분한 예제 목록 (예: `Ran/ran/NEq Bess/bessk/NEq examples`). 비우면 기본 5개 + `examples/` 전체
  - `tool_args`: ARDiff 옵션 (기본 `--tool A --H H123`)

실행이 끝나면 결과는 다음 위치에 있습니다. (Actions에서 아직 실제로 돌려보지 않아 소요 시간은 확인 전)

| 위치 | 내용 |
|---|---|
| `https://<계정>.github.io/ARDiff/` | interactive 뷰어 |
| `https://<계정>.github.io/ARDiff/runs/summary.txt` | 예제별 iteration 수와 판정 |
| `https://<계정>.github.io/ARDiff/runs/<예제>/debug.log` | 예제별 전체 로그 |
| Actions 실행 화면의 Summary | 같은 판정 표 |

## 4. 새 입력 넣기

`examples/<이름>/oldV.java`, `examples/<이름>/newV.java`를 추가하고 push. 입력 규칙은 `examples/README.md` 참고.

## 러너 환경 메모

- `ubuntu-24.04` 러너 (public repo 기준 4 vCPU / 16GB). 코어 전체를 쓰고 예제 2개씩 병렬, JVM 힙 5GB
- JDK는 `actions/setup-java`의 Zulu 8 `jdk+fx`(JavaFX 포함)를 사용
- 예제 하나의 제한 시간 600초, job 전체 120분. 무거운 예제는 `UNKNOWN`이나 `TIMEOUT/ERROR`가 나올 수 있음
- 실패한 예제가 있어도 나머지로 뷰어를 만듦. 하나도 성공하지 못하면 job이 실패함
