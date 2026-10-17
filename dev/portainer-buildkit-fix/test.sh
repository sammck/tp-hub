#!/usr/bin/env bash
#
# Run the Go test suites of the Portainer CE and Portainer Agent forks in the toolchain container (Dockerfile.builder),
# the way their Makefiles do (`make test-server` / `make test`, minus coverage). See docs/portainer-buildkit-fix-handoff.md.
#
# Environment variables (all optional):
#   WORK_DIR     Where the two fork checkouts live, side by side (default: ~/src/portainer-buildkit-fix)
#   REF          Branch/ref/tag to test in both forks (default: build/2.45.2-buildkit-fix). Use REF=2.45.2 for a
#                baseline of the unpatched release, to tell pre-existing failures from new ones.
#   COMPONENTS   "server agent" (default), "server" or "agent"
#   PACKAGES     Go packages to test (default: ./...)
#   DOCKER       1 (default) to give the tests the local Docker daemon (mounts /var/run/docker.sock); some packages
#                (pkg/libstack/compose, edge/stack) deploy real stacks and pull small images. 0 to run without it,
#                in which case those packages fail with "Cannot connect to the Docker daemon".
#
# Writes $WORK_DIR/test-<component>-<ref>.log and prints a summary of failing packages.
#
set -uo pipefail

WORK_DIR=${WORK_DIR:-$HOME/src/portainer-buildkit-fix}
REF=${REF:-build/2.45.2-buildkit-fix}
COMPONENTS=${COMPONENTS:-server agent}
PACKAGES=${PACKAGES:-./...}
DOCKER=${DOCKER:-1}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BUILDER_IMAGE=portainer-fix-builder:local
docker build -q -f "$SCRIPT_DIR/Dockerfile.builder" -t "$BUILDER_IMAGE" "$SCRIPT_DIR" >/dev/null

checkout() {
  local dir=$1
  git -C "$dir" checkout --quiet --detach "$REF" 2>/dev/null || git -C "$dir" checkout --quiet --detach "origin/$REF"
  echo "$dir: $(git -C "$dir" log --oneline -1)"
}

run_tests() {
  local subdir=$1 log=$2; shift 2
  mkdir -p "$WORK_DIR/.cache/home"
  local docker_args=()
  if [ "$DOCKER" = 1 ]; then
    docker_args=(-v /var/run/docker.sock:/var/run/docker.sock --group-add "$(stat -c %g /var/run/docker.sock)")
  fi
  docker run --rm -u "$(id -u):$(id -g)" -e HOME=/cache/home "${docker_args[@]}" \
    -e GOCACHE=/cache/go-build -e GOMODCACHE=/cache/go-mod -e GOFLAGS=-buildvcs=false "$@" \
    -v "$WORK_DIR/.cache:/cache" -v "$WORK_DIR:/work" -w "/work/$subdir" \
    "$BUILDER_IMAGE" go test -count=1 $PACKAGES >"$log" 2>&1
  local rc=$?
  echo "$subdir: go test exit $rc; failing packages:"
  grep -E '^(FAIL|---)' "$log" | grep -vE '^--- (PASS|SKIP)' | sed 's/^/  /' | head -50
  return $rc
}

ref_slug=${REF//\//-}
rc=0
checkout "$WORK_DIR/server-ce"
if [[ " $COMPONENTS " == *" server "* ]]; then
  run_tests server-ce "$WORK_DIR/test-server-$ref_slug.log" || rc=1
fi
if [[ " $COMPONENTS " == *" agent "* ]]; then
  checkout "$WORK_DIR/portainer-agent"
  run_tests portainer-agent "$WORK_DIR/test-agent-$ref_slug.log" -e CGO_ENABLED=1 -e GOFLAGS="-buildvcs=false -race" \
    || rc=1
fi
exit $rc
