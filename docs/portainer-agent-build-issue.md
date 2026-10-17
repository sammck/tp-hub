Known issue: Portainer cannot build stack images through the Portainer Agent
===========================================================================

*Investigated 2026-10-16 on Portainer CE 2.45.2 / Portainer Agent 2.45.2 / Docker Engine 29.9.1 (Raspberry Pi 5, Ubuntu 22.04).*

Summary
-------

A Portainer stack whose docker-compose.yml contains a `build:` section fails to deploy when the target
environment is connected through the Portainer Agent, which is how tp-hub connects Portainer to the hub host.
The same stack deploys fine on an environment that Portainer reaches directly through the Docker socket.

There are two independent bugs. BuildKit, Docker's default builder, needs both of them fixed:

1. **Portainer Agent:** its Docker API proxy does not relay HTTP protocol upgrades (`101 Switching Protocols`),
   which BuildKit requires. This bug has been reported upstream since 2023 (see [References](#references)).
2. **Portainer server (since 2.31.0):** the header allowlist in its internal proxy to agent environments drops
   BuildKit's `X-Docker-Expose-Session-*` headers, so build sessions reach Docker without an ID.

**Workaround:** set `DOCKER_BUILDKIT=0` in the Portainer server container's environment, so that builds use
Docker's classic builder, which needs neither a protocol upgrade nor build sessions.

Fixes for both bugs are written and partly verified. See
[portainer-buildkit-fix-handoff.md](portainer-buildkit-fix-handoff.md).

Symptoms
--------

Deploying or redeploying the stack fails, and the container is left as it was:

```text
failed to deploy a stack: compose build operation failed: listing workers for Build: failed to list workers:
Unavailable: connection error: desc = "error reading server preface: http2: failed reading the frame payload:
http2: frame too large, note that the frame header looked like an HTTP/1.1 header"
```

At the same moment, the Portainer Agent (`portainer-portainer_agent-1`) logs one warning each for the BuildKit
`/session` and `/grpc` requests:

```text
WRN github.com/portainer/agent/http/proxy/local.go:51 > Error copying response body from proxied request
    error="http: request method or response status code does not allow body"
```

Portainer may also log `Docker Compose is configured to build using Bake, but buildx isn't installed` just before
the failure. That message is harmless: compose then falls back to its built-in BuildKit client, which is the step that fails.

Root cause
----------

1. Portainer runs `docker compose` in-process, using the compose library in the Portainer server. For an
   agent environment, every Docker API call goes Portainer server → Portainer Agent → Docker socket on the target host.
2. Compose v2.40.3, as bundled in Portainer 2.45.2, builds with BuildKit by default. BuildKit opens its `/session` and
   `/grpc` channels by asking the Docker daemon to upgrade the HTTP/1.1 connection to HTTP/2 (h2c). The daemon
   answers `HTTP/1.1 101 Switching Protocols`.
3. The agent's proxy
   ([`http/proxy/local.go`](https://github.com/portainer/agent/blob/2.45.2/http/proxy/local.go))
   is a plain request/response relay. It forwards the status line and headers, then tries to `io.Copy` the body.
   It has no special handling for `101`, so the copy fails ("does not allow body") and the connection is never
   handed over as a raw byte stream. (The agent handles `exec` and `attach` hijacks separately, through websockets,
   so those features work.)
4. The BuildKit client, already expecting HTTP/2 frames, reads the relayed `HTTP/1.1 101 ...` text as an HTTP/2
   frame header, which produces "frame too large, note that the frame header looked like an HTTP/1.1 header".

With the agent fixed, the build gets further, then hits the second bug:

5. Compose in the Portainer server reaches an agent environment through a small local reverse proxy that Portainer
   starts for each agent environment
   ([`api/http/proxy/factory/agent.go`](https://github.com/portainer/portainer/blob/2.45.2/api/http/proxy/factory/agent.go)).
   Since 2.31.0, that proxy deletes every request header that is not on an allowlist
   ([`reverse_proxy.go`](https://github.com/portainer/portainer/blob/2.45.2/api/http/proxy/factory/reverse_proxy.go)).
   The allowlist includes `Connection` and `Upgrade`, but not BuildKit's `X-Docker-Expose-Session-Uuid`, `-Name`,
   `-Sharedkey` and `-Grpc-Method` headers.
6. The Docker daemon therefore registers the build session with an empty ID. The build cannot find its session
   (`failed to read dockerfile: no active sessions` in the daemon log), and the next session is rejected with
   `400 {"message":"session  already exists"}`. Compose reports this as
   `failed to dial gRPC: unable to upgrade to h2c, received 400`.

Docker's classic builder sends the build context as a plain `POST /build` request and streams back an ordinary
response. It uses neither a protocol upgrade nor sessions, so both proxies relay it correctly.

Why it appeared after upgrading Portainer
-----------------------------------------

Portainer 2.19 deployed stacks by running `docker-compose up -d`
([2.19.0 composeplugin.go](https://github.com/portainer/portainer/blob/2.19.0/pkg/libstack/compose/internal/composeplugin/composeplugin.go)).
That only builds an image when it is missing locally, so a stack whose image was already present (for example,
pulled from Docker Hub) never built anything through the agent.

Portainer 2.45 calls compose `Build` before `Up` on every deploy
([2.45.2 composeplugin.go](https://github.com/portainer/portainer/blob/2.45.2/pkg/libstack/compose/composeplugin.go)).
As a result, every stack with a `build:` section now builds, and fails, on every deploy, even when the image already exists.
This is consistent with upstream reports such as "the same code deploys on 2.19.4 but fails on 2.25.1". We
checked only 2.19.0 and 2.45.2, not the exact release in which the behavior changed.

Why most Portainer users don't see it
-------------------------------------

All three of these must be true:

* The environment is connected through the Portainer Agent, not the Docker socket or the Docker API. tp-hub uses
  the agent deliberately, so the same Portainer manager can control additional, possibly remote, hosts.
* The stack has a `build:` section.
* Portainer is a version that always builds on deploy (2.45 does; 2.19 did not).

Workaround
----------

Add `DOCKER_BUILDKIT: "0"` to the environment of the **Portainer server** service, not the agent, in
`stacks/portainer/docker-compose.yml`, then run `hub portainer up`. The setting covers builds on every
environment Portainer manages, including remote agent hosts, because the compose build runs inside the
Portainer server.

Caveats:

* The classic builder is deprecated by Docker. Docker Engine 29 still supports it, but a future release may remove it.
* Dockerfiles that use BuildKit-only features fail with the classic builder. Examples are `RUN --mount=...`
  (cache, secret and ssh mounts) and `COPY --chmod`. Builds are also generally slower.
* Remove the setting once Portainer ships fixes for both bugs (see [Status](#status)). In tp-hub the value comes from
  `PORTAINER_DOCKER_BUILDKIT` (default `0`), which can be set in `config.yml` under `portainer_stack_env`.

Alternatives that were considered:

* Manage the hub host through a local Docker-socket environment instead of the agent. BuildKit works there, but this
  gives up the multi-host agent design, so tp-hub rejects it.
* Remove `build:` and use only prebuilt registry images. That loses Portainer's "pull from git and rebuild" workflow.

Status
------

* **Upstream:** open. [portainer/portainer#13255](https://github.com/portainer/portainer/issues/13255) is labelled
  `kind/bug` and `release/3.0.0` and is linked to Portainer's internal tracker. As of 2026-10-16 no
  fix has been released, and no pull request addresses it in either `portainer/portainer` or `portainer/agent`.
  None of the upstream threads identify either root cause.
* **tp-hub:** the `DOCKER_BUILDKIT=0` workaround is set in `stacks/portainer/docker-compose.yml`. Verified 2026-10-16:
  a git stack ([sammck/jvc-projector](https://github.com/sammck/jvc-projector)) was built by Portainer through the agent
  with the classic builder and deployed successfully. Note that changing a git stack's branch or reference makes Portainer
  remove the stack *before* building, so the service is down for the length of the build.
* **Fixes in progress** (see [portainer-buildkit-fix-handoff.md](portainer-buildkit-fix-handoff.md)):
  * agent: on `101 Switching Protocols`, hijack the client connection and relay bytes in both directions.
    Verified live on the hub.
  * server: add the four `X-Docker-Expose-Session-*` headers to the proxy allowlist. Unit-tested; end-to-end test pending.

References
----------

Upstream issues:

* [portainer/portainer#10562](https://github.com/portainer/portainer/issues/10562): "error reading server preface: http2: frame too large".
  Open since 2023-10, with many reports across CE and BE 2.19–2.33. The `DOCKER_BUILDKIT: 0` workaround is confirmed in the comments (May 2025).
* [portainer/portainer#13255](https://github.com/portainer/portainer/issues/13255): "Git-based stack deployment with `build:` fails via
  Portainer Agent, succeeds via local Docker socket". Open, 2026-08, labelled `release/3.0.0`.
* [portainer/portainer#12754](https://github.com/portainer/portainer/issues/12754): "Builder issues with stacks throwing 'unable to
  upgrade to tcp, receive 200' error". Possibly related; not reviewed in detail.
* [portainer/portainer#7254](https://github.com/portainer/portainer/issues/7254) and
  [portainer/portainer#4753](https://github.com/portainer/portainer/issues/4753): older reports of builds failing on agent environments.

Source code:

* [portainer/agent `http/proxy/local.go` (2.45.2)](https://github.com/portainer/agent/blob/2.45.2/http/proxy/local.go): the agent's Docker socket proxy.
* [portainer/portainer `api/http/proxy/factory/reverse_proxy.go` (2.45.2)](https://github.com/portainer/portainer/blob/2.45.2/api/http/proxy/factory/reverse_proxy.go): the header allowlist.
* [moby/buildkit `session/session.go` (v0.25.1)](https://github.com/moby/buildkit/blob/v0.25.1/session/session.go): the `X-Docker-Expose-Session-*` header names.
* [portainer/portainer `pkg/libstack/compose/composeplugin.go` (2.45.2)](https://github.com/portainer/portainer/blob/2.45.2/pkg/libstack/compose/composeplugin.go): `Build` before `Up` on every deploy.
* [portainer/portainer `composeplugin.go` (2.19.0)](https://github.com/portainer/portainer/blob/2.19.0/pkg/libstack/compose/internal/composeplugin/composeplugin.go): `docker-compose up -d`, which builds only missing images.
* [docker/compose `pkg/compose/build.go` (v2.40.3)](https://github.com/docker/compose/blob/v2.40.3/pkg/compose/build.go): uses the classic builder when BuildKit is disabled by `DOCKER_BUILDKIT=0`.
