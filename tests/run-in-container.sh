#!/usr/bin/env bash
# Build the test image and run the full pyramid inside it.
#
# Prefers podman (rootless, default on Fedora); falls back to docker.
# Pass any extra pytest args as arguments:
#
#   ./tests/run-in-container.sh -k mpd_monitor
#   ./tests/run-in-container.sh tests/unit

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="galliard-tests:latest"

if command -v podman >/dev/null 2>&1; then
    RUNTIME=podman
elif command -v docker >/dev/null 2>&1; then
    RUNTIME=docker
else
    echo "error: neither podman nor docker found on PATH" >&2
    exit 1
fi

# :Z so SELinux relabels the mount; harmless on systems without SELinux.
MOUNT_FLAGS=""
if [[ "$RUNTIME" == "podman" ]]; then
    MOUNT_FLAGS=":Z"
fi

echo "==> Building $IMAGE with $RUNTIME"
"$RUNTIME" build -t "$IMAGE" -f "$REPO_ROOT/tests/Containerfile" "$REPO_ROOT"

echo "==> Running tests"
exec "$RUNTIME" run --rm \
    -v "$REPO_ROOT:/workspace${MOUNT_FLAGS}" \
    "$IMAGE" \
    sh -c "Xvfb :99 -screen 0 1024x768x24 & sleep 0.3; exec pytest -v $*"
