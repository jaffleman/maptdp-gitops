#!/usr/bin/env bash
set -euo pipefail

# -----------------
# CONFIG CHECK
# -----------------
: "${GITLAB_API_V4_URL:?Missing GitLab API URL}"
: "${GITLAB_TOKEN:?Missing GitLab Group Deploy Token}"
: "${GROUP_ID_OR_PATH:?Missing GitLab Group path or ID}"
: "${ROLE:?Missing GitLab Group Role ARN}"

# -----------------
# API HELPERS
# -----------------
exists_var() {
  local key="$1"
  curl -sSf -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    "${GITLAB_API_V4_URL}/groups/${GROUP_ID_OR_PATH}/variables/${key}" \
    >/dev/null 2>&1
}

create_var() {
  local key="$1"
  local value="$2"
  curl -sS -X POST \
    -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    "${GITLAB_API_V4_URL}/groups/${GROUP_ID_OR_PATH}/variables" \
    --form "key=${key}" \
    --form "value=${value}" \
    --form "variable_type=env_var" \
    --form "masked=false" \
    --form "protected=false"
}

update_var() {
  local key="$1"
  local value="$2"
  curl -sS -X PUT \
    -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    "${GITLAB_API_V4_URL}/groups/${GROUP_ID_OR_PATH}/variables/${key}" \
    --form "value=${value}" \
    --form "variable_type=env_var" \
    --form "masked=false" \
    --form "protected=false"
}

upsert() {
  local key="$1"
  local value="$2"

  if exists_var "$key"; then
    echo "[UPDATE] $key"
    update_var "$key" "$value"
  else
    echo "[CREATE] $key"
    create_var "$key" "$value"
  fi
}

# -----------------
# PUSH VARIABLES
# -----------------
echo "=== Mise à jour des variables EKS ==="
upsert "EKS_CLUSTER_NAME"  "${CLUSTER_NAME}"
upsert "REGION"            "${REGION}"
upsert "ROLE_ARN"          "${ROLE}"

echo "=== Mise à jour des variables RDS ==="
upsert "RDS_ENDPOINT"      "${RDS_ENDPOINT}"
upsert "RDS_DB_NAME"       "${RDS_DB_NAME}"
upsert "RDS_USERNAME"      "${RDS_USERNAME}"
upsert "RDS_PORT"          "${RDS_PORT}"

echo "[OK] Toutes les variables de groupe mises à jour."