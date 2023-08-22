#!/bin/bash

# optional "-f" option to force reinstall

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

FORCE=""
if [ "$1" == "-f" ]; then
    FORCE="-f"
    shift
fi

if [ -n "$FORCE" ]; then
  rm -fr "$SCRIPT_DIR/../build"
fi

. "$SCRIPT_DIR/activate"

# This will install docker along with buildx support and QEMU emulation for cross-running ARM/X86
project-init-tools install docker $FORCE "$@"

# This will install docker-compose
project-init-tools install docker-compose $FORCE "$@"

