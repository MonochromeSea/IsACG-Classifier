#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

render_device="$(find /dev/dri -maxdepth 1 -name 'renderD*' -print -quit 2>/dev/null || true)"
if [ -z "${ISACG_RENDER_GID:-}" ] && [ -n "$render_device" ]; then
  ISACG_RENDER_GID="$(stat -c '%g' "$render_device")"
  export ISACG_RENDER_GID
fi

docker compose -f docker-compose.yml -f docker-compose.vulkan.yml up -d --build
