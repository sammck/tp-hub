#!/usr/bin/env bash
#
# Move our patched Portainer CE and Agent builds to a new upstream release: create build/<tag>-<suffix> branches
# (the release tag plus our fix commits), run the test suites, build and push the images, and push the branches.
# See README.md in this directory.
#
# Usage:  update.sh [TAG]        TAG defaults to the newest upstream 2.45.x tag
#
# Environment variables (all optional):
#   WORK_DIR       Where the two fork checkouts live, side by side (default: ~/src/portainer-buildkit-fix)
#   TAG_PATTERN    Release line to follow when TAG is not given (default: 2.45.*)
#   SUFFIX         Branch and image tag suffix (default: buildkit-fix): branch build/<tag>-<suffix>, image <tag>-<suffix>
#   FIX_BRANCHES   Fork branches whose commits are our fixes, applied in this order (default: every origin/fix/*
#                  branch). Each branch's commits are those not in upstream/develop.
#   SKIP_TESTS     1 to skip the test suites
#   PUSH           1 (default) to push images and branches; 0 to build and load locally only
#   ARCH           Passed to build.sh (default: arm64)
#
set -euo pipefail

WORK_DIR=${WORK_DIR:-$HOME/src/portainer-buildkit-fix}
TAG_PATTERN=${TAG_PATTERN:-2.45.*}
SUFFIX=${SUFFIX:-buildkit-fix}
SKIP_TESTS=${SKIP_TESTS:-0}
PUSH=${PUSH:-1}
export WORK_DIR ARCH=${ARCH:-arm64}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPOS=(server-ce portainer-agent)    # server first: the agent builds against ../server-ce

for dir in "${REPOS[@]}"; do
  if [ -n "$(git -C "$WORK_DIR/$dir" status --porcelain --untracked-files=no)" ]; then
    echo "$WORK_DIR/$dir has local changes; refusing to continue" >&2
    exit 1
  fi
  git -C "$WORK_DIR/$dir" fetch --quiet origin
  git -C "$WORK_DIR/$dir" fetch --quiet --tags upstream
  git -C "$WORK_DIR/$dir" fetch --quiet upstream develop
done

TAG=${1:-$(git -C "$WORK_DIR/server-ce" tag -l "$TAG_PATTERN" | sort -V | tail -1)}
BRANCH="build/$TAG-$SUFFIX"
echo "Release: $TAG -> branch $BRANCH, images *:$TAG-$SUFFIX"

# --- 1. Branches: tag + our fixes -------------------------------------------------------------------------------
for dir in "${REPOS[@]}"; do
  repo="$WORK_DIR/$dir"
  if ! git -C "$repo" rev-parse --verify --quiet "refs/tags/$TAG^{commit}" >/dev/null; then
    echo "$dir: upstream has no tag $TAG" >&2
    exit 1
  fi
  fixes=${FIX_BRANCHES:-$(git -C "$repo" for-each-ref --format='%(refname:short)' 'refs/remotes/origin/fix/*')}
  git -C "$repo" checkout --quiet -B "$BRANCH" "$TAG"
  for fix in $fixes; do
    commits=$(git -C "$repo" rev-list --reverse "upstream/develop..$fix")
    [ -n "$commits" ] || { echo "$dir: $fix has no commits outside upstream/develop (merged upstream?)"; continue; }
    # --empty=drop skips a fix that the release already contains
    # shellcheck disable=SC2086
    if ! git -C "$repo" cherry-pick -x --empty=drop $commits >/dev/null; then
      echo "$dir: $fix does not apply cleanly to $TAG. Resolve it in $repo (git cherry-pick --continue)," >&2
      echo "then rerun this script with FIX_BRANCHES set to the remaining branches, or fix the fix/ branch." >&2
      exit 1
    fi
  done
  echo "$dir: $BRANCH = $TAG + $(git -C "$repo" rev-list --count "$TAG..$BRANCH") fix commit(s)"
  git -C "$repo" log --format='    %h %s' "$TAG..$BRANCH"
done

# --- 2. Tests: compare with the unpatched release, retry suspected flakes ---------------------------------------
failing_packages() { grep -hE '^FAIL\s+\S+' "$@" 2>/dev/null | awk '{print $2}' | sort -u; }

if [ "$SKIP_TESTS" != 1 ]; then
  echo "Running test suites on $BRANCH and on $TAG (baseline)..."
  REF="$BRANCH" "$SCRIPT_DIR/test.sh" >/dev/null || true
  REF="$TAG" "$SCRIPT_DIR/test.sh" >/dev/null || true
  slug_new=${BRANCH//\//-}
  new_failures=()
  for component in server agent; do
    dir=$([ $component = server ] && echo server-ce || echo portainer-agent)
    extra=$(comm -23 <(failing_packages "$WORK_DIR/test-$component-$slug_new.log") \
                     <(failing_packages "$WORK_DIR/test-$component-$TAG.log"))
    for pkg in $extra; do
      # A package that fails only with our fixes: retry it, since some upstream tests are flaky
      passed=0
      for _ in 1 2 3; do
        if REF="$BRANCH" COMPONENTS=$component PACKAGES="$pkg" "$SCRIPT_DIR/test.sh" >/dev/null 2>&1; then
          passed=1; break
        fi
      done
      if [ $passed = 1 ]; then echo "  $pkg: failed once, passed on retry (flaky)"
      else new_failures+=("$dir $pkg"); fi
    done
    git -C "$WORK_DIR/$dir" checkout --quiet "$BRANCH"
  done
  echo "Failing on $TAG without our fixes too (not ours): $(failing_packages "$WORK_DIR"/test-*-"$TAG".log | tr '\n' ' ')"
  if [ ${#new_failures[@]} -gt 0 ]; then
    printf 'New test failures with our fixes:\n'; printf '  %s\n' "${new_failures[@]}"
    echo "Logs: $WORK_DIR/test-*-$slug_new.log. Not building or pushing." >&2
    exit 1
  fi
  echo "Tests: no new failures."
fi

# --- 3. Images and branches ---------------------------------------------------------------------------------------
REF="$BRANCH" TAG="$TAG-$SUFFIX" PUSH="$PUSH" "$SCRIPT_DIR/build.sh"

if [ "$PUSH" = 1 ]; then
  for dir in "${REPOS[@]}"; do
    git -C "$WORK_DIR/$dir" push --quiet --force-with-lease origin "$BRANCH"
  done
  echo "Pushed $BRANCH to both forks."
fi

cat <<EOF

To make it tp-hub's default, set the new tag in both places and commit:
    bin/python/tp_hub/config/impl.py:     PORTAINER_DEFAULT_VERSION = "$TAG-$SUFFIX"
    stacks/portainer/docker-compose.yml:  the two \${PORTAINER_VERSION:-...} fallbacks
(or, to try it on the hub first, set "portainer_version: $TAG-$SUFFIX" in ~/tp-hub/config.yml).
Then on the hub: hub build && hub portainer up, and run the end-to-end test
(docs/portainer-buildkit-fix-handoff.md, "Testing on the hub").
EOF
