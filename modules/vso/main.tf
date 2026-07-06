
resource "helm_release" "vault_secrets_operator" {
  name             = "vault-secrets-operator"
  namespace        = "vault"
  create_namespace = true
  repository       = "https://helm.releases.hashicorp.com"
  chart            = "vault-secrets-operator"
}