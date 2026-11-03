#!/usr/bin/env bash
# Verify and load a locally exported image. No pull, push, pod or container.
set -euo pipefail
[[ $# == 1 ]] || { echo "Usage: $0 EXPORT_DIR" >&2; exit 2; }
cd -- "$1"
sha256sum --strict --check SHA256SUMS
id=$(cat image-id)
[[ $id =~ ^sha256:[0-9a-f]{64}$ ]]
# Check the archive itself even if this Docker daemon already has the image.
python3 - "$id" <<'PY'
import hashlib
import json
import sys
import tarfile
with tarfile.open("image.tar", "r:") as archive:
    items = json.load(archive.extractfile("manifest.json"))
    if not items or any(item.get("RepoTags") for item in items):
        sys.exit("Expected an untagged archive")
    expected = sys.argv[1]
    config_ids = set()
    for item in items:
        config = archive.extractfile(item["Config"]).read()
        config_ids.add("sha256:" + hashlib.sha256(config).hexdigest())
    if expected not in config_ids:
        # Docker's containerd store can identify an image by its OCI descriptor.
        index = json.load(archive.extractfile("index.json"))
        if expected not in {entry["digest"] for entry in index["manifests"]}:
            sys.exit("Image ID absent from archive")
        blob = archive.extractfile("blobs/sha256/" + expected.split(":")[1]).read()
        if "sha256:" + hashlib.sha256(blob).hexdigest() != expected:
            sys.exit("OCI descriptor checksum mismatch")
PY
docker --host unix:///var/run/docker.sock image load --input image.tar
loaded=$(docker --host unix:///var/run/docker.sock image inspect --format '{{.Id}}' "$id")
[[ $loaded == "$id" ]]
printf 'Verified local image %s (%s)\n' "$loaded" "$(cat source)"
