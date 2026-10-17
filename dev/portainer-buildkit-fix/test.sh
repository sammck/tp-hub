#!/usr/bin/env bash
#
# Run the Go test suites of the Portainer CE and Portainer Agent forks in the toolchain container (Dockerfile.builder),
# the way their Makefiles do (`make test-server` / `make test`, minus coverage). Tests run in worktrees of your clones
# (see common.sh), so your working checkouts are not touched. See README.md in this directory.
#
# Environment variables (all optional; see also common.sh for SERVER_REPO, AGENT_REPO, CACHE_DIR):
#   REF          Branch/ref/tag to test in both forks (default: build/2.45.2-buildkit-fix). Use REF=2.45.2 for a
#                baseline of the unpatched release, to tell pre-existing failures from new ones.
#   COMPONENTS   "server agent" (default), "server" or "agent"
#   PACKAGES     Go packages to test (default: ./...)
#   DOCKER       1 (default) to give the tests the local Docker daemon (mounts /var/run/docker.sock); some packages
#                (pkg/libstack/compose, edge/stack) deploy real stacks and pull small images. 0 to run without it,
#                in which case those packages fail with "Cannot connect to the Docker daemon".
#
# Writes $CACHE_DIR/logs/test-<component>-<ref>.log and prints a summary of failing packages.
#
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

REF=${REF:-build/2.45.2-buildkit-fix}
COMPONENTS=${COMPONENTS:-server agent}
PACKAGES=${PACKAGES:-./...}
DOCKER=${DOCKER:-1}

ensure_builder
mkdir -p "$LOG_DIR"

run_tests() {
  local subdir=$1 log=$2; shift 2
  local docker_args=()
  if [ "$DOCKER" = 1 ]; then
    docker_args=(-v /var/run/docker.sock:/var/run/docker.sock --group-add "$(stat -c %g /var/run/docker.sock)")
  fi
  # shellcheck disable=SC2086
  in_builder "$subdir" "${docker_args[@]}" "$@" -- go test -count=1 $PACKAGES >"$log" 2>&1
  local rc=$?
  echo "$subdir: go test exit $rc; failing packages:"
  grep -E '^(FAIL|---)' "$log" | grep -vE '^--- (PASS|SKIP)' | sed 's/^/  /' | head -50
  return $rc
}

ref_slug=${REF//\//-}
rc=0
checkout_wt server "$REF" || exit 1    # the agent tests build against ../server-ce too
if [[ " $COMPONENTS " == *" server "* ]]; then
  run_tests server-ce "$LOG_DIR/test-server-$ref_slug.log" || rc=1
fi
if [[ " $COMPONENTS " == *" agent "* ]]; then
  checkout_wt agent "$REF" || exit 1
  run_tests portainer-agent "$LOG_DIR/test-agent-$ref_slug.log" -e CGO_ENABLED=1 -e GOFLAGS="-buildvcs=false -race" \
    || rc=1
fi
exit $rc
