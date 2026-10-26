#!/usr/bin/env bats
# Unit tests for cloudflare-rag-eplan-p8/migration/scripts/02_deploy_to_cloudflare.sh

setup() {
  bats_load_library bats-support
  bats_load_library bats-assert
  load test_helper/fake_npx

  SCRIPT="$BATS_TEST_DIRNAME/../cloudflare-rag-eplan-p8/migration/scripts/02_deploy_to_cloudflare.sh"
  WORK="$BATS_TEST_TMPDIR/output"
  mkdir -p "$WORK"
  setup_fake_npx
  cd "$WORK"
}

@test "runs login, create, per-batch insert, deploy and whoami in order" {
  touch vectors_batch_001.ndjson vectors_batch_002.ndjson
  run bash "$SCRIPT"
  assert_success
  run npx_calls
  assert_output "wrangler login
wrangler vectorize create eplan-knowledge-base --dimensions=768 --metric=cosine
wrangler vectorize insert eplan-knowledge-base --file=vectors_batch_001.ndjson --batch-size=1000
wrangler vectorize insert eplan-knowledge-base --file=vectors_batch_002.ndjson --batch-size=1000
wrangler deploy
wrangler whoami"
}

@test "deploys from the current directory" {
  run bash "$SCRIPT"
  assert_success
  run grep -F "|wrangler deploy" "$NPX_LOG"
  assert_output "$WORK|wrangler deploy"
}

@test "uses the URL reported by whoami in the test commands" {
  export NPX_WHOAMI_OUT="Worker at https://eplan-rag-mcp.acme.workers.dev ready"
  run bash "$SCRIPT"
  assert_success
  assert_line "  curl https://eplan-rag-mcp.acme.workers.dev/health"
  assert_line "  curl https://eplan-rag-mcp.acme.workers.dev/stats"
  assert_output --partial "curl -X POST https://eplan-rag-mcp.acme.workers.dev/search"
}

@test "falls back to the placeholder URL when whoami shows no URL" {
  export NPX_WHOAMI_OUT="You are logged in as someone"
  run bash "$SCRIPT"
  assert_success
  assert_line "  curl https://eplan-rag-mcp.<YOUR_SUBDOMAIN>.workers.dev/health"
  assert_line "DEPLOYMENT COMPLETE"
}

@test "falls back to the placeholder URL when whoami fails" {
  export NPX_FAIL_ON="whoami"
  run bash "$SCRIPT"
  assert_success
  assert_line "  curl https://eplan-rag-mcp.<YOUR_SUBDOMAIN>.workers.dev/stats"
  refute_output --partial "fake npx"
}

@test "continues when the index already exists" {
  export NPX_FAIL_ON="vectorize create"
  touch vectors_batch_001.ndjson
  run bash "$SCRIPT"
  assert_success
  assert_line "Index may already exist, continuing..."
  run grep -F "vectorize insert" "$NPX_LOG"
  assert_success
}

@test "aborts when the login fails" {
  export NPX_FAIL_ON="login"
  run bash "$SCRIPT"
  assert_failure
  run npx_calls
  assert_output "wrangler login"
}

@test "aborts before deploying when a batch insert fails" {
  export NPX_FAIL_ON="--file=vectors_batch_002.ndjson"
  touch vectors_batch_001.ndjson vectors_batch_002.ndjson vectors_batch_003.ndjson
  run bash "$SCRIPT"
  assert_failure
  assert_line "  Done: vectors_batch_001.ndjson"
  refute_output --partial "Done: vectors_batch_002.ndjson"
  run grep -F "vectors_batch_003" "$NPX_LOG"
  assert_failure
  run grep -F "wrangler deploy" "$NPX_LOG"
  assert_failure
}

@test "without batch files the unexpanded glob is passed to wrangler and aborts the run" {
  # Unlike the EEC Pro script there is no [ -f ] guard, so the literal pattern
  # reaches `vectorize insert`, which fails on the missing file under set -e.
  export NPX_CHECK_FILES=1
  run bash "$SCRIPT"
  assert_failure
  assert_line "  Importing: vectors_batch_*.ndjson"
  run grep -F "wrangler deploy" "$NPX_LOG"
  assert_failure
}
