#!/bin/bash
# ARDiff workflow: setup -> run examples (debug + per-iteration snapshots) -> render interactive HTML viewer.
#
# usage:
#   ardiff-workflow.sh setup                    JDK 8 (Zulu FX), ~/.jpf, benchmark copy, debug classes
#   ardiff-workflow.sh run    [bench...]        run ARDiff in debug mode (default: $DEFAULT_BENCH)
#   ardiff-workflow.sh render [bench...]        build $OUT_HTML from runs already done
#   ardiff-workflow.sh scan                     run all benchmarks once, rank by iteration count -> scan.txt
#   ardiff-workflow.sh all    [bench...]        setup + run + render
#   ardiff-workflow.sh rundir DIR...            run on arbitrary dirs holding oldV.java/newV.java (absolute or relative paths)
#   ardiff-workflow.sh commit [options]         EQ/NEQ check of methods changed by a commit (commitcheck/commit_check.py --help)
#
# bench names are relative to $WORK/bench, e.g. Ran/ran/NEq.  "--top N" picks the N with most iterations from scan.txt.
# "examples" = every pair under $EXAMPLES_DIR (copied to bench/examples/). No bench args = defaults + examples.
# env: ARDIFF_REPO, WORK, EXAMPLES_DIR, ARDIFF_JAVA_HOME, CORES (taskset list), JOBS, TIMEOUT (s), HEAP, TOOL_ARGS, OUT_HTML
set -euo pipefail

