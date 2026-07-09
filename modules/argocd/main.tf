
locals {
  namespace = "argocd"
}

# 1) Namespace explicite (sert de point d’ancrage statique)
resource "kubernetes_namespace" "argocd" {
  count = var.enabled ? 1 : 0

  metadata {
    name = local.namespace
    labels = {
      "app.kubernetes.io/name" = "argocd"
    }
  }
}

# 2) ArgoCD via Helm chart
resource "helm_release" "argocd" {
  count = var.enabled ? 1 : 0

  set_sensitive {
    name  = "configs.secret.argocdServerAdminPassword"
    value = var.argocd_admin_password
  }

  set_sensitive {
    name  = "configs.secret.argocdServerSecretkey"
    value = var.argocd_server_secretkey
  }

  set {
    name  = "configs.secret.argocdServerAdminPasswordMtime"
    value = var.argocd_password_mtime
  }

  name       = "argocd"
  namespace  = local.namespace
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = "6.9.0"

  # on crée quand même le ns côté Helm, sans dépendre de ça
  create_namespace = true

  # plus robuste
  atomic          = true
  cleanup_on_fail = true
  wait            = true
  timeout         = 1200

  values = [
    yamlencode({
      server = {
        service = {
          configs = {
            params = {
              "server.insecure" = "true"
            }
          }
          # ClusterIP si tu exposes via Traefik ; sinon, mets LoadBalancer
          type = "ClusterIP"
        }
      }
    })
  ]

  # >>> Dépendance statique interne au module, acceptée par Terraform
  depends_on = [
    kubernetes_namespace.argocd
  ]
}
resource "kubernetes_ingress_v1" "argocd" {
  metadata {
    name      = "argocd"
    namespace = "argocd"

    annotations = {
      "cert-manager.io/cluster-issuer" = "letsencrypt-prod"
    }
  }

  spec {
    ingress_class_name = "traefik"

    tls {
      hosts       = ["argocd.jaffleman.tech"]
      secret_name = "argocd-tls"
    }

    rule {
      host = "argocd.jaffleman.tech"

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = "argocd-server"

              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }
}
