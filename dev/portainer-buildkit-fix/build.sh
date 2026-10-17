#!/usr/bin/env bash
#
# Build patched Portainer Agent and Portainer CE server images for testing the BuildKit-through-agent fixes.
# See docs/portainer-buildkit-fix-handoff.md.
#
# Runs on any Linux (or WSL2) host with Docker and git. The Go binaries are cross-compiled in a golang container,
# then layered onto the official images, so no QEMU emulation is needed even when building arm64 images on x86.
#
# Environment variables (all optional):
#   WORK_DIR         Where the two fork checkouts live, side by side (default: ~/src/portainer-buildkit-fix).
#                    The agent's go.mod requires the server repo to be checked out as ../server-ce.
#   ARCH             Target architecture: arm64 (Raspberry Pi) or amd64 (default: arm64)
#   COMPONENTS       Which images to build: "agent server", "agent" or "server" (default: "agent server")
#   AGENT_REF        Branch/ref of mckelvie-org/portainer-agent (default: test/2.45.2-protocol-switch)
#   SERVER_REF       Branch/ref of mckelvie-org/portainer (default: test/2.45.2-buildkit-session-headers)
#   PORTAINER_BASE   Version tag of the official images to layer onto (default: 2.45.2)
#   PUSH_REGISTRY    If set (e.g. ghcr.io/mckelvie-org), push the images there instead of saving a tar file
#   GO_IMAGE         Go toolchain image (default: golang:1.26)
#
# Outputs (without PUSH_REGISTRY): $WORK_DIR/out/portainer-buildkit-fix-images-$ARCH.tar, which can be loaded on the
# hub with:   ssh <hub> docker load < portainer-buildkit-fix-images-arm64.tar
#
set -euo pipefail

WORK_DIR=${WORK_DIR:-$HOME/src/portainer-buildkit-fix}
ARCH=${ARCH:-arm64}
COMPONENTS=${COMPONENTS:-agent server}
AGENT_REF=${AGENT_REF:-test/2.45.2-protocol-switch}
SERVER_REF=${SERVER_REF:-test/2.45.2-buildkit-session-headers}
PORTAINER_BASE=${PORTAINER_BASE:-2.45.2}
PUSH_REGISTRY=${PUSH_REGISTRY:-}
GO_IMAGE=${GO_IMAGE:-golang:1.26}

AGENT_REPO=https://github.com/mckelvie-org/portainer-agent.git
SERVER_REPO=https://github.com/mckelvie-org/portainer.git
IMAGE_PREFIX=${PUSH_REGISTRY:-mckelvie-org}
AGENT_IMAGE="$IMAGE_PREFIX/portainer-agent:$PORTAINER_BASE-protocol-switch"
SERVER_IMAGE="$IMAGE_PREFIX/portainer-ce:$PORTAINER_BASE-buildkit-session-headers"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

checkout() {
  local repo=$1 dir=$2 ref=$3
  if [ ! -d "$dir/.git" ]; then
    git clone --filter=blob:none "$repo" "$dir"
  fi
  git -C "$dir" fetch --quiet origin
  git -C "$dir" checkout --quiet --detach "origin/$ref" 2>/dev/null || git -C "$dir" checkout --quiet --detach "$ref"
  echo "$dir: $(git -C "$dir" log --oneline -1)"
}

# Run a command in the Go container, with both checkouts mounted side by side and a persistent module/build cache
go_run() {
  local subdir=$1; shift
  mkdir -p "$WORK_DIR/.gocache"
  docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
    -e GOCACHE=/cache/build -e GOMODCACHE=/cache/mod -e GOFLAGS=-buildvcs=false \
    -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH="$ARCH" \
    -v "$WORK_DIR/.gocache:/cache" -v "$WORK_DIR:/work" -w "/work/$subdir" \
    "$GO_IMAGE" "$@"
}

# Layer a binary onto an official image for the target platform
layer_image() {
  local dockerfile=$1 base=$2 image=$3 binary=$4
  local ctx="$WORK_DIR/out/ctx-$(basename "$binary")"
  rm -rf "$ctx" && mkdir -p "$ctx"
  cp "$binary" "$ctx/"
  local output=(--load)
  [ -n "$PUSH_REGISTRY" ] && output=(--push)
  docker buildx build --platform "linux/$ARCH" -f "$SCRIPT_DIR/$dockerfile" --build-arg "BASE_IMAGE=$base" \
    --label "org.opencontainers.image.revision=$5" -t "$image" "${output[@]}" "$ctx"
}

mkdir -p "$WORK_DIR/out"
images=()

# The agent build always needs the server checkout too, because of the agent's `replace ... => ../server-ce`
checkout "$SERVER_REPO" "$WORK_DIR/server-ce" "$SERVER_REF"

if [[ " $COMPONENTS " == *" agent "* ]]; then
  checkout "$AGENT_REPO" "$WORK_DIR/portainer-agent" "$AGENT_REF"
  echo "Building agent binary (linux/$ARCH)..."
  go_run portainer-agent go build -trimpath --installsuffix cgo --ldflags "-s" -o ../out/agent ./cmd/agent/
  layer_image Dockerfile.agent "portainer/agent:$PORTAINER_BASE" "$AGENT_IMAGE" "$WORK_DIR/out/agent" \
    "$(git -C "$WORK_DIR/portainer-agent" rev-parse HEAD)"
  images+=("$AGENT_IMAGE")
fi

if [[ " $COMPONENTS " == *" server "* ]]; then
  echo "Building Portainer server binary (linux/$ARCH)..."
  go_run server-ce/api go build -trimpath --installsuffix cgo \
    --ldflags "-s -X 'github.com/portainer/liblicense.LicenseServerBaseURL=https://api.portainer.io' -X 'github.com/portainer/portainer/pkg/build.GitCommit=$(git -C "$WORK_DIR/server-ce" rev-parse --short HEAD)'" \
    -o ../../out/portainer ./cmd/portainer/
  layer_image Dockerfile.server "portainer/portainer-ce:$PORTAINER_BASE" "$SERVER_IMAGE" "$WORK_DIR/out/portainer" \
    "$(git -C "$WORK_DIR/server-ce" rev-parse HEAD)"
  images+=("$SERVER_IMAGE")
fi

if [ -z "$PUSH_REGISTRY" ]; then
  tarfile="$WORK_DIR/out/portainer-buildkit-fix-images-$ARCH.tar"
  docker save -o "$tarfile" "${images[@]}"
  echo "Saved ${images[*]} to $tarfile"
else
  echo "Pushed ${images[*]}"
fi
