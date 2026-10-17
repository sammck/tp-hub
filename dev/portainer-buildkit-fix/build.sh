#!/usr/bin/env bash
#
# Build Portainer CE and Portainer Agent images from our forks, using the forks' own Makefiles and Dockerfiles
# (build/linux/Dockerfile), and push them to a registry. See README.md in this directory.
#
# Runs on any Linux (or WSL2) host with Docker and git. The Go binaries are cross-compiled and the web client is built
# in a toolchain container (Dockerfile.builder); only the final `COPY`-only image build runs for the target platform,
# so no QEMU emulation is needed even when building arm64 images on x86. Builds happen in worktrees of your clones
# (see common.sh), so your working checkouts are not touched.
#
# Environment variables (all optional; see also common.sh for SERVER_REPO, AGENT_REPO, CACHE_DIR):
#   ARCH             Target architecture (default: arm64). One image per run; Portainer's own Dockerfiles take one
#                    architecture's dist/ at a time.
#   COMPONENTS       Which images to build: "server agent", "server" or "agent" (default: "server agent")
#   REF              Branch/ref to build in both forks (default: build/2.45.2-buildkit-fix, i.e. tag 2.45.2 + the fix).
#                    A local branch wins over origin/REF.
#   REGISTRY         Image namespace (default: docker.io/sammck)
#   TAG              Image tag (default: 2.45.2-buildkit-fix). Each image is also tagged $TAG-<short commit>.
#   PUSH             1 (default) to push to $REGISTRY, 0 to load the images into the local Docker instead
#                    (only possible when ARCH matches what the local Docker can load).
#   SYNC             1 (default) to fetch both forks and upstream first; 0 to use what the clones have
#
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

ARCH=${ARCH:-arm64}
COMPONENTS=${COMPONENTS:-server agent}
REF=${REF:-build/2.45.2-buildkit-fix}
REGISTRY=${REGISTRY:-docker.io/sammck}
TAG=${TAG:-2.45.2-buildkit-fix}
PUSH=${PUSH:-1}
SYNC=${SYNC:-1}

# Build a fork's build/linux/Dockerfile for the target platform and push (or load) it
build_image() {
  local dir=$1 name=$2 repo=$3
  local commit; commit=$(git -C "$dir" rev-parse HEAD)
  local output=(--push)
  [ "$PUSH" = 1 ] || output=(--load)
  docker buildx build --platform "linux/$ARCH" -f "$dir/build/linux/Dockerfile" \
    --build-arg "GIT_COMMIT=$commit" --build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --label "org.opencontainers.image.source=$(git -C "$repo" remote get-url origin)" \
    -t "$REGISTRY/$name:$TAG" -t "$REGISTRY/$name:$TAG-${commit:0:7}" \
    "${output[@]}" "$dir"
  images+=("$REGISTRY/$name:$TAG ($REGISTRY/$name:$TAG-${commit:0:7})")
}

ensure_builder
images=()

# The agent build needs the server worktree too, because of the agent's `replace ... => ../server-ce`
[ "$SYNC" = 1 ] && sync_repo server
checkout_wt server "$REF"

if [[ " $COMPONENTS " == *" server "* ]]; then
  echo "Building Portainer CE (server binary and web client, linux/$ARCH)..."
  # Client deps first, as in `make all`: build_binary.sh records the installed webpack version and exits
  # (silently) if it is missing. `make client-deps` is a plain `pnpm install`, which adds the pnpmfileChecksum of
  # package.json's configDependencies to pnpm-lock.yaml (missing from the committed lockfile, so
  # --frozen-lockfile is refused). Show the diff's removed lines (a changed pinned version would show up there),
  # then restore the lockfile.
  in_builder server-ce -- bash -euo pipefail -c "
    rm -rf dist
    make client-deps
    git diff --stat -- pnpm-lock.yaml
    git diff -U0 -- pnpm-lock.yaml | grep -E '^-[^-]' | head -20 || true
    git checkout -- pnpm-lock.yaml
    SKIP_GO_GET=true CONTAINER_IMAGE_TAG=$TAG make build-server PLATFORM=linux ARCH=$ARCH
    make build-client ENV=production"
  build_image "$SERVER_WT" portainer-ce "$SERVER_REPO"
fi

if [[ " $COMPONENTS " == *" agent "* ]]; then
  [ "$SYNC" = 1 ] && sync_repo agent
  checkout_wt agent "$REF"
  echo "Building Portainer Agent (linux/$ARCH)..."
  in_builder portainer-agent -- bash -euo pipefail -c "
    rm -rf dist && mkdir dist
    make agent credential-helper healthy PLATFORM=linux ARCH=$ARCH"
  build_image "$AGENT_WT" portainer-agent "$AGENT_REPO"
fi

printf '%s\n' "${images[@]/#/Built }"
