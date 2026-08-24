#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"

for command in git node npm python3 codex; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    printf 'error: required command is missing: %s\n' "${command}" >&2
    exit 2
  fi
done

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if (( NODE_MAJOR < 18 )); then
  printf 'error: Node.js 18 or newer is required\n' >&2
  exit 2
fi

if ! codex login status 2>&1 | grep -q 'Logged in using ChatGPT'; then
  printf 'error: run `codex login` with your ChatGPT account first\n' >&2
  exit 2
fi

cd "${ROOT}"
npm ci --omit=dev
mkdir -p "${BIN_DIR}"
ln -sfn "${ROOT}/bin/hill-climber" "${BIN_DIR}/hill-climber"

printf 'installed hill-climber -> %s\n' "${ROOT}"
printf 'CLI: %s/hill-climber\n' "${BIN_DIR}"
if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
  printf 'note: add %s to PATH\n' "${BIN_DIR}"
fi
