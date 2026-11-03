#!/usr/bin/env bash
# Export one observed Docker Hub digest for the local Linux/amd64 PRA.
set -euo pipefail
umask 077
[[ $# == 2 ]] || { echo "Usage: $0 docker.io/REPO@sha256:DIGEST OUTPUT_DIR" >&2; exit 2; }
source_ref=$1
[[ $source_ref =~ ^docker\.io/([a-z0-9._-]+/)*[a-z0-9._-]+@sha256:[a-f0-9]{64}$ ]] || { echo "Expected a pinned Docker Hub reference" >&2; exit 2; }
mkdir -p -- "$2"
output=$(realpath -- "$2")
target="$output/${source_ref##*:}"
[[ ! -e $target ]] || { echo "Existing export: verify it or choose another output directory" >&2; exit 1; }
stage=$(mktemp -d -- "$output/.export.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT
mkdir "$stage/client"
# No host Docker credentials, credential helpers, remote contexts or plugins.
printf '%s\n' '{"auths":{"unused.invalid":{}}}' > "$stage/client/config.json"
docker_bin=$(command -v docker)
local_docker() { env -i PATH=/nonexistent HOME="$stage/client" "$docker_bin" --config "$stage/client" --host unix:///var/run/docker.sock "$@"; }
local_docker pull --platform linux/amd64 "$source_ref"
id=$(local_docker image inspect --format '{{.Id}}' "$source_ref")
platform=$(local_docker image inspect --format '{{.Os}}/{{.Architecture}}' "$source_ref")
[[ $platform == linux/amd64 && $id =~ ^sha256:[0-9a-f]{64}$ ]]
local_docker image save --output "$stage/image.tar" "$id"
printf '%s\n' "$source_ref" > "$stage/source"
printf '%s\n' "$id" > "$stage/image-id"
(cd "$stage" && sha256sum image.tar image-id source > SHA256SUMS)
rm -f -- "$stage/client/config.json"
rmdir "$stage/client"
# Atomic publication; concurrent successful exports must not overwrite each other.
mv -Tn -- "$stage" "$target"
[[ ! -e "$stage" ]] || { echo "Destination already published" >&2; exit 1; }
printf 'Exported %s to %s\n' "$source_ref" "$target"
