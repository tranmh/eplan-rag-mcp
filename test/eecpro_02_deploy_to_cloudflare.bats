#!/usr/bin/env bats
# Unit tests for cloudflare-rag-eecpro/migration/scripts/02_deploy_to_cloudflare.sh

setup() {
  bats_load_library bats-support
  bats_load_library bats-assert
  load test_helper/fake_npx

  SCRIPT="$BATS_TEST_DIRNAME/../cloudflare-rag-eecpro/migration/scripts/02_deploy_to_cloudflare.sh"
  PROJ="$BATS_TEST_TMPDIR/proj"
  mkdir -p "$PROJ/migration" "$PROJ/worker"
  setup_fake_npx
  cd "$PROJ/migration"
}

@test "runs login, create, per-batch insert and deploy in order" {
  touch vectors_batch_001.ndjson vectors_batch_002.ndjson
  run bash "$SCRIPT"
  assert_success
  run npx_calls
  assert_output "wrangler login
wrangler vectorize create eecpro-knowledge-base --dimensions=768 --metric=cosine
wrangler vectorize insert eecpro-knowledge-base --file=vectors_batch_001.ndjson --batch-size=1000
wrangler vectorize insert eecpro-knowledge-base --file=vectors_batch_002.ndjson --batch-size=1000
wrangler deploy"
}

@test "inserts batches from the migration directory and deploys from ../worker" {
  touch vectors_batch_001.ndjson
  run bash "$SCRIPT"
  assert_success
  run grep -F "|wrangler vectorize insert" "$NPX_LOG"
  assert_output --partial "$PROJ/migration|"
  run grep -F "|wrangler deploy" "$NPX_LOG"
  assert_output "$PROJ/worker|wrangler deploy"
}

@test "prints progress per batch and the completion banner" {
  touch vectors_batch_001.ndjson
  run bash "$SCRIPT"
  assert_success
  assert_line "  Importing: vectors_batch_001.ndjson"
  assert_line "  Done: vectors_batch_001.ndjson"
  assert_line "DEPLOYMENT COMPLETE"
  assert_output --partial "curl https://rageecpro.covaga.xyz/health"
  assert_output --partial "npx wrangler secret put WORKER_API_KEY"
}

@test "skips the import step when there are no batch files" {
  run bash "$SCRIPT"
  assert_success
  refute_output --partial "Importing:"
  run grep -F "vectorize insert" "$NPX_LOG"
  assert_failure
  run grep -F "|wrangler deploy" "$NPX_LOG"
  assert_success
}

@test "ignores files that do not match the batch pattern" {
  touch vectors_batch_001.ndjson other.ndjson vectors_batch_002.json
  run bash "$SCRIPT"
  assert_success
  run grep -cF "vectorize insert" "$NPX_LOG"
  assert_output "1"
}

@test "continues when the index already exists" {
  export NPX_FAIL_ON="vectorize create"
  touch vectors_batch_001.ndjson
  run bash "$SCRIPT"
  assert_success
  assert_line "Index may already exist, continuing..."
  assert_line "DEPLOYMENT COMPLETE"
  run grep -F "vectorize insert" "$NPX_LOG"
  assert_success
}

@test "aborts when the login fails" {
  export NPX_FAIL_ON="login"
  run bash "$SCRIPT"
  assert_failure
  refute_output --partial "STEP 2"
  run npx_calls
  assert_output "wrangler login"
}

@test "aborts before deploying when a batch insert fails" {
  export NPX_FAIL_ON="--file=vectors_batch_001.ndjson"
  touch vectors_batch_001.ndjson vectors_batch_002.ndjson
  run bash "$SCRIPT"
  assert_failure
  refute_output --partial "Done: vectors_batch_001.ndjson"
  refute_output --partial "DEPLOYMENT COMPLETE"
  run grep -F "vectors_batch_002" "$NPX_LOG"
  assert_failure
  run grep -F "wrangler deploy" "$NPX_LOG"
  assert_failure
}

@test "aborts when the deploy fails" {
  export NPX_FAIL_ON="deploy"
  run bash "$SCRIPT"
  assert_failure
  refute_output --partial "STEP 5"
}

@test "fails when there is no sibling worker directory" {
  rmdir "$PROJ/worker"
  run bash "$SCRIPT"
  assert_failure
  run grep -F "wrangler deploy" "$NPX_LOG"
  assert_failure
}
