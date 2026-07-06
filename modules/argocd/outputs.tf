
output "argocd_namespace" {
  description = "Namespace où ArgoCD est installé"
  value       = try(helm_release.argocd[0].namespace, null)
}

output "argocd_release_name" {
  description = "Nom de la release Helm ArgoCD"
  value       = try(helm_release.argocd[0].name, null)
}

output "argocd_chart_version" {
  description = "Version du chart ArgoCD installé"
  value       = try(helm_release.argocd[0].version, null)
}
