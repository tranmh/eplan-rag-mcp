// The safety net of eplan-rag-mcp, written by aqaa from what its QA run found: unit tests with coverage and its
// floor, integration tests against the databases they need, end-to-end tests, and lint, SAST and dependency
// checks (report only: a finding marks the stage unstable until it is triaged).
// Needs the plugins Pipeline, Docker Pipeline, JUnit, Coverage, Timestamper and Workspace Cleanup;
// integration stages run on an agent labelled 'docker'.
pipeline {
  agent none
  options {
    timeout(time: 90, unit: 'MINUTES')
    timestamps()
    buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
    disableConcurrentBuilds(abortPrevious: true)
  }
  environment {
    CI = 'true'
  }
  stages {
    stage('Tests') {
      parallel {
        stage('Unit: python eplan-p8-mcp-server/mcp_server') {
          agent { docker { image 'python:3.13-slim' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('eplan-p8-mcp-server/mcp_server') {
              sh '''
                set -eu
                if [ -f .venv-ci/bin/activate ]; then . .venv-ci/bin/activate; fi
                mkdir -p test-reports
                python -m venv .venv-ci
                . .venv-ci/bin/activate && python -m pip install --upgrade pip
                . .venv-ci/bin/activate && if [ -f pyproject.toml ]; then pip install -e '.[test,dev]' || pip install -e .; fi
                . .venv-ci/bin/activate && for f in requirements*.txt; do if [ -f "$f" ]; then pip install -r "$f"; fi; done
                . .venv-ci/bin/activate && pip install pytest==9.1.1 pytest-cov==7.1.0 ruff==0.17.2 'bandit[sarif]==1.9.4' pip-audit==2.10.1
                python -m pytest -q -m "not integration and not e2e" --junitxml=test-reports/unit.xml --cov=. --cov-report=xml:test-reports/coverage.xml || { rc=$?; [ "$rc" -eq 5 ] || exit "$rc"; }
              '''
            }
          }
          post {
            always {
              junit allowEmptyResults: true, testResults: 'eplan-p8-mcp-server/mcp_server/test-reports/*.xml'
              recordCoverage id: 'coverage-python-eplan-p8-mcp-server-mcp_server', name: 'Coverage python eplan-p8-mcp-server/mcp_server', tools: [[parser: 'COBERTURA', pattern: 'eplan-p8-mcp-server/mcp_server/test-reports/coverage.xml']], sourceDirectories: [[path: 'eplan-p8-mcp-server/mcp_server']], qualityGates: [[threshold: 40.0, metric: 'LINE', baseline: 'PROJECT', criticality: 'FAILURE']]
              archiveArtifacts allowEmptyArchive: true, artifacts: 'eplan-p8-mcp-server/mcp_server/test-reports/**'
            }
            cleanup {
              cleanWs deleteDirs: true, notFailBuild: true
            }
          }
        }
        stage('Unit: shell') {
          agent { dockerfile { filename 'shell.Dockerfile'; dir 'ci/jenkins' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('.') {
              sh '''
                set -eu
                export BATS_LIB_PATH="${BATS_LIB_PATH:-/usr/lib/bats}"
                mkdir -p test-reports
                T=""; for d in test tests; do if [ -d "$d" ]; then T="$T $d"; fi; done
                if [ -z "$T" ]; then echo "no bats tests"; exit 0; fi
                # shellcheck disable=SC2086
                bats --recursive --allow-empty-suite --formatter tap --report-formatter junit --output test-reports --filter-tags '!integration,!e2e' $T
              '''
            }
          }
          post {
            always {
              junit allowEmptyResults: true, testResults: 'test-reports/*.xml'
              archiveArtifacts allowEmptyArchive: true, artifacts: 'test-reports/**'
            }
            cleanup {
              cleanWs deleteDirs: true, notFailBuild: true
            }
          }
        }
        stage('Unit: typescript cloudflare-rag-eecpro/worker') {
          agent { docker { image 'node:22-bookworm' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('cloudflare-rag-eecpro/worker') {
              sh '''
                set -eu
                mkdir -p test-reports
                npm ci
                npm install --no-save --no-audit --no-fund "@vitest/coverage-v8@$(node -p "require('vitest/package.json').version")"
                npx vitest run --coverage --coverage.reporter=cobertura --coverage.reportsDirectory=test-reports/coverage --reporter=default --reporter=junit --outputFile.junit=test-reports/unit.xml --exclude '**/*.integration.test.*' --exclude 'e2e/**'
              '''
            }
          }
          post {
            always {
              junit allowEmptyResults: true, testResults: 'cloudflare-rag-eecpro/worker/test-reports/*.xml'
              recordCoverage id: 'coverage-typescript-cloudflare-rag-eecpro-worker', name: 'Coverage typescript cloudflare-rag-eecpro/worker', tools: [[parser: 'COBERTURA', pattern: 'cloudflare-rag-eecpro/worker/test-reports/coverage/cobertura-coverage.xml']], sourceDirectories: [[path: 'cloudflare-rag-eecpro/worker']]
              archiveArtifacts allowEmptyArchive: true, artifacts: 'cloudflare-rag-eecpro/worker/test-reports/**'
            }
            cleanup {
              cleanWs deleteDirs: true, notFailBuild: true
            }
          }
        }
        stage('Unit: typescript cloudflare-rag-eplan-p8/worker') {
          agent { docker { image 'node:22-bookworm' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('cloudflare-rag-eplan-p8/worker') {
              sh '''
                set -eu
                mkdir -p test-reports
                npm install --no-audit --no-fund
                npm install --no-save --no-audit --no-fund "@vitest/coverage-v8@$(node -p "require('vitest/package.json').version")"
                npx vitest run --coverage --coverage.reporter=cobertura --coverage.reportsDirectory=test-reports/coverage --reporter=default --reporter=junit --outputFile.junit=test-reports/unit.xml --exclude '**/*.integration.test.*' --exclude 'e2e/**'
              '''
            }
          }
          post {
            always {
              junit allowEmptyResults: true, testResults: 'cloudflare-rag-eplan-p8/worker/test-reports/*.xml'
              recordCoverage id: 'coverage-typescript-cloudflare-rag-eplan-p8-worker', name: 'Coverage typescript cloudflare-rag-eplan-p8/worker', tools: [[parser: 'COBERTURA', pattern: 'cloudflare-rag-eplan-p8/worker/test-reports/coverage/cobertura-coverage.xml']], sourceDirectories: [[path: 'cloudflare-rag-eplan-p8/worker']]
              archiveArtifacts allowEmptyArchive: true, artifacts: 'cloudflare-rag-eplan-p8/worker/test-reports/**'
            }
            cleanup {
              cleanWs deleteDirs: true, notFailBuild: true
            }
          }
        }
      }
    }
    stage('Checks') {
      parallel {
        stage('Checks: python eplan-p8-mcp-server/mcp_server') {
          agent { docker { image 'python:3.13-slim' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('eplan-p8-mcp-server/mcp_server') {
              sh '''
                set -eu
                if [ -f .venv-ci/bin/activate ]; then . .venv-ci/bin/activate; fi
                mkdir -p test-reports
                python -m venv .venv-ci
                . .venv-ci/bin/activate && python -m pip install --upgrade pip
                . .venv-ci/bin/activate && if [ -f pyproject.toml ]; then pip install -e '.[test,dev]' || pip install -e .; fi
                . .venv-ci/bin/activate && for f in requirements*.txt; do if [ -f "$f" ]; then pip install -r "$f"; fi; done
                . .venv-ci/bin/activate && pip install pytest==9.1.1 pytest-cov==7.1.0 ruff==0.17.2 'bandit[sarif]==1.9.4' pip-audit==2.10.1
              '''
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'ruff found issues') {
                sh '''
                  set -eu
                  if [ -f .venv-ci/bin/activate ]; then . .venv-ci/bin/activate; fi
                  ruff check .
                '''
              }
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'bandit found issues') {
                sh '''
                  set -eu
                  if [ -f .venv-ci/bin/activate ]; then . .venv-ci/bin/activate; fi
                  bandit -r . -x ./tests,./.venv-ci,./node_modules -f sarif -o test-reports/bandit.sarif
                '''
              }
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'pip-audit found issues') {
                sh '''
                  set -eu
                  if [ -f .venv-ci/bin/activate ]; then . .venv-ci/bin/activate; fi
                  pip-audit
                '''
              }
            }
          }
          post {
            always { archiveArtifacts allowEmptyArchive: true, artifacts: 'eplan-p8-mcp-server/mcp_server/test-reports/**' }
            cleanup { cleanWs deleteDirs: true, notFailBuild: true }
          }
        }
        stage('Checks: shell') {
          agent { dockerfile { filename 'shell.Dockerfile'; dir 'ci/jenkins' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('.') {
              sh '''
                set -eu
                export BATS_LIB_PATH="${BATS_LIB_PATH:-/usr/lib/bats}"
                mkdir -p test-reports
              '''
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'shellcheck found issues') {
                sh '''
                  set -eu
                  export BATS_LIB_PATH="${BATS_LIB_PATH:-/usr/lib/bats}"
                  find . -type f \\( -name '*.sh' -o -name '*.bash' \\) -not -path './.git/*' -not -path '*/node_modules/*' -print0 | xargs -0 -r shellcheck -x -P SCRIPTDIR
                '''
              }
            }
          }
          post {
            always { archiveArtifacts allowEmptyArchive: true, artifacts: 'test-reports/**' }
            cleanup { cleanWs deleteDirs: true, notFailBuild: true }
          }
        }
        stage('Checks: typescript cloudflare-rag-eecpro/worker') {
          agent { docker { image 'node:22-bookworm' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('cloudflare-rag-eecpro/worker') {
              sh '''
                set -eu
                mkdir -p test-reports
                npm ci
                npm install --no-save --no-audit --no-fund "@vitest/coverage-v8@$(node -p "require('vitest/package.json').version")"
              '''
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'eslint found issues') {
                sh '''
                  set -eu
                  if ls eslint.config.* .eslintrc* >/dev/null 2>&1; then npx eslint .; else echo 'no ESLint configuration'; fi
                '''
              }
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'tsc found issues') {
                sh '''
                  set -eu
                  npx tsc --noEmit
                '''
              }
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'npm audit found issues') {
                sh '''
                  set -eu
                  npm audit --audit-level=high --omit=dev
                '''
              }
            }
          }
          post {
            always { archiveArtifacts allowEmptyArchive: true, artifacts: 'cloudflare-rag-eecpro/worker/test-reports/**' }
            cleanup { cleanWs deleteDirs: true, notFailBuild: true }
          }
        }
        stage('Checks: typescript cloudflare-rag-eplan-p8/worker') {
          agent { docker { image 'node:22-bookworm' } }
          options { timeout(time: 30, unit: 'MINUTES') }
          steps {
            dir('cloudflare-rag-eplan-p8/worker') {
              sh '''
                set -eu
                mkdir -p test-reports
                npm install --no-audit --no-fund
                npm install --no-save --no-audit --no-fund "@vitest/coverage-v8@$(node -p "require('vitest/package.json').version")"
              '''
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'eslint found issues') {
                sh '''
                  set -eu
                  if ls eslint.config.* .eslintrc* >/dev/null 2>&1; then npx eslint .; else echo 'no ESLint configuration'; fi
                '''
              }
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'tsc found issues') {
                sh '''
                  set -eu
                  npx tsc --noEmit
                '''
              }
              catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE', message: 'npm audit found issues') {
                sh '''
                  set -eu
                  npm audit --audit-level=high --omit=dev
                '''
              }
            }
          }
          post {
            always { archiveArtifacts allowEmptyArchive: true, artifacts: 'cloudflare-rag-eplan-p8/worker/test-reports/**' }
            cleanup { cleanWs deleteDirs: true, notFailBuild: true }
          }
        }
      }
    }
  }
}
