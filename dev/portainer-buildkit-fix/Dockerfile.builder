# Toolchain for building Portainer CE and the Portainer Agent from source with their own Makefiles:
# Go (both), plus Node and pnpm (the server's client build, and build/build_binary.sh records their versions).
# Versions follow server-ce/package.json (engines.node, packageManager) and go.mod.
ARG GO_IMAGE=golang:1.26.6-bookworm
ARG NODE_IMAGE=node:22.22.1-bookworm-slim
ARG PNPM_VERSION=10.26.2
ARG DOCKER_CLI_IMAGE=docker:29.4-cli

FROM ${NODE_IMAGE} AS node
FROM ${DOCKER_CLI_IMAGE} AS docker

FROM ${GO_IMAGE}
ARG PNPM_VERSION
COPY --from=node /usr/local/bin/node /usr/local/bin/
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
# The docker CLI (and compose plugin) are only used by tests that deploy real stacks (pkg/libstack/compose, edge/stack)
COPY --from=docker /usr/local/bin/docker /usr/local/bin/
COPY --from=docker /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
ENV COREPACK_HOME=/opt/corepack COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN ln -s ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
 && ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && corepack enable --install-directory /usr/local/bin pnpm \
 && corepack prepare "pnpm@${PNPM_VERSION}" --activate \
 && chmod -R a+rX "$COREPACK_HOME" \
 && node -v && pnpm -v && go version
