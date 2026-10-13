#!/bin/bash
# usage: iterdiff.sh <fileA> <fileB> [difft options]
# Diff two ARDiff iteration files, ignoring UF renumbering (UF_x_1 vs UF_x_2 -> UF_x).
a=$1; b=$2; shift 2
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
mkdir -p "$t/a" "$t/b"
ext=".${a##*.}"
perl -pe 's/\b(UF_\w+)_\d+\b/$1/g' "$a" > "$t/a/$(basename "$(dirname "$a")")$ext"
perl -pe 's/\b(UF_\w+)_\d+\b/$1/g' "$b" > "$t/b/$(basename "$(dirname "$b")")$ext"
difft "$@" "$t/a/"* "$t/b/"*
