# Shared settings and helpers for build.sh, test.sh and update.sh (sourced, not run).
#
# The scripts never touch your working clones' checkouts. They build and test in git worktrees of those clones,
# under $CACHE_DIR/worktrees: server-ce/ and portainer-agent/ side by side, as the agent's go.mod requires
# (`replace github.com/portainer/portainer => ../server-ce`). Worktrees share the clones' commits and branches, so a
# branch created in a worktree is a branch of your clone.
#
# Environment variables (all optional):
#   SERVER_REPO   Your clone of the Portainer CE fork (default: ~/projects/portainer)
#   AGENT_REPO    Your clone of the Portainer Agent fork (default: ~/projects/portainer-agent)
#   CACHE_DIR     Worktrees, Go/pnpm caches and logs (default: ~/.cache/portainer-fix-build)

SERVER_REPO=${SERVER_REPO:-$HOME/projects/portainer}
AGENT_REPO=${AGENT_REPO:-$HOME/projects/portainer-agent}
CACHE_DIR=${CACHE_DIR:-$HOME/.cache/portainer-fix-build}
export SERVER_REPO AGENT_REPO CACHE_DIR

WORKTREES="$CACHE_DIR/worktrees"
SERVER_WT="$WORKTREES/server-ce"
AGENT_WT="$WORKTREES/portainer-agent"
LOG_DIR="$CACHE_DIR/logs"
BUILDER_IMAGE=portainer-fix-builder:local
COMMON_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

repo_for() { case $1 in server) echo "$SERVER_REPO" ;; agent) echo "$AGENT_REPO" ;; esac; }
wt_for() { case $1 in server) echo "$SERVER_WT" ;; agent) echo "$AGENT_WT" ;; esac; }
upstream_url_for() {
  case $1 in server) echo https://github.com/portainer/portainer.git ;; agent) echo https://github.com/portainer/agent.git ;; esac
}

# Make sure a clone has the `upstream` remote, and fetch fork branches and upstream tags
sync_repo() {
  local component=$1 repo; repo=$(repo_for "$1")
  [ -d "$repo/.git" ] || { echo "No git clone at $repo (set ${component^^}_REPO)" >&2; exit 1; }
  git -C "$repo" remote get-url upstream >/dev/null 2>&1 || git -C "$repo" remote add upstream "$(upstream_url_for "$component")"
  git -C "$repo" fetch --quiet --prune origin
  git -C "$repo" fetch --quiet --tags upstream
  git -C "$repo" fetch --quiet upstream develop
}

# Check out REF (a local branch wins over origin/REF) detached in a component's build worktree
checkout_wt() {
  local component=$1 ref=$2 repo wt; repo=$(repo_for "$1"); wt=$(wt_for "$1")
  mkdir -p "$WORKTREES"
  if [ ! -e "$wt/.git" ]; then
    git -C "$repo" worktree prune
    git -C "$repo" worktree add --quiet --detach "$wt" HEAD
  fi
  if [ -n "$(git -C "$wt" status --porcelain --untracked-files=no)" ]; then
    echo "$wt has uncommitted changes; refusing to continue" >&2
    exit 1
  fi
  git -C "$wt" checkout --quiet --detach "$ref" 2>/dev/null || git -C "$wt" checkout --quiet --detach "origin/$ref"
  echo "$component: $(git -C "$wt" log --oneline -1)"
}

ensure_builder() {
  docker build -q -f "$COMMON_DIR/Dockerfile.builder" -t "$BUILDER_IMAGE" "$COMMON_DIR" >/dev/null
}

# Run a command in the toolchain container: worktrees at /work, persistent caches at /cache.
# Usage: in_builder <server-ce|portainer-agent> [docker run options...] -- <command...>
in_builder() {
  local subdir=$1; shift
  local opts=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do opts+=("$1"); shift; done
  shift
  mkdir -p "$CACHE_DIR/home" "$CACHE_DIR/go-build" "$CACHE_DIR/go-mod"
  # The worktrees' .git files point at the clones' .git directories, so mount those at the same paths
  docker run --rm -u "$(id -u):$(id -g)" -e HOME=/cache/home \
    -e GOCACHE=/cache/go-build -e GOMODCACHE=/cache/go-mod -e GOFLAGS=-buildvcs=false \
    -v "$CACHE_DIR:/cache" -v "$WORKTREES:/work" \
    -v "$SERVER_REPO/.git:$SERVER_REPO/.git" -v "$AGENT_REPO/.git:$AGENT_REPO/.git" \
    "${opts[@]}" -w "/work/$subdir" "$BUILDER_IMAGE" "$@"
}