WORK=${WORK:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
if [ -z "${ARDIFF_REPO:-}" ]; then
  if [ -d "$WORK/../Implementation" ]; then ARDIFF_REPO=$(cd "$WORK/.." && pwd); else ARDIFF_REPO=$HOME/workspace/ARDiff; fi
fi
EXAMPLES_DIR=${EXAMPLES_DIR:-$ARDIFF_REPO/examples}
CORES=${CORES:-120-159}
JOBS=${JOBS:-4}
TIMEOUT=${TIMEOUT:-300}
HEAP=${HEAP:-8G}
TOOL_ARGS=${TOOL_ARGS:---tool A --H H123}
OUT_HTML=${OUT_HTML:-$WORK/refinement-viewer.html}
JDK_ROOT=$HOME/.local/jdk8
ENV_FILE=$JDK_ROOT/ardiff-env.sh
IMPL=$ARDIFF_REPO/Implementation
DEFAULT_BENCH=(Ran/ran/NEq Bess/bessj1/Eq ModDiff/Eq/Comp tsafe/conflict/Eq Bess/bessj0/Eq)

log() { printf '\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
pin() { taskset -c "$CORES" "$@"; }
load_env() { [ -f "$ENV_FILE" ] || die "run '$0 setup' first"; source "$ENV_FILE"; }

# ---------------------------------------------------------------- setup
setup_jdk() {
  local jdk=""
  if [ -n "${ARDIFF_JAVA_HOME:-}" ]; then
    [ -f "$ARDIFF_JAVA_HOME/jre/lib/ext/jfxrt.jar" ] || die "ARDIFF_JAVA_HOME has no JavaFX (jre/lib/ext/jfxrt.jar)"
    jdk=$ARDIFF_JAVA_HOME
  else
    jdk=$(ls -d "$JDK_ROOT"/zulu8*-fx-jdk* 2>/dev/null | head -1 || true)
  fi
  if [ -z "$jdk" ]; then
    log "downloading Azul Zulu 8 JDK with JavaFX (ARDiff needs javafx.util.Pair)"
    local url
    url=$(curl -fsS "https://api.azul.com/metadata/v1/zulu/packages/?java_version=8&os=linux&arch=x64&archive_type=tar.gz&java_package_type=jdk&javafx_bundled=true&latest=true&release_status=ga&availability_types=CA" \
          | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["download_url"])')
    mkdir -p "$JDK_ROOT"
    pin curl -fSL --retry 3 -o "$JDK_ROOT/zulu.tgz" "$url"
    pin tar xzf "$JDK_ROOT/zulu.tgz" -C "$JDK_ROOT" && rm "$JDK_ROOT/zulu.tgz"
    jdk=$(ls -d "$JDK_ROOT"/zulu8*-fx-jdk* | head -1)
  else
    log "JDK present: $jdk"
  fi
  mkdir -p "$(dirname "$ENV_FILE")"
  cat > "$ENV_FILE" <<EOF
# source $ENV_FILE
export JAVA_HOME=$jdk
export PATH=\$JAVA_HOME/bin:\$PATH
export LD_LIBRARY_PATH=$IMPL/jpf-git/jpf-symbc/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}
EOF
  source "$ENV_FILE"
  java -version 2>&1 | head -1 >&2
}

setup_jpf() {
  local want; want=$(printf 'jpf-core = %s\njpf-symbc = %s\nextensions = ${jpf-core},${jpf-symbc}\n' \
    "$IMPL/jpf-git/jpf-core" "$IMPL/jpf-git/jpf-symbc")
  mkdir -p "$HOME/.jpf"
  if [ -f "$HOME/.jpf/site.properties" ] && [ "$(cat "$HOME/.jpf/site.properties")" != "$want" ]; then
    cp "$HOME/.jpf/site.properties" "$HOME/.jpf/site.properties.bak.$(date +%s)"
    log "backed up existing ~/.jpf/site.properties"
  fi
  printf '%s\n' "$want" > "$HOME/.jpf/site.properties"
  log "~/.jpf/site.properties -> $IMPL/jpf-git"
}

setup_bench() {
  if [ -d "$WORK/bench" ]; then
    log "benchmark copy present: $WORK/bench"
  else
    log "copying benchmarks to $WORK/bench (runs write outputs there, repo stays clean)"
    mkdir -p "$WORK/bench"
    (cd "$ARDIFF_REPO/benchmarks" && find . -name '*.java' -not -path '*/instrumented/*' -exec cp --parents {} "$WORK/bench/" \;)
  fi
  sync_examples
}

sync_examples() {  # copy $EXAMPLES_DIR/<name>/{oldV,newV}.java to bench/examples/<name>
  [ -d "$EXAMPLES_DIR" ] || return 0
  local n=0 d
  for d in "$EXAMPLES_DIR"/*/; do
    [ -f "$d/oldV.java" ] && [ -f "$d/newV.java" ] || continue
    mkdir -p "$WORK/bench/examples/$(basename "$d")"
    cp "$d/oldV.java" "$d/newV.java" "$WORK/bench/examples/$(basename "$d")/"
    n=$((n + 1))
  done
  log "examples: $n pair(s) from $EXAMPLES_DIR"
}

list_examples() { [ -d "$WORK/bench/examples" ] && (cd "$WORK/bench" && ls -d examples/*/ 2>/dev/null | sed 's|/$||') || true; }
table() { if command -v column >/dev/null; then column -t -s'|'; else tr '|' '\t'; fi; }

