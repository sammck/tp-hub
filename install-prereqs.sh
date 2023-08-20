#!/bin/bash

# optional "-f" option to force reinstall

set -e
#set -x

VPYAPP_URL="https://raw.githubusercontent.com/sammck/vpyapp/latest/vpyapp.py"
#VPYAPP_URL="https://s3.us-west-2.amazonaws.com/public.mckelvie.org/vpyapp.py"

PROJECT_INIT_TOOLS="git+https://github.com/sammck/project-init-tools.git@main"

vpyapp() {
    if [ -n "$DEBUG" ]; then
        echo 'Running: [curl -sSL '"$(printf "%q" "$VPYAPP_URL")"' | python3 -'"$(printf ' %q' "$@")"']' >&2
    fi
    curl -sSL "$VPYAPP_URL" | python3 - "$@"
    return $?
}

project-init-tools() {
    vpyapp run "$PROJECT_INIT_TOOLS" project-init-tools "$@"
    return $?
}

FORCE=""
if [ "$1" == "-f" ]; then
    FORCE="-f"
    shift
fi

if [ -n "$FORCE" ]; then
  vpyapp uninstall "$PROJECT_INIT_TOOLS" 2>/dev/null || true
fi

if [ -n "$DEBUG" ]; then
  # build project-init-tools under ~/.cache/vpyapp if necessary, displaying build output
  vpyapp install "$PROJECT_INIT_TOOLS"
fi

# This will install docker along with buildx support and QEMU emulation for cross-running ARM/X86
project-init-tools install docker $FORCE "$@"

# This will install docker-compose
project-init-tools install docker-compose $FORCE "$@"
