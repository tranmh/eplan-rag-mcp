# Shared helpers for the deploy script tests: a fake `npx` on PATH that logs
# every call as "<cwd>|<args>" to $NPX_LOG instead of reaching Cloudflare.
#
# Knobs (environment variables read by the fake):
#   NPX_FAIL_ON      substring; a call whose args contain it exits 1
#   NPX_WHOAMI_OUT   text printed for `npx wrangler whoami`
#   NPX_CHECK_FILES  when set, `vectorize insert --file=X` fails if X is missing

setup_fake_npx() {
  FAKE_BIN="$BATS_TEST_TMPDIR/bin"
  NPX_LOG="$BATS_TEST_TMPDIR/npx.log"
  export NPX_LOG
  mkdir -p "$FAKE_BIN"
  : > "$NPX_LOG"
  cat > "$FAKE_BIN/npx" <<'EOF'
#!/bin/bash
echo "$PWD|$*" >> "$NPX_LOG"
if [ -n "$NPX_FAIL_ON" ] && [[ "$*" == *"$NPX_FAIL_ON"* ]]; then
  echo "fake npx: failing on '$NPX_FAIL_ON'" >&2
  exit 1
fi
if [ "$1 $2" = "wrangler whoami" ]; then
  printf '%s\n' "$NPX_WHOAMI_OUT"
  exit 0
fi
if [ -n "$NPX_CHECK_FILES" ] && [ "$2 $3" = "vectorize insert" ]; then
  for arg in "$@"; do
    case "$arg" in
      --file=*)
        f="${arg#--file=}"
        if [ ! -f "$f" ]; then
          echo "fake npx: no such file $f" >&2
          exit 1
        fi
        ;;
    esac
  done
fi
exit 0
EOF
  chmod +x "$FAKE_BIN/npx"
  PATH="$FAKE_BIN:$PATH"
  export PATH
}

# Prints the logged npx arguments without the working directory prefix.
npx_calls() {
  cut -d'|' -f2- "$NPX_LOG"
}
