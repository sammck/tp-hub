Patched Portainer CE builds
==========================

Tools for running Portainer CE and the Portainer Agent built from our forks, with fixes that upstream hasn't released.
tp-hub uses these images by default: `sammck/portainer-ce` and `sammck/portainer-agent`, tagged with the upstream CE
version plus a suffix naming our fixes (`2.45.2-buildkit-fix`).
Today that is the pair of BuildKit-through-the-agent fixes (portainer/agent#752, portainer/portainer#13324); the
background, test results and hub setup are in
[docs/portainer-buildkit-fix-handoff.md](../../docs/portainer-buildkit-fix-handoff.md).

Why a fork
----------

Portainer CE stops at the 2.x line: 3.0 has no CE build, and the 2.45 LTS line (CE and BE) gets fixes until May 2027
([announcement](https://www.portainer.io/blog/portainer-3-0-is-coming), [lifecycle](https://docs.portainer.io/start/lifecycle)).
Portainer staff port external PRs into their internal monorepo rather than merging them, so even accepted fixes may only
ship in 3.x. Until a community fork of CE emerges, we follow 2.45 LTS releases and carry our fixes on top.

The code is zlib-licensed, so forking is fine. The "Portainer" name and logo are trademarks: fine for personal images
like `sammck/portainer-ce`, but anything published as a project needs its own name.

Repositories and branches
-------------------------

Your working clones of the forks, next to tp-hub:

| Clone | Fork (`origin`) | Upstream (`upstream`) |
|---|---|---|
| `~/projects/portainer` | `mckelvie-org/portainer` | `portainer/portainer` |
| `~/projects/portainer-agent` | `mckelvie-org/portainer-agent` | `portainer/agent` |

The agent's `go.mod` requires the server checkout at `../server-ce`. For Go tooling on the host (VS Code/gopls in the
agent clone), `~/projects/server-ce` is a symlink to `portainer`.

The scripts never change your clones' checkouts or working trees. They build and test in **git worktrees** of the
clones under `~/.cache/portainer-fix-build/worktrees/` (`server-ce/` and `portainer-agent/`), which share the clones'
commits and branches: a `build/` branch that `update.sh` creates is a branch of your clone. The same directory holds
the Go and pnpm caches (~10 GB) and test logs (`logs/`). Settings and helpers shared by the scripts are in
[`common.sh`](common.sh) (`SERVER_REPO`, `AGENT_REPO`, `CACHE_DIR`).

Branch conventions:

* `fix/<name>`: one fix per branch, based on upstream `develop`, ideally one commit. This is the patch queue, and the
  source of any upstream (or future community-fork) PR. Keep each one small and self-contained so it cherry-picks
  cleanly onto any 2.x-based code.
* `build/<tag>-<suffix>`: an upstream release tag plus every `fix/*` branch's commits. Images are built from these.
* `test/*`: one-off experiments (none currently). Delete when done.

Workflow
--------

**New upstream release (e.g. 2.45.3):**

```bash
dev/portainer-buildkit-fix/update.sh            # newest 2.45.x tag; or: update.sh 2.45.3
```

`update.sh`:

1. creates `build/<tag>-buildkit-fix` in both forks: the tag plus the `fix/*` commits. A fix that upstream already
   contains is dropped automatically; a fix that no longer applies stops the script;
2. runs both test suites on the new branch and on the plain tag, and fails only on packages that fail with our fixes
   but not without them (retrying those 3 times, since a few upstream tests are flaky);
3. builds and pushes `sammck/portainer-ce` and `sammck/portainer-agent` as `<tag>-buildkit-fix` (plus
   `<tag>-buildkit-fix-<commit>`), and pushes the branches;
4. prints where to set the new tag.

Then make the new tag tp-hub's default (`PORTAINER_DEFAULT_VERSION` in `bin/python/tp_hub/config/impl.py` and the
fallbacks in `stacks/portainer/docker-compose.yml`), deploy on the hub, and run the end-to-end test from the hand-off doc
("Testing on the hub"). To try a tag before making it the default, set `portainer_version` in the hub's `config.yml`.

**New fix:** in your clone, branch `fix/<name>` from `upstream/develop`, commit, test (`REF=fix/<name> test.sh`), push
it to `origin`, then rerun `update.sh` for the current release to rebuild with it included.

**Fix merged or released upstream:** nothing to do; `update.sh` drops it once the release contains it. Delete the
`fix/` branch when its PR is closed.

Scripts
-------

| Script | Purpose |
|---|---|
| `update.sh [TAG]` | The whole release update described above. `PUSH=0` builds locally only; `SKIP_TESTS=1` skips tests. |
| `build.sh` | Builds images from `REF` (default `build/2.45.2-buildkit-fix`) with the forks' own Makefiles and `build/linux/Dockerfile`; `PUSH=0` loads locally. |
| `test.sh` | Runs both forks' Go test suites (`REF=...`, `PACKAGES=...`, `COMPONENTS=server\|agent`). Mounts the Docker socket, because some packages deploy real stacks. Logs go to `~/.cache/portainer-fix-build/logs/`. |
| `common.sh` | Shared settings (clone locations, cache directory) and helpers, sourced by the other scripts. |
| `Dockerfile.builder` | Toolchain image (Go, Node, pnpm, docker CLI) that the scripts run in. Versions follow `package.json` and `go.mod`; bump them when upstream does. |
| `upstream-drafts.md` | The text posted for the upstream PRs and issue comments (2026-10-17). |

All scripts work in the worktrees described above and refuse to run if a worktree has uncommitted changes. `build.sh`
and `update.sh` fetch both forks and upstream first. A local branch wins over `origin/`, so a branch you create in
your clone is built as is.

Gotchas
-------

* `build/build_binary.sh` exits **silently** when `node_modules` is missing (it records the webpack version), so the
  client deps are installed before the server binary.
* `pnpm install --frozen-lockfile` fails on 2.45.x (missing `pnpmfileChecksum` for a `configDependencies` entry).
  `build.sh` uses `make client-deps` (plain `pnpm install`), shows the lockfile diff, and restores the file. On
  2.45.2 the diff only adds entries; no pinned version changes. Check that it stays that way.
* Images are single-arch (`ARCH`, default `arm64`): Portainer's Dockerfiles copy one arch's `dist/`. A multi-arch image
  would be one build per arch, joined with `docker buildx imagetools create`.
* Known flaky upstream tests: server `api/http/middlewares` (fails on plain 2.45.2 too) and agent `edge/health`
  (`TestConcurrency`, occasional).
* `pkill -f <pattern>` also matches the shell running it; kill builds by PID.
