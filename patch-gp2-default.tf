# patch-gp2-default.tf (version corrigée, prête à coller)
resource "null_resource" "unset_gp2_default" {
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-lc"]
    command     = <<-BASH
      set -euo pipefail

      # Si la SC gp2 existe
      if kubectl get storageclass gp2 >/dev/null 2>&1; then
        # Lire l'annotation "is-default-class" (si absente, 'current' sera vide)
        current="$(kubectl get storageclass gp2 -o jsonpath='{.metadata.annotations.storageclass\\.kubernetes\\.io/is-default-class}' 2>/dev/null || true)"

        # Si elle vaut "true", on retire l'annotation
        if [ -n "$current" ] && [ "$current" = "true" ]; then
          kubectl annotate storageclass gp2 storageclass.kubernetes.io/is-default-class=false --overwrite
        fi
      fi
    BASH
  }

  depends_on = [
    kubernetes_storage_class_v1.gp3
  ]
}
