resource "kubernetes_manifest" "letsencrypt_prod" {
  count = var.enable_issuer ? 1 : 0
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata   = { name = "letsencrypt-prod" }
    spec = {
      acme = {
        email               = "sebastien@jaffleman.tech"
        server              = "https://acme-v02.api.letsencrypt.org/directory"
        privateKeySecretRef = { name = "acme-account-key" }
        solvers = [{
          http01 = {
            ingress = {
              class = "traefik"
            }
          }
        }]
      }
    }
  }

  depends_on = [
    helm_release.cert_manager,
    null_resource.wait_for_cert_manager_ready
  ]
}
