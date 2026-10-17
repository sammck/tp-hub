Upstream drafts: BuildKit builds through the Portainer Agent
===========================================================

Drafts for Sam to review before anything is posted. Nothing here has been submitted.

**Order of posting**

1. Open the agent PR (§1). Note its number.
2. Open the server PR (§2), with the agent PR number filled in.
3. Edit the agent PR description to fill in the server PR number.
4. Post the #13255 comment (§3), then #12754 (§4) and #10562 (§5).

`<agent PR>` and `<server PR>` are placeholders for those numbers. #13255 carries the full explanation; the PRs stay
short and point to it.

**Facts the drafts rely on** (verified 2026-10-17)

* Both GitHub repos mirror Portainer's internal monorepo. Staff port external PRs internally rather than merge them
  (e.g. predlac on portainer/portainer#13300: "we'll need to port this upstream"). That's why the PRs offer to be ported.
* #13255 is tracked internally (FR-1176, label release/3.0.0, assigned andres-portainer). #12754 is FR-705.
* Every non-socket environment (agent, Docker API over TCP) deploys stacks through `CreateAgentProxyServer`, which uses
  the allowlisted reverse proxy (`api/exec/common.go` `fetchEndpointProxy`, `api/http/proxy/factory/agent.go`).
* The allowlist is in 2.27.7–2.27.9 LTS and 2.31.0+, not in 2.29.2. `Connection`/`Upgrade` were allowed from 2.33.0
  (bdb2e2f41). `X-Docker-Expose-Session-*` is still missing on develop.
* Tested only through an agent environment (2.45.2, arm64), not a Docker API one.
* `local.go` and `reverse_proxy.go` are identical on 2.45.2 and develop, so the patches were tested on 2.45.2
  (agent develop doesn't build against portainer develop).

---

1. PR to portainer/agent (base `develop`)
----------------------------------------

**From:** `mckelvie-org/portainer-agent:fix/docker-proxy-protocol-upgrade`

**Title:** fix(proxy): relay protocol-switching responses from the Docker daemon

**Body:**

> The local Docker proxy (`http/proxy/local.go`) copies every daemon response as an ordinary body, including
> `101 Switching Protocols`. BuildKit's h2c upgrade of `/grpc` and `/session` therefore never gets the upgraded
> connection, and stacks with a `build:` section fail on agent environments with `http2: frame too large`.
>
> On a 101 response, this hijacks the client connection, relays the response, and copies bytes in both directions until
> either side closes. It also clears the connection deadlines, which would otherwise cut builds off after the server's
> 120 s timeout. `TestLocalProxyRelaysProtocolSwitch` covers it; it times out on the current code.
>
> Agent builds also need portainer/portainer#&lt;server PR&gt;. Background and test details are in
> portainer/portainer#13255. Happy for this to be ported internally if that's easier.

---

2. PR to portainer/portainer (base `develop`)
---------------------------------------------

**From:** `mckelvie-org/portainer:fix/proxy-buildkit-session-headers`

**Title:** fix(proxy): forward BuildKit session headers to Docker environments

**Body:**

> The proxy header allowlist (BE-11819, 2.31.0) drops the `X-Docker-Expose-Session-*` headers that BuildKit sends to
> the daemon's `/session` endpoint. The daemon then registers each build session without an ID, so stacks with a
> `build:` section fail with `no active sessions` or `unable to upgrade to h2c, received 400`.
>
> This adds the four session headers to the allowlist, with a case in `Test_createRewriteFn`. The allowlist is shared
> with the other proxies, but these headers only name a session the caller opens itself, so they grant nothing beyond
> the Docker API access the caller already has.
>
> Agent environments also need portainer/agent#&lt;agent PR&gt;. Background and test details are in #13255. Docker API
> environments use the same proxy, which likely explains #12754, though I've only tested through an agent.
>
> Relates to #13255, #12754, #10562.

---

3. Comment on portainer/portainer#13255
---------------------------------------

> I tracked this down to two bugs, one in the agent and one in the server, and opened fixes for both.
>
> 1. The agent's Docker proxy doesn't relay the daemon's `101 Switching Protocols`. BuildKit opens `/grpc` and
>    `/session` with an h2c upgrade, so the client gets the raw HTTP/1.1 response where it expects HTTP/2, hence the
>    "frame too large" error. Fixed in portainer/agent#&lt;agent PR&gt;.
> 2. Since 2.31.0 the server's proxy allowlist drops BuildKit's `X-Docker-Expose-Session-*` headers. With the agent
>    fixed, the daemon then sees build sessions without an ID and the build fails with
>    `unable to upgrade to h2c, received 400`. Fixed in #&lt;server PR&gt;.
>
> Agent environments need both. This isn't specific to Git stacks; any stack with `build:` is affected. I tested both
> patches on 2.45.2 (arm64) with BuildKit: a Git stack redeploy, and a build with a 150 s step, which also checks that
> long builds aren't cut off by the agent's 120 s timeout. Until a release has the fixes, `DOCKER_BUILDKIT=0` on the
> Portainer server container works around it, for Dockerfiles that don't need BuildKit features like `RUN --mount`.

*Optional last paragraph, only if Sam wants to offer test images publicly:*

> If anyone wants to try it on arm64, there are unofficial images built from those branches:
> `sammck/portainer-ce:2.45.2-buildkit-fix` and `sammck/portainer-agent:2.45.2-buildkit-fix`.

---

4. Comment on portainer/portainer#12754
---------------------------------------

> I think this one comes from the server's proxy header allowlist (BE-11819), added in 2.31.0 and the 2.27 LTS line.
> 2.29.2 doesn't have it, which fits rolling back to 2.29.2 helping. Docker API and agent environments both deploy
> stacks through that proxy.
>
> Before 2.33.0 the allowlist didn't include `Connection`/`Upgrade`, so every upgrade got a plain 200. buildx's
> `/grpc` probe fails, it falls back to the docker-container driver, and attaching to that container fails with
> `unable to upgrade to tcp, received 200`. 2.33.0 allowed those headers, but `X-Docker-Expose-Session-*` is still
> dropped, which gives the `unable to upgrade to h2c, received 400` reported here on 2.33.1.
>
> #&lt;server PR&gt; adds the session headers; more in #13255. I've only tested it on an agent environment (which also
> needs portainer/agent#&lt;agent PR&gt;), so a confirmation from someone with a Docker API environment would help.

---

5. Comment on portainer/portainer#10562
---------------------------------------

> For anyone still hitting this on an agent environment: the cause is that the agent's Docker proxy doesn't relay the
> daemon's protocol upgrade, which BuildKit needs. Fixes are in portainer/agent#&lt;agent PR&gt; and, for 2.31.0 and
> later, #&lt;server PR&gt;. Details in #13255.
