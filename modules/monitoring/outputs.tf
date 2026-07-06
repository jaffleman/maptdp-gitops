output "monitoring_namespace" {
  description = "Namespace du monitoring"
  value       = helm_release.monitoring.namespace
}

output "monitoring_status" {
  description = "Status du release Helm"
  value       = helm_release.monitoring.status
}

output "monitoring_release_name" {
  description = "Nom du release Helm"
  value       = helm_release.monitoring.name
}
