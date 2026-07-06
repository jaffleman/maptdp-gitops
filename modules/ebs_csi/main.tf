############################################################
# EBS-CSI via IRSA (stable EKS 1.34) — PATCH OIDC
############################################################

# 1) Infos du cluster EKS
data "aws_eks_cluster" "this" {
  name = var.cluster_name
}

# 2) OIDC provider à partir de l'issuer passé en variable
data "aws_iam_openid_connect_provider" "eks" {
  url = var.cluster_oidc_issuer
}

# 3) Locals
locals {
  issuer_full     = var.cluster_oidc_issuer
  issuer_noscheme = replace(local.issuer_full, "https://", "")
  sa_namespace    = "kube-system"
  sa_name         = "ebs-csi-controller-sa"
}

# 4) Rôle IAM IRSA pour EBS-CSI
resource "aws_iam_role" "ebs_csi_irsa" {
  name = "${var.project_name}-${var.environment}-EBSCSI-IRSA"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect : "Allow",
      Principal : {
        Federated : data.aws_iam_openid_connect_provider.eks.arn
      },
      Action : "sts:AssumeRoleWithWebIdentity",
      Condition : {
        StringEquals : {
          "${local.issuer_noscheme}:aud" = "sts.amazonaws.com",
          "${local.issuer_noscheme}:sub" = "system:serviceaccount:${local.sa_namespace}:${local.sa_name}"
        }
      }
    }]
  })
}

# 5) Attache la policy managée AWS du driver EBS-CSI
resource "aws_iam_role_policy_attachment" "ebs_csi_irsa_policy" {
  role       = aws_iam_role.ebs_csi_irsa.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# 6) Addon EBS-CSI avec le rôle IRSA
resource "aws_eks_addon" "ebs_csi" {
  cluster_name                = var.cluster_name # <-- ✅ utiliser la variable
  addon_name                  = "aws-ebs-csi-driver"
  resolve_conflicts_on_update = "OVERWRITE"
  service_account_role_arn    = aws_iam_role.ebs_csi_irsa.arn

  depends_on = [
    aws_iam_role.ebs_csi_irsa,
    aws_iam_role_policy_attachment.ebs_csi_irsa_policy
  ]
}
