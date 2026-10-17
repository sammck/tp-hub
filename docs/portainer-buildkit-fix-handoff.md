Hand-off: fixing BuildKit builds through the Portainer Agent
===========================================================

*Status as of 2026-10-16. This document is meant to let the work continue from another machine (e.g., a faster dev box)
without access to the hub's shell history. For the problem description and the `DOCKER_BUILDKIT=0` workaround, see
[portainer-agent-build-issue.md](portainer-agent-build-issue.md).*

TL;DR
-----

BuildKit builds of Portainer stacks deployed to an **agent** environment need fixes in **two** Portainer repositories.
Both fixes are written, unit-tested, and pushed to forks in the `mckelvie-org` GitHub organization:

| # | Repo (fork → upstream) | Bug | PR branch (based on upstream `develop`) | Test branch (based on tag `2.45.2`) |
|---|---|---|---|---|
| 1 | [mckelvie-org/portainer-agent](https://github.com/mckelvie-org/portainer-agent) → `portainer/agent` | The agent's Docker socket proxy (`http/proxy/local.go`) does not relay `101 Switching Protocols`, so BuildKit's h2c upgrade of `/grpc` and `/session` dies (`http2: frame too large`). | `fix/docker-proxy-protocol-upgrade` | `test/2.45.2-protocol-switch` (also has a TEMPORARY debug-logging commit) |
| 2 | [mckelvie-org/portainer](https://github.com/mckelvie-org/portainer) → `portainer/portainer` | The header allowlist in the server's reverse proxy (`api/http/proxy/factory/reverse_proxy.go`, added in 2.31.0) drops BuildKit's `X-Docker-Expose-Session-*` headers, so sessions are registered with an empty ID (`no active sessions`, then 400 `session  already exists`). | `fix/proxy-buildkit-session-headers` | `test/2.45.2-buildkit-session-headers` |

**Fix 1 is verified live on the hub**: with the patched agent, every `/grpc` and `/session` upgrade is relayed with `101`
and BuildKit's `Solve` reaches the daemon. **Fix 2 is unit-tested only**. The next step is to build a patched
Portainer server image (too slow on the Raspberry Pi), deploy both patched images on the hub, and run an end-to-end
BuildKit build.

Remaining steps
---------------

1. Build the patched images on a fast machine ([Building](#building-the-patched-images)).
2. Load them on the hub and switch tp-hub to them with BuildKit enabled ([Testing on the hub](#testing-on-the-hub)).
3. Run the end-to-end test, including a build longer than 2 minutes. That exercises fix 1's clearing of the agent
   server's 120 s read deadline.
4. If the test passes: drop the debug commit, open the two upstream PRs, and comment on portainer/portainer#13255
   ([Publishing upstream](#publishing-upstream)).
5. When Portainer releases both fixes, remove the overrides and the workaround from tp-hub.

Evidence collected so far
-------------------------

* Stock agent + BuildKit: the server fails with `listing workers for Build: ... http2: frame too large, note that the
  frame header looked like an HTTP/1.1 header`. At the same moment, the agent logs
  `http/proxy/local.go:51 > Error copying response body ... "http: request method or response status code does not allow body"`,
  once each for `/session` and `/grpc`.
* Patched agent + BuildKit: the error changes to `failed to dial gRPC: unable to upgrade to h2c, received 400`. The agent
  debug trace shows `/grpc` → 101, `/session` → 101, `/grpc` → 101, then `/session` → **400**. The headers that reach the
  agent are only `Upgrade, Connection, X-Portaineragent-Publickey, X-Portaineragent-Signature, Accept-Encoding,
  User-Agent, Content-Length`; no `X-Docker-Expose-Session-*`. dockerd logs
  `LLBBridge/Solve ... failed to read dockerfile: no active sessions` and
  `session healthcheck failed fatally: ... only one connection allowed`.
* Reproduced directly against `/var/run/docker.sock`: a `/session` upgrade without `X-Docker-Expose-Session-Uuid` gets
  101; a second one while the first is open gets `400 {"message":"session  already exists"}` (note the empty ID); one with
  a UUID gets 101.
* Unit tests: agent `TestLocalProxyRelaysProtocolSwitch` fails on the original `local.go` in 5 s and passes with the fix;
  server `Test_createRewriteFn/BuildKit_session_headers` fails on the original allowlist and passes with the fix.
  Existing tests in `http/proxy`, `http/handler/docker` (agent) and `api/http/proxy/factory` (server) pass.
* History: the agent bug predates 2023 (reports in #10562 on 2.19). The server allowlist arrived in 2.31.0
  (`b767dcb27 fix(proxy): whitelist headers for proxy to forward [BE-11819]`, 2025-05-30). Portainer 2.19 also did not
  build images that already existed, because it ran `docker-compose up -d`, while 2.45 calls `Build` on every deploy.

Repository notes
----------------

* The agent's `go.mod` contains `replace github.com/portainer/portainer => ../server-ce`, so the server repository
  must be checked out **as a sibling directory named `server-ce`**, at a compatible revision.
* Upstream `develop` branches are not usable for building or testing. `portainer/agent` `develop` (last commit 2026-08-31)
  is older than the `2.45.2` tag, and it does not compile against the public `portainer/portainer` `develop`
  (`undefined: httprequest.TrimDockerVersion`). Releases appear to be cut from internal branches. Therefore:
  * test on the `test/2.45.2-*` branches (agent tag `2.45.2` + server tag `2.45.2`), which match the hub;
  * PRs target `develop`. The changed files (`http/proxy/local.go`, `api/http/proxy/factory/reverse_proxy.go`) are
    identical between `2.45.2` and `develop`, so the same patch applies to both.
* Toolchain: Go 1.26 (`golang:1.26` image). All builds use `CGO_ENABLED=0`, so cross-compiling to `arm64` is trivial.
* Unit tests (from a checkout with `server-ce` as a sibling):
  ```bash
  # agent (needs CGO for -race)
  docker run --rm -v "$PWD/..:/work" -w /work/portainer-agent -e CGO_ENABLED=1 golang:1.26 \
    go test -race ./http/proxy/ ./http/handler/docker/
  # server
  docker run --rm -v "$PWD/..:/work" -w /work/server-ce golang:1.26 go test ./api/http/proxy/factory/
  ```

Setting up a dev box (Windows)
------------------------------

Use **WSL2** with an Ubuntu distribution. It behaves like a normal Linux box for everything here.

1. Install WSL2 + Ubuntu (`wsl --install -d Ubuntu`), and either Docker Desktop with WSL integration enabled for that
   distribution, or Docker Engine installed inside WSL.
2. Inside WSL: install `git` and `gh`, run `gh auth login`, and set up the SSH key used for GitHub.
3. Keep checkouts in the WSL filesystem (e.g. `~/src`), not under `/mnt/c`, which is much slower and has permission quirks.
   VS Code's "WSL" extension opens them natively.
4. Clone tp-hub (branch `traefik-v3-rule-syntax`) to get the build kit and this document.

Building the patched images
---------------------------

[`dev/portainer-buildkit-fix/build.sh`](../dev/portainer-buildkit-fix/build.sh) clones or updates both forks side by side
under `$WORK_DIR` (default `~/src/portainer-buildkit-fix`) and checks out the test branches. It then cross-compiles the
agent and server binaries in a `golang:1.26` container and layers each onto the official `2.45.2` image, so the result
is the official image with one binary replaced. The images are:

* `mckelvie-org/portainer-agent:2.45.2-protocol-switch`
* `mckelvie-org/portainer-ce:2.45.2-buildkit-session-headers`

```bash
cd tp-hub/dev/portainer-buildkit-fix
ARCH=arm64 ./build.sh                     # builds both; writes $WORK_DIR/out/portainer-buildkit-fix-images-arm64.tar
COMPONENTS=server ARCH=arm64 ./build.sh   # server only (the agent image already exists on the hub)
```

Transfer the images to the hub:

```bash
scp ~/src/portainer-buildkit-fix/out/portainer-buildkit-fix-images-arm64.tar sam@mchub:/tmp/
ssh sam@mchub docker load -i /tmp/portainer-buildkit-fix-images-arm64.tar
```

Alternatively, set `PUSH_REGISTRY=ghcr.io/mckelvie-org` to push the images to GitHub Container Registry. That requires
`docker login ghcr.io` with a token that has `write:packages`, and the hub must be able to pull them: make the packages
public, or `docker login` on the hub. The image names in config.yml then include the registry.

The agent path of `build.sh` was verified on the Pi; the server path has not been run yet. The server binary is built the
same way as Portainer's `build/build_binary.sh`, minus build-info ldflags such as Node/pnpm versions.

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

**Current hub state.** This is a test configuration: the patched agent (with debug logging) is running, but the
workaround is still on because the server isn't patched yet:

```yaml
  portainer_stack_env:
    PORTAINER_AGENT_IMAGE: mckelvie-org/portainer-agent
    PORTAINER_AGENT_VERSION: 2.45.2-protocol-switch
    PORTAINER_DOCKER_BUILDKIT: "0"
```

**End-to-end test**, after loading both images on the hub:

1. Add `PORTAINER_IMAGE: mckelvie-org/portainer-ce` and `PORTAINER_VERSION: 2.45.2-buildkit-session-headers`, and set
   `PORTAINER_DOCKER_BUILDKIT: "1"`. Keep `PORTAINER_AGENT_VERSION` set explicitly, since otherwise it would default to
   the server's tag. Then run `hub build && hub portainer up`.
2. To make the build longer than the agent server's 120 s `ReadTimeout`, clear the BuildKit cache: `docker builder prune -af`.
3. Redeploy the jvc-projector stack (Portainer stack 3, a git stack from `github.com/sammck/jvc-projector`, currently on
   branch `modernize-docker-build`): in the Portainer UI, use "Pull and redeploy", or call the API
   (`PUT /api/stacks/3/git/redeploy?endpointId=3`, keeping the stack's env and reference; the API base is
   `http://<hub>:9000/portainer/api` with an `X-API-Key` header).
4. Success looks like:
   * the stack deployment status is OK, and the container `jvc-projector-jvc-projector-1` is recreated;
   * the Portainer log shows BuildKit-style progress (`#1 [internal] load build definition ...`) instead of `Step 1/10`,
     and the container's `com.docker.compose.image.builder` label is no longer `classic`;
   * the agent's `DEBUG proxied request` lines show `/session` requests that include the `X-Docker-Expose-Session-*`
     headers and get status 101, with no 400s;
   * no `session already exists` / `no active sessions` messages in `journalctl -u docker`;
   * `http://<hub>/jvc-projector/api/v1/` returns 200.
5. **Rollback** at any time: remove the override lines from `portainer_stack_env` (or set
   `PORTAINER_DOCKER_BUILDKIT: "0"`), then run `hub build && hub portainer up`.

Publishing upstream
-------------------

After the end-to-end test passes:

**Style requirement:** before anything is submitted, prune it to a concise, human-like form, so that maintainers are
not burdened with a verbose, obviously AI-generated PR. PR descriptions should be a few short plain paragraphs
(what breaks, why, what the fix does, how it was tested), with no headings, tables or evidence dumps; link to the issue
for details. Commit messages should be a subject line plus a few lines; the current messages on the `fix/*` branches
are too long and should be trimmed and force-pushed before opening the PRs. The issue comment should be a short
paragraph naming the two root causes and linking the PRs. Sam reviews all text before it is posted.


1. Agent PR: from `mckelvie-org/portainer-agent:fix/docker-proxy-protocol-upgrade` to `portainer/agent:develop`.
   This branch does **not** contain the debug-logging commit.
2. Server PR: from `mckelvie-org/portainer:fix/proxy-buildkit-session-headers` to `portainer/portainer:develop`.
3. Each PR should explain that BuildKit builds through an agent need both fixes, and link the other PR.
4. Comment on [portainer/portainer#13255](https://github.com/portainer/portainer/issues/13255), which Portainer has labelled
   `release/3.0.0` and tracks internally, with the root cause of both bugs, the evidence above, and links to the PRs.
   Optionally, mention [#10562](https://github.com/portainer/portainer/issues/10562).
5. Security note for the server PR: the allowlist is shared by Portainer's other proxies (Docker API, Kubernetes,
   GitLab, Azure). Forwarding the session headers grants nothing beyond the Docker API access a caller already has,
   because they only identify a BuildKit session the same caller opens.

Related state elsewhere
-----------------------

* tp-hub branch `traefik-v3-rule-syntax` (not yet merged to `main`) contains: the traefik v2/v3-neutral rules, the
  `PORTAINER_` prefixed shared variables, the `DOCKER_BUILDKIT` workaround and image overrides, these docs, and the build kit.
  The hub's untracked `config.yml` pins `traefik_version: "3.7.15"`.
* jvc-projector branch `modernize-docker-build` (pushed, not merged) contains: python 3.13 / Poetry 2 Dockerfile,
  committed `poetry.lock`, the `PORTAINER_*` variable names, and the local `jvc-projector:local` image. The Portainer stack
  deploys from this branch until it is merged; switching the stack back to `main` makes Portainer remove the stack before
  rebuilding, so expect brief downtime.
