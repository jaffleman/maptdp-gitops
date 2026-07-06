output "reviewer_service_account" {
  value = kubernetes_service_account.vault_reviewer.metadata[0].name
}
