#!/usr/bin/env bash
#
# Build Portainer CE and Portainer Agent images from the mckelvie-org forks, using the forks' own Makefiles and
# Dockerfiles (build/linux/Dockerfile), and push them to a registry. See docs/portainer-buildkit-fix-handoff.md.
#
# Runs on any Linux (or WSL2) host with Docker and git. The Go binaries are cross-compiled and the web client is built
# in a toolchain container (Dockerfile.builder); only the final `COPY`-only image build runs for the target platform,
# so no QEMU emulation is needed even when building arm64 images on x86.
#
# Environment variables (all optional):
#   WORK_DIR         Where the two fork checkouts live, side by side (default: ~/src/portainer-buildkit-fix).
#                    The agent's go.mod requires the server repo to be checked out as ../server-ce.
#   ARCH             Target architecture (default: arm64). One image per run; Portainer's own Dockerfiles take one
#                    architecture's dist/ at a time.
#   COMPONENTS       Which images to build: "server agent", "server" or "agent" (default: "server agent")
#   REF              Branch/ref to build in both forks (default: build/2.45.2-buildkit-fix, i.e. tag 2.45.2 + the fix)
#   REGISTRY         Image namespace (default: docker.io/sammck)
#   TAG              Image tag (default: 2.45.2-buildkit-fix). Each image is also tagged $TAG-<short commit>.
#   PUSH             1 (default) to push to $REGISTRY, 0 to load the images into the local Docker instead
#                    (only possible when ARCH matches what the local Docker can load).
#
set -euo pipefail

WORK_DIR=${WORK_DIR:-$HOME/src/portainer-buildkit-fix}
ARCH=${ARCH:-arm64}
COMPONENTS=${COMPONENTS:-server agent}
REF=${REF:-build/2.45.2-buildkit-fix}
REGISTRY=${REGISTRY:-docker.io/sammck}
TAG=${TAG:-2.45.2-buildkit-fix}
PUSH=${PUSH:-1}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BUILDER_IMAGE=portainer-fix-builder:local

checkout() {
  local repo=$1 upstream=$2 dir=$3
  if [ ! -d "$dir/.git" ]; then
    git clone --filter=blob:none "$repo" "$dir"
  fi
  git -C "$dir" remote get-url upstream >/dev/null 2>&1 || git -C "$dir" remote add upstream "$upstream"
  git -C "$dir" fetch --quiet origin
  git -C "$dir" fetch --quiet --tags upstream
  git -C "$dir" checkout --quiet --detach "origin/$REF" 2>/dev/null || git -C "$dir" checkout --quiet --detach "$REF"
  if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]; then
    echo "$dir has local changes; refusing to build" >&2
    exit 1
  fi
  echo "$dir: $(git -C "$dir" log --oneline -1)"
}

# Run a command in the toolchain container, with both checkouts mounted side by side and persistent caches
in_builder() {
  local subdir=$1; shift
  mkdir -p "$WORK_DIR/.cache/home"
  docker run --rm -u "$(id -u):$(id -g)" -e HOME=/cache/home \
    -e GOCACHE=/cache/go-build -e GOMODCACHE=/cache/go-mod -e GOFLAGS=-buildvcs=false \
    -v "$WORK_DIR/.cache:/cache" -v "$WORK_DIR:/work" -w "/work/$subdir" \
    "$BUILDER_IMAGE" bash -euo pipefail -c "$*"
}

# Build a fork's build/linux/Dockerfile for the target platform and push (or load) it
build_image() {
  local dir=$1 name=$2
  local commit; commit=$(git -C "$dir" rev-parse HEAD)
  local output=(--push)
  [ "$PUSH" = 1 ] || output=(--load)
  docker buildx build --platform "linux/$ARCH" -f "$dir/build/linux/Dockerfile" \
    --build-arg "GIT_COMMIT=$commit" --build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --label "org.opencontainers.image.source=$(git -C "$dir" remote get-url origin)" \
    -t "$REGISTRY/$name:$TAG" -t "$REGISTRY/$name:$TAG-${commit:0:7}" \
    "${output[@]}" "$dir"
  images+=("$REGISTRY/$name:$TAG ($REGISTRY/$name:$TAG-${commit:0:7})")
}

docker build -q -f "$SCRIPT_DIR/Dockerfile.builder" -t "$BUILDER_IMAGE" "$SCRIPT_DIR" >/dev/null
images=()

# The agent build needs the server checkout too, because of the agent's `replace ... => ../server-ce`
checkout https://github.com/mckelvie-org/portainer.git https://github.com/portainer/portainer.git "$WORK_DIR/server-ce"

if [[ " $COMPONENTS " == *" server "* ]]; then
  echo "Building Portainer CE (server binary and web client, linux/$ARCH)..."
  # Client deps first, as in `make all`: build_binary.sh records the installed webpack version and exits
  # (silently) if it is missing. `make client-deps` is a plain `pnpm install`, which adds the pnpmfileChecksum of
  # package.json's configDependencies to pnpm-lock.yaml (missing from the committed lockfile, so
  # --frozen-lockfile is refused). Show that diff, so any change of resolved packages would be visible, then
  # restore the lockfile.
  in_builder server-ce "
    rm -rf dist
    make client-deps
    git -c safe.directory='*' diff --stat -- pnpm-lock.yaml
    git -c safe.directory='*' diff -U0 -- pnpm-lock.yaml | grep -E '^[-+][^-+]' | head -20 || true
    git -c safe.directory='*' checkout -- pnpm-lock.yaml
    SKIP_GO_GET=true CONTAINER_IMAGE_TAG=$TAG make build-server PLATFORM=linux ARCH=$ARCH
    make build-client ENV=production"
  build_image "$WORK_DIR/server-ce" portainer-ce
fi

if [[ " $COMPONENTS " == *" agent "* ]]; then
  checkout https://github.com/mckelvie-org/portainer-agent.git https://github.com/portainer/agent.git \
    "$WORK_DIR/portainer-agent"
  echo "Building Portainer Agent (linux/$ARCH)..."
  in_builder portainer-agent "
    rm -rf dist && mkdir dist
    make agent credential-helper healthy PLATFORM=linux ARCH=$ARCH"
  build_image "$WORK_DIR/portainer-agent" portainer-agent
fi

printf '%s\n' "${images[@]/#/Built }"
