#!/usr/bin/env bash
set -euo pipefail

ANSIBLE_DIR="$HOME/maptdp-gitops"
PLAYBOOK="playbooks/k3s_platform.yml"
START_AT=""
SECRET_ID=""
ROLE_ID=""
MODE="full"
SKIP_WAIT=false
VERBOSE=false
DRY_RUN=false

# -------------------------
# HELP
# -------------------------
show_help() {
  cat <<EOF
🔥 Phoenix - Infra Bootstrap CLI

Usage:
  ./phoenix.sh [options]

Modes:
  --clean-only             Run only VPS cleanup
  --ansible-only           Run only Ansible playbook

Options:
  --start-at <task>        Start Ansible at a specific task
  --secret-id <id>         Inject Vault global_vault_secret_id
  --role-id <id>           Inject Vault global_vault_role_id
  --skip-wait              Skip waiting time
  --verbose                Enable verbose Ansible logs (-vv)
  --dry-run                Run Ansible in check mode (no changes)
  -h, --help               Show this help message

Notes:
  Si --role-id n'est pas fourni (et que le mode inclut Ansible),
  le script le demandera de façon interactive.

Examples:
  ./phoenix.sh
  ./phoenix.sh --clean-only
  ./phoenix.sh --ansible-only
  ./phoenix.sh --start-at "Install ArgoCD"
  ./phoenix.sh --secret-id abc123 --role-id def456
  ./phoenix.sh --ansible-only --verbose
  ./phoenix.sh --dry-run
  ./phoenix.sh --skip-wait --secret-id xyz
EOF
}

# -------------------------
# ARG PARSING
# -------------------------
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --clean-only)
      MODE="clean"
      shift
      ;;
    --ansible-only)
      MODE="ansible"
      shift
      ;;
    --start-at)
      [[ $# -ge 2 ]] || { echo "❌ --start-at nécessite une valeur"; exit 1; }
      START_AT="$2"
      shift 2
      ;;
    --secret-id)
      [[ $# -ge 2 ]] || { echo "❌ --secret-id nécessite une valeur"; exit 1; }
      SECRET_ID="$2"
      shift 2
      ;;
    --role-id)
      [[ $# -ge 2 ]] || { echo "❌ --role-id nécessite une valeur"; exit 1; }
      ROLE_ID="$2"
      shift 2
      ;;
    --skip-wait)
      SKIP_WAIT=true
      shift
      ;;
    --verbose)
      VERBOSE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

echo "🔥 Phoenix mode: $MODE"

# -------------------------
# GARDE-FOU : --start-at ne doit JAMAIS déclencher un reinstall du VPS
# -------------------------
if [[ -n "$START_AT" && "$MODE" == "full" ]]; then
  echo "ℹ️  --start-at détecté : passage automatique en mode ansible-only."
  echo "ℹ️  Le nettoyage/reinstall du VPS est ignoré pour éviter de tout écraser."
  MODE="ansible"
fi

# -------------------------
# CLEAN
# -------------------------
if [[ "$MODE" == "full" || "$MODE" == "clean" ]]; then
  echo "🧹 Cleaning VPS..."
  if [[ ! -f "$HOME/lib/clean_vps.sh" ]]; then
    echo "❌ Fichier introuvable: $HOME/lib/clean_vps.sh"
    exit 1
  fi
  # shellcheck source=/dev/null
  source "$HOME/lib/clean_vps.sh"

  if ! declare -f clean_vps >/dev/null; then
    echo "❌ La fonction clean_vps() n'est pas définie dans clean_vps.sh"
    exit 1
  fi
  clean_vps
fi

# exit if clean-only
if [[ "$MODE" == "clean" ]]; then
  echo "✅ Clean completed"
  exit 0
fi

# -------------------------
# WAIT
# -------------------------
if [[ "$MODE" == "full" && "$SKIP_WAIT" == false ]]; then
  echo "⏳ Waiting 10 seconds..."
  sleep 10
elif [[ "$SKIP_WAIT" == true ]]; then
  echo "⚡ Skipping wait"
fi

# -------------------------
# ANSIBLE PREREQUIS
# -------------------------
if [[ ! -d "$ANSIBLE_DIR" ]]; then
  echo "❌ Dossier Ansible introuvable: $ANSIBLE_DIR"
  exit 1
fi

echo "📂 Moving to Ansible directory..."
cd "$ANSIBLE_DIR"

if [[ ! -f "$PLAYBOOK" ]]; then
  echo "❌ Playbook introuvable: $ANSIBLE_DIR/$PLAYBOOK"
  exit 1
fi

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "❌ ansible-playbook n'est pas installé ou introuvable dans le PATH"
  exit 1
fi

# -------------------------
# DEMANDE INTERACTIVE DU ROLE_ID / SECRET_ID
# -------------------------
DEFAULT_ROLE_ID="5e295cf4-d749-4518-8342-3b723f642501"

if [[ -z "$ROLE_ID" ]]; then
  read -r -p "🔑 Entrez le Vault role_id [Entrée = défaut: $DEFAULT_ROLE_ID]: " ROLE_ID
  if [[ -z "$ROLE_ID" ]]; then
    ROLE_ID="$DEFAULT_ROLE_ID"
    echo "ℹ️  Utilisation du role_id par défaut."
  fi
fi

if [[ -z "$SECRET_ID" ]]; then
  echo "🔒 Entrez le Vault secret_id (saisie masquée)"
  echo "   Pour le récupérer : vault write -f auth/approle/role/ansible-vps/secret-id"
  read -r -s -p "> " SECRET_ID
  echo
  if [[ -z "$SECRET_ID" ]]; then
    echo "❌ Le secret_id est obligatoire pour lancer le playbook."
    exit 1
  fi
fi

# -------------------------
# CONSTRUCTION DE LA COMMANDE (tableau, pas d'eval)
# -------------------------
CMD=(ansible-playbook "$PLAYBOOK")

if [[ -n "$START_AT" ]]; then
  CMD+=(--start-at-task "$START_AT")
fi

CMD+=(-e "vault_ansible_role_id=$ROLE_ID")
CMD+=(-e "vault_ansible_secret_id=$SECRET_ID")

if [[ "$VERBOSE" == true ]]; then
  CMD+=(-vv)
fi

if [[ "$DRY_RUN" == true ]]; then
  CMD+=(--check)
fi

echo "🚀 Running: ${CMD[*]//$SECRET_ID/******}"

"${CMD[@]}" | tee phoenix.log

echo "✅ Done"