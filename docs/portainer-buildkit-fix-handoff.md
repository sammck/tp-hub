Hand-off: fixing BuildKit builds through the Portainer Agent
===========================================================

*Status as of 2026-10-17. This document is meant to let the work continue from another machine without access to the
hub's shell history. For the problem description and the `DOCKER_BUILDKIT=0` workaround, see
[portainer-agent-build-issue.md](portainer-agent-build-issue.md).*

TL;DR
-----

BuildKit builds of Portainer stacks deployed to an **agent** environment need fixes in **two** Portainer repositories.
Both fixes are written, tested, and pushed to forks in the `mckelvie-org` GitHub organization:

| # | Repo (fork → upstream) | Bug | PR branch (on upstream `develop`) |
|---|---|---|---|
| 1 | [mckelvie-org/portainer-agent](https://github.com/mckelvie-org/portainer-agent) → `portainer/agent` | The agent's Docker socket proxy (`http/proxy/local.go`) does not relay `101 Switching Protocols`, so BuildKit's h2c upgrade of `/grpc` and `/session` dies (`http2: frame too large`). | `fix/docker-proxy-protocol-upgrade` |
| 2 | [mckelvie-org/portainer](https://github.com/mckelvie-org/portainer) → `portainer/portainer` | The header allowlist in the server's reverse proxy (`api/http/proxy/factory/reverse_proxy.go`, added in 2.31.0) drops BuildKit's `X-Docker-Expose-Session-*` headers, so sessions are registered with an empty ID (`no active sessions`, then 400 `session  already exists`). | `fix/proxy-buildkit-session-headers` |

**Status:** both fixes are verified end to end on the hub, with images built from source by the forks' own Makefiles and
published to Docker Hub. The hub runs those images with BuildKit on. The PR branches have trimmed commit messages and
are current with upstream `develop`. The PR descriptions and issue comments are drafted in
[upstream-drafts.md](../dev/portainer-buildkit-fix/upstream-drafts.md), waiting for Sam's review.

Remaining steps
---------------

1. Sam reviews the commits on the two `fix/*` branches and the drafts in
   [upstream-drafts.md](../dev/portainer-buildkit-fix/upstream-drafts.md).
2. Open the PRs and post the issue comments in the order given there.
3. When Portainer releases both fixes, remove the overrides from the hub's `config.yml` (and the `DOCKER_BUILDKIT`
   workaround from tp-hub), then delete the `build/` and `test/` branches and the Docker Hub images.

Branches and images
-------------------

| Fork branch | Base | Purpose |
|---|---|---|
| `fix/docker-proxy-protocol-upgrade` (agent, `38bb455`) | upstream `develop` | PR branch |
| `fix/proxy-buildkit-session-headers` (server, `658a3eae6`) | upstream `develop` | PR branch |
| `build/2.45.2-buildkit-fix` (agent `c8def40`, server `dc32cb97d`) | tag `2.45.2` | What the Docker Hub images are built from: the release plus the fix, nothing else |
| `test/2.45.2-protocol-switch` (agent) | tag `2.45.2` | Earlier test build; the fix plus a TEMPORARY debug-logging commit. Can be deleted |
| `test/2.45.2-buildkit-session-headers` (server) | tag `2.45.2` | Same commit as the server `build/` branch. Can be deleted |

PRs include only their own branch's commits, so the `build/` and `test/` branches never end up in a PR. The fix diffs
on `fix/*` and `build/*` are identical.

Docker Hub images (public, linux/arm64 only), built from the `build/` branches:

* `sammck/portainer-ce:2.45.2-buildkit-fix` (also `…-dc32cb9`)
* `sammck/portainer-agent:2.45.2-buildkit-fix` (also `…-c8def40`)

They report version "2.45.2 LTS" like the official release; `GET /api/system/version` shows
`Build.ImageTag: 2.45.2-buildkit-fix` and `Build.GitCommit: dc32cb97d`.

Building the images
-------------------

[`dev/portainer-buildkit-fix/build.sh`](../dev/portainer-buildkit-fix/build.sh) checks out both forks side by side
under `$WORK_DIR` (default `~/src/portainer-buildkit-fix`), then builds each one with its own tooling inside a
toolchain container ([`Dockerfile.builder`](../dev/portainer-buildkit-fix/Dockerfile.builder): Go 1.26.6, Node 22.22.1,
pnpm 10.26.2, docker CLI):

* server: `make client-deps`, `make build-server PLATFORM=linux ARCH=<arch>`, `make build-client ENV=production`;
* agent: `make agent credential-helper healthy PLATFORM=linux ARCH=<arch>`;
* then each fork's `build/linux/Dockerfile` (`FROM portainer/base`) with `docker buildx --platform linux/<arch>`.

The Go binaries are cross-compiled and the image build only copies files, so no QEMU is needed. On a 32-core x86 box
the whole build takes about 4 minutes.

```bash
dev/portainer-buildkit-fix/build.sh            # arm64, push to docker.io/sammck (needs `docker login`)
PUSH=0 dev/portainer-buildkit-fix/build.sh     # load into local Docker instead
ARCH=amd64 COMPONENTS=agent dev/portainer-buildkit-fix/build.sh
```

Things that are not obvious:

* `build/build_binary.sh` records the installed webpack version and exits **silently** if `node_modules` is missing,
  so client deps must be installed before `make build-server` (as `make all` does).
* `pnpm install --frozen-lockfile` is refused on 2.45.2: `package.json` has a pnpm `configDependencies` entry
  (`@pnpm/plugin-types-fixer`) whose `pnpmfileChecksum` is missing from the committed lockfile. `make client-deps` is a
  plain `pnpm install`, which adds about 190 lockfile entries (`@types/*` and other peer dependencies). It changes
  **no** version of the 1,838 pinned packages. `build.sh` prints the lockfile diff and then restores the file.
* Portainer's release pipeline (multi-arch manifests) is internal; the public repos only build one arch per `dist/`.
  A multi-arch image would be one build per arch, joined with `docker buildx imagetools create`.

Compared with the official `portainer/portainer-ce:2.45.2` and `portainer/agent:2.45.2` (arm64), the images have the
same files, entrypoint, working directory, ports, volume and `io.portainer.*` labels. The only differences are the
patched binaries and the hashed names of the 6 webpack bundles.

Tests
-----

[`dev/portainer-buildkit-fix/test.sh`](../dev/portainer-buildkit-fix/test.sh) runs both forks' full Go test suites in the
toolchain container (`REF=2.45.2` for a baseline of the unpatched release). It mounts the Docker socket, because
`pkg/libstack/compose` (server) and `edge/stack` (agent) deploy real stacks.

Results on the `build/` branches (2026-10-17): every package passes except two flaky tests, which behave the same on
unpatched `2.45.2`:

* server `api/http/middlewares` `TestWithPanicLoggerRePanicsErrAbortHandler`: fails on 2.45.2 too (it catches a
  deprecation warning logged by another test);
* agent `edge/health` `TestConcurrency`: an occasional race on `/tmp/.portainer-healthy`; it passed 10 of 10 runs on
  both branches.

On the server PR branch (`develop`-based), `go build ./api/... ./pkg/...`, `go vet` and the `api/http/proxy/...` and
`api/exec/...` tests pass. The agent PR branch can't be built: agent `develop` doesn't compile against portainer
`develop` (see [Repository notes](#repository-notes)). Its `local.go` is identical to 2.45.2's.

End-to-end results
------------------

**Run 2 (2026-10-17, final):** Docker Hub images (from-source build), BuildKit on, cache pruned first.

* jvc-projector (stack 3) redeployed via the API in 57 s with BuildKit (`#1 [jvc-projector internal] load build
  definition`, no `Step N/M` lines). The container was recreated and `/jvc-projector/api/v1/` returns 200.
* A throwaway stack with `RUN sleep 150` completed (`#5 150.6 done-sleeping`), so long builds survive the agent's 120 s
  timeout. The stack and its image were removed afterwards.
* No errors in the Portainer log, no warnings or errors from the agent, no session errors in dockerd.

**Run 1 (2026-10-17):** official images with the patched binary swapped in, and the agent with debug logging.

* Every `/session` upgrade carried `X-Docker-Expose-Session-Uuid`, `-Grpc-Method` (and `-Sharedkey`) and got 101; there
  were no non-101 `/session` or `/grpc` upgrades.
* dockerd logs `healthcheck failed` / `session healthcheck failed fatally: ... only one connection allowed` during and
  after each build. This is **not** caused by Portainer: a plain `DOCKER_BUILDKIT=1 docker compose build` run directly
  on the hub produces the same messages. Builds are unaffected.

Evidence from before the fixes
------------------------------

* Stock agent + BuildKit: the server fails with `listing workers for Build: ... http2: frame too large, note that the
  frame header looked like an HTTP/1.1 header`. At the same moment, the agent logs
  `http/proxy/local.go:51 > Error copying response body ... "http: request method or response status code does not allow body"`,
  once each for `/session` and `/grpc`.
* Patched agent + stock server: the error changes to `failed to dial gRPC: unable to upgrade to h2c, received 400`. The
  agent debug trace shows `/grpc` → 101, `/session` → 101, `/grpc` → 101, then `/session` → **400**. The headers that
  reach the agent are only `Upgrade, Connection, X-Portaineragent-Publickey, X-Portaineragent-Signature,
  Accept-Encoding, User-Agent, Content-Length`; no `X-Docker-Expose-Session-*`. dockerd logs
  `LLBBridge/Solve ... failed to read dockerfile: no active sessions`.
* Reproduced directly against `/var/run/docker.sock`: a `/session` upgrade without `X-Docker-Expose-Session-Uuid` gets
  101; a second one while the first is open gets `400 {"message":"session  already exists"}` (note the empty ID); one with
  a UUID gets 101.
* Unit tests: agent `TestLocalProxyRelaysProtocolSwitch` fails on the original `local.go` in 5 s and passes with the fix;
  server `Test_createRewriteFn/BuildKit_session_headers` fails on the original allowlist and passes with the fix.
* History: the agent bug predates 2023 (reports in #10562 on 2.19). The server allowlist arrived in 2.31.0 and the
  2.27 LTS line (`b767dcb27 fix(proxy): whitelist headers for proxy to forward [BE-11819]`); it is not in 2.29.2.
  `Connection`/`Upgrade` were only allowed from 2.33.0, which also explains portainer/portainer#12754 on Docker API
  environments (all non-socket environments deploy through the same proxy). Portainer 2.19 also did not build images
  that already existed, because it ran `docker-compose up -d`, while 2.45 calls `Build` on every deploy.

Repository notes
----------------

* The agent's `go.mod` contains `replace github.com/portainer/portainer => ../server-ce`, so the server repository
  must be checked out **as a sibling directory named `server-ce`**, at a compatible revision. Both checkouts have an
  `upstream` remote for the Portainer repos (tags come from there).
* Upstream `portainer/agent` `develop` (last commit 2026-08-31) is older than the `2.45.2` tag and does not compile
  against the public `portainer/portainer` `develop` (`undefined: httprequest.TrimDockerVersion`). Releases are cut from
  Portainer's internal monorepo, which both GitHub repos mirror. Hence: build and test on `2.45.2`, and open the PRs
  against `develop`. The changed files are identical between the two.
* Staff port external PRs internally rather than merge them; the drafts are written with that in mind.
* git in WSL has no global `user.name`/`user.email`; the fork commits use `Sam McKelvie <dev@mckelvie.org>`.

Setting up a dev box (Windows)
------------------------------

Use **WSL2** with an Ubuntu distribution. It behaves like a normal Linux box for everything here.

1. Install WSL2 + Ubuntu (`wsl --install -d Ubuntu`), and either Docker Desktop with WSL integration enabled for that
   distribution, or Docker Engine installed inside WSL. With Docker Desktop, `docker login` uses its credential store.
2. Inside WSL: install `git`, and set up the SSH key used for GitHub (the forks are pushed over SSH).
3. Keep checkouts in the WSL filesystem (e.g. `~/src`), not under `/mnt/c`, which is much slower and has permission quirks.
   VS Code's "WSL" extension opens them natively.
4. Clone tp-hub (branch `traefik-v3-rule-syntax`) to get the build kit and this document.

`mchub` doesn't resolve inside WSL. Use the IP that Windows resolves for `mchub.local` (192.168.4.244 at the time):
`ssh -o HostKeyAlias=mchub sam@<ip>`.

Testing on the hub
------------------

tp-hub's Portainer stack accepts these overrides, set under `portainer_stack_env` in the hub's `config.yml` (which is
not tracked in git):

| Variable | Purpose | Default |
|---|---|---|
| `PORTAINER_IMAGE` | Portainer server image repository | `portainer/portainer-ce` |
| `PORTAINER_VERSION` | Portainer server image tag | `config.portainer_version` |
| `PORTAINER_AGENT_IMAGE` | Agent image repository | `portainer/agent` |
| `PORTAINER_AGENT_VERSION` | Agent image tag | `${PORTAINER_VERSION}` |
| `PORTAINER_DOCKER_BUILDKIT` | `DOCKER_BUILDKIT` for the Portainer server: `0` = classic-builder workaround, `1` = BuildKit | `0` |

**Current hub state** (2026-10-17). The previous config is saved as `~/tp-hub/config.yml.bak-2026-10-17` on the hub:

```yaml
  portainer_stack_env:
    PORTAINER_IMAGE: sammck/portainer-ce
    PORTAINER_VERSION: 2.45.2-buildkit-fix
    PORTAINER_AGENT_IMAGE: sammck/portainer-agent
    PORTAINER_AGENT_VERSION: 2.45.2-buildkit-fix
    PORTAINER_DOCKER_BUILDKIT: "1"
```

**End-to-end test:**

1. Apply the config with `hub build && hub portainer up` (Docker pulls the images).
2. Clear the BuildKit cache, so the builds are real: `docker builder prune -af`.
3. Redeploy the jvc-projector stack (stack 3, a git stack from `github.com/sammck/jvc-projector`, branch
   `modernize-docker-build`): "Pull and redeploy" in the UI, or `PUT /api/stacks/3/git/redeploy?endpointId=3` with the
   stack's env and reference. Deployments are asynchronous: poll `GET /api/stacks/3` until the last
   `DeploymentStatus` entry is no longer 3 (1 = done).
4. For a build longer than the agent's 120 s timeout, create a throwaway stack with
   `POST /api/stacks/create/standalone/string?endpointId=3` whose compose file builds
   `FROM busybox` / `RUN sleep 150` via `dockerfile_inline`, then delete it.
5. Success: the Portainer log shows BuildKit progress (`#1 [... internal] load build definition`) and no `Step N/M`,
   no `frame too large` / `unable to upgrade` / `no active sessions` / `session already exists` anywhere, and
   `http://<hub>/jvc-projector/api/v1/` returns 200.
6. **Rollback** at any time: remove the override lines (or set `PORTAINER_DOCKER_BUILDKIT: "0"` with stock images),
   then `hub build && hub portainer up`.

API notes: the API is at `http://localhost:9000/portainer/api` on the hub. The token in
`~/.private/claude_portainer_access_token.txt` is the bare token with no newline, so
`-H "X-API-Key: $(cat ~/.private/claude_portainer_access_token.txt)"` works as is. (It originally had CRLF line endings
from a Windows copy/paste, which made the API return 400.) `docker logs --since` takes UTC or a relative time
(`15m`); a local-time timestamp silently selects the wrong window.

Publishing upstream
-------------------

Everything to post is in [upstream-drafts.md](../dev/portainer-buildkit-fix/upstream-drafts.md): both PR descriptions
and comments for portainer/portainer#13255 (the main write-up), #12754 and #10562, plus the order of posting and the
facts they rely on. Sam reviews all text before it is posted.

Style requirement: keep everything concise and human-like, so that maintainers are not burdened with a verbose,
obviously AI-generated PR. PR descriptions are a few short plain paragraphs, with no headings, tables or evidence dumps,
and link to the issue for details. Commit messages are a subject line plus a few lines.

Related state elsewhere
-----------------------

* tp-hub branch `traefik-v3-rule-syntax` (not yet merged to `main`) contains: the traefik v2/v3-neutral rules, the
  `PORTAINER_` prefixed shared variables, the `DOCKER_BUILDKIT` workaround and image overrides, these docs, and the build kit.
  The hub's untracked `config.yml` pins `traefik_version: "3.7.15"`.
* jvc-projector branch `modernize-docker-build` (pushed, not merged) contains: python 3.13 / Poetry 2 Dockerfile,
  committed `poetry.lock`, the `PORTAINER_*` variable names, and the local `jvc-projector:local` image. The Portainer stack
  deploys from this branch until it is merged; switching the stack back to `main` makes Portainer remove the stack before
  rebuilding, so expect brief downtime.
