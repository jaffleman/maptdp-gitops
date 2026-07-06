

resource "kubernetes_service_account" "vault_reviewer" {
  metadata {
    name      = "vault-reviewer"
    namespace = "kube-system"
  }
}

resource "kubernetes_cluster_role_binding" "vault_reviewer" {
  metadata {
    name = "vault-reviewer"
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = "system:auth-delegator"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.vault_reviewer.metadata[0].name
    namespace = "kube-system"
  }
}

resource "kubernetes_secret_v1" "vault_reviewer_token" {
  metadata {
    name      = "vault-reviewer-token"
    namespace = "kube-system"

    annotations = {
      "kubernetes.io/service-account.name" = kubernetes_service_account.vault_reviewer.metadata[0].name
    }
  }

  type = "kubernetes.io/service-account-token"

  depends_on = [
    kubernetes_service_account.vault_reviewer
  ]
}

resource "vault_kubernetes_auth_backend_config" "eks" {

  backend = "k8s-prod"

  kubernetes_host = var.cluster_endpoint

  kubernetes_ca_cert = base64decode(
    var.cluster_ca_data
  )

  token_reviewer_jwt = kubernetes_secret_v1.vault_reviewer_token.data["token"]

  disable_iss_validation = true

  depends_on = [
    kubernetes_cluster_role_binding.vault_reviewer,
    kubernetes_secret_v1.vault_reviewer_token
  ]
}