setup_debug_classes() {
  log "building debug classes (DSE.debug=true, GradDiff per-iteration snapshots)"
  mkdir -p "$WORK/src" "$WORK/classes"
  cp "$IMPL/src/main/java/DSE/DSE.java" "$IMPL/src/main/java/GradDiff/GradDiff.java" "$WORK/src/"
  sed -i 's/protected boolean debug = false;/protected boolean debug = true;/' "$WORK/src/DSE.java"
  grep -q 'protected boolean debug = true;' "$WORK/src/DSE.java" || die "DSE.java debug patch failed"
  python3 - "$WORK/src/GradDiff.java" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = """               summary = runEquivalenceChecking();
               finalRes = equivalenceResult(summary);
               result += finalRes;"""
new = """               summary = runEquivalenceChecking();
               File snap = snapshotIteration(outputs, index, summary);
               finalRes = equivalenceResult(summary);
               result += finalRes;
               snapshotAfterRefine(outputs, snap, finalRes);"""
anchor = "\n    public String updateUserOutput(String finalResult){"
helper = '''
    /** [debug patch] copy instrumented/ and the Z3 summary of this iteration to iterations/iter_N */
    private File snapshotIteration(String outputs, int index, SMTSummary summary) throws IOException {
        File src = new File(outputs + "instrumented");
        File dst = new File(outputs + "iterations/iter_" + String.format("%02d", index));
        copyDir(src, dst);
        BufferedWriter bw = new BufferedWriter(new FileWriter(new File(dst, "z3summary.txt")));
        bw.write(summary.toWrite == null ? "" : summary.toWrite);
        bw.close();
        return dst;
    }

    /** [debug patch] after the result/refinement step: save the result text and the H1 query of this iteration */
    private void snapshotAfterRefine(String outputs, File dst, String res) throws IOException {
        BufferedWriter bw = new BufferedWriter(new FileWriter(new File(dst, "result.txt")));
        bw.write(res);
        bw.close();
        File h1 = new File(outputs + "instrumented/H1Checking.smt2");
        if (h1.exists())
            java.nio.file.Files.copy(h1.toPath(), new File(dst, "H1Checking.smt2").toPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING);
    }

    private static void copyDir(File src, File dst) throws IOException {
        dst.mkdirs();
        File[] files = src.listFiles();
        if (files == null) return;
        for (File f : files) {
            File t = new File(dst, f.getName());
            if (f.isDirectory()) copyDir(f, t);
            else java.nio.file.Files.copy(f.toPath(), t.toPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
    }
'''
if s.count(old) != 1 or s.count(anchor) != 1:
    sys.exit("GradDiff.java no longer matches the snapshot patch; update setup_debug_classes")
s = s.replace(old, new).replace(anchor, helper + anchor, 1)
open(p, "w").write(s)
PY
  rm -rf "$WORK/classes"/*
  (cd "$IMPL" && pin javac -nowarn -cp "target/artifacts/Implementation_jar/*" -d "$WORK/classes" \
      "$WORK/src/DSE.java" "$WORK/src/GradDiff.java" 2>&1 | grep -v '^Note:' >&2 || true)
  [ -f "$WORK/classes/GradDiff/GradDiff.class" ] && [ -f "$WORK/classes/DSE/DSE.class" ] || die "javac failed"
}

smoke_test() {
  log "smoke test: Airy/MAX/Eq"
  run_one Airy/MAX/Eq >/dev/null
  grep -q "Output : EQUIVALENT" "$WORK/bench/Airy/MAX/Eq/debug.log" || die "smoke test failed, see $WORK/bench/Airy/MAX/Eq/debug.log"
  log "smoke test ok"
}

cmd_setup() {
  [ -f "$IMPL/target/artifacts/Implementation_jar/Implementation.jar" ] || die "ARDiff not found at $ARDIFF_REPO"
  command -v taskset >/dev/null || die "taskset missing"
  setup_jdk; setup_jpf; setup_bench; setup_debug_classes; smoke_test
}

# ---------------------------------------------------------------- run
run_one() {  # bench name relative to $WORK/bench, or an absolute dir; prints "name|iterations|verdict"
  load_env
  local d="$WORK/bench/$1"
  case "$1" in /*) d=$1 ;; esac
  [ -f "$d/oldV.java" ] || die "no oldV.java in $d"
  rm -rf "$d/instrumented" "$d/outputs" "$d/z3models" "$d/iterations"
  (cd "$IMPL" && timeout "$TIMEOUT" taskset -c "$CORES" java -Djava.library.path=jpf-git/jpf-symbc/lib -Xmx"$HEAP" \
      -cp "$WORK/classes:target/artifacts/Implementation_jar/*" Runner.Runner \
      --path1 "$d/oldV.java" --path2 "$d/newV.java" $TOOL_ARGS > "$d/debug.log" 2>&1) || true
  local n v
  n=$(ls "$d/iterations" 2>/dev/null | wc -l)
  v=$(grep -o "Output : [A-Z ]*" "$d/debug.log" | tail -1 | sed 's/Output : //; s/ *$//')
  echo "$1|$n|${v:-TIMEOUT/ERROR}"
}

resolve_bench() {  # args -> bench list on stdout
  if [ $# -eq 0 ]; then printf '%s\n' "${DEFAULT_BENCH[@]}"; list_examples; return; fi
  if [ "$1" = "--top" ]; then
    [ -f "$WORK/scan.txt" ] || die "no scan.txt; run '$0 scan' first"
    sort -t'|' -k1 -nr "$WORK/scan.txt" | head -"${2:-5}" | cut -d'|' -f3 | sed "s|^$WORK/bench/||"
    return
  fi
  local b
  for b in "$@"; do if [ "$b" = examples ]; then list_examples; else echo "$b"; fi; done
}

cmd_run() {
  load_env
  sync_examples
  mapfile -t list < <(resolve_bench "$@")
  [ ${#list[@]} -gt 0 ] || die "no benchmarks selected"
  log "running ${#list[@]} benchmark(s), $JOBS in parallel on cores $CORES: $TOOL_ARGS"
  printf '%s\n' "${list[@]}" | xargs -P "$JOBS" -I{} "$0" _one {} | table
}

cmd_scan() {
  load_env
  log "scanning all benchmarks (original jar, timeout 120s, $JOBS parallel)"
  find "$WORK/bench" -name oldV.java -not -path '*/instrumented/*' -not -path '*/iterations/*' -printf '%h\n' | sort \
    | xargs -P "$JOBS" -I{} "$0" _scan {} > "$WORK/scan.txt"
  log "top 10 by iteration count (full list: $WORK/scan.txt)"
  sort -t'|' -k1 -nr "$WORK/scan.txt" | head -10 | sed "s|$WORK/bench/||" | table
}

scan_one() {
  load_env
  local d=$1
  (cd "$IMPL" && timeout 120 taskset -c "$CORES" java -Djava.library.path=jpf-git/jpf-symbc/lib -Xmx"$HEAP" \
     -jar target/artifacts/Implementation_jar/Implementation.jar --path1 "$d/oldV.java" --path2 "$d/newV.java" $TOOL_ARGS \
     > "$d/scan.log" 2>&1) || true
  local n r
  n=$(grep -c "Iteration" "$d"/outputs/ARDiff*.txt 2>/dev/null | head -1 | cut -d: -f2 || true)
  r=$(grep "^Output" "$d/scan.log" | tail -1 || true)
  echo "${n:-0}|$r|$d"
}

# ---------------------------------------------------------------- render
cmd_render() {
  mapfile -t list < <(resolve_bench "$@")
  local dirs=()
  for b in "${list[@]}"; do
    if [ -d "$WORK/bench/$b/iterations" ]; then dirs+=("$WORK/bench/$b"); else log "skip $b (not run yet)"; fi
  done
  [ ${#dirs[@]} -gt 0 ] || die "nothing to render; run '$0 run' first"
  python3 "$WORK/build_viewer.py" "$OUT_HTML" "${dirs[@]}" >&2
  log "wrote $OUT_HTML ($(du -h "$OUT_HTML" | cut -f1))"
}

# ---------------------------------------------------------------- main
case "${1:-}" in
  setup)  cmd_setup ;;
  run)    shift; cmd_run "$@" ;;
  render) shift; cmd_render "$@" ;;
  scan)   cmd_scan ;;
  all)    shift; cmd_setup; cmd_run "$@"; cmd_render "$@" ;;
  rundir) shift; load_env
          [ $# -gt 0 ] || die "rundir needs at least one directory"
          for x in "$@"; do realpath "$x"; done | xargs -P "$JOBS" -I{} "$0" _one {} | table ;;
  commit) shift; exec python3 "$WORK/commitcheck/commit_check.py" "$@" ;;
  _one)   run_one "$2" ;;
  _scan)  scan_one "$2" ;;
  *)      sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
