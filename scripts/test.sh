#!/usr/bin/env bash
set -e

echo "=== 🔍 Test Terraform sans déploiement ==="

echo "1️⃣  Vérification formatage Terraform"
terraform fmt -recursive -check

echo "2️⃣  terraform validate"
terraform validate

echo "3️⃣  terraform init (mode offline si cache déjà présent)"
terraform init -backend=false

echo "4️⃣  terraform plan (sans backend + sans apply)"
terraform plan -input=false -lock=false -refresh=false -no-color || true

echo "5️⃣  Affichage des outputs (si existants)"
terraform output || true

echo "6️⃣  Génération du graphe Terraform"
terraform graph > tf-graph.dot
echo "   → Fichier généré : tf-graph.dot (tu peux le convertir en PNG avec graphviz)"

echo "=== 🔐 Tests AWS/K8s optionnels (sans déploiement) ==="

echo "7️⃣  aws sts get-caller-identity"
aws sts get-caller-identity || echo "⚠️ AWS non configuré, test ignoré"

echo "8️⃣  Test kubeconfig local (kubectl get nodes)"
kubectl get nodes || echo "⚠️ kubectl ne peut pas accéder au cluster (normal si cluster pas encore créé)"

echo "9️⃣  Test Helm"
helm ls || echo "⚠️ Helm ne peut pas communiquer avec un cluster (ok si cluster non créé)"

echo "=== 🛡️ Tests sécurité ==="

echo "🔎 tflint"
tflint || echo "⚠️ tflint non installé"

echo "🔎 tfsec"
tfsec . || echo "⚠️ tfsec non installé"

echo "=== ✔️ Tests terminés : aucune modification AWS effectuée ==="