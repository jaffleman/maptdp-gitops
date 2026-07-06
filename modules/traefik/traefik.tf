resource "helm_release" "traefik" {
  name       = "traefik"
  namespace  = "traefik"
  chart      = "traefik"
  repository = "https://traefik.github.io/charts"
  version    = "25.0.0"

  create_namespace = true

  values = [
    file("${path.module}/traefik-values.yaml")
  ]
}
