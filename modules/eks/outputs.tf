output "cluster_name" {
  value = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "cluster_version" {
  value = aws_eks_cluster.this.version
}

output "cluster_oidc_provider_arn" {
  description = "ARN du provider OIDC (null si non activé)"
  value       = var.enable_post_cluster ? one(aws_iam_openid_connect_provider.eks[*].arn) : null
}

output "nodegroup_name" {
  value = aws_eks_node_group.default.node_group_name
}

output "node_role_arn" {
  value = aws_iam_role.nodegroup.arn
}

output "cluster_security_group_id" {
  description = "Security Group primaire du cluster EKS"
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "cluster_arn" {
  value = aws_eks_cluster.this.arn
}

output "cluster_oidc_issuer" {
  description = "URL de l'issuer OIDC du cluster"
  value       = aws_eks_cluster.this.identity[0].oidc[0].issuer
}


output "cluster_certificate_authority_data" {
  value = aws_eks_cluster.this.certificate_authority[0].data
}
# output "kubeconfig" {
#   value     = module.eks.kubeconfig
#   sensitive = true
# }
