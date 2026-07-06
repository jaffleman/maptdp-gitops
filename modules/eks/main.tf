###############################################
# LOCALS
###############################################
locals {
  base_tags = merge({
    ManagedBy   = "Terraform"
    Project     = var.project_name
    Environment = var.environment
  }, var.tags)
}

###############################################
# IAM ROLE DU CLUSTER
###############################################
data "aws_iam_policy_document" "eks_cluster_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${var.cluster_name}-cluster-role"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_assume.json
  tags               = local.base_tags
}

resource "aws_iam_role_policy_attachment" "cluster_AmazonEKSClusterPolicy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role_policy_attachment" "cluster_AmazonEKS_VPCResourceController" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
}

###############################################
# CLUSTER EKS
###############################################
resource "aws_eks_cluster" "this" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.kubernetes_version

  # Auth v2 (Access Entries)
  access_config {
    authentication_mode = "API_AND_CONFIG_MAP"
  }

  vpc_config {
    subnet_ids              = var.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  tags = merge(local.base_tags, { Name = var.cluster_name })

  depends_on = [
    aws_iam_role_policy_attachment.cluster_AmazonEKSClusterPolicy,
    aws_iam_role_policy_attachment.cluster_AmazonEKS_VPCResourceController
  ]
}

###############################################
# IAM ROLE DU NODEGROUP
###############################################
data "aws_iam_policy_document" "nodegroup_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "nodegroup" {
  name               = "${var.cluster_name}-nodegroup-role"
  assume_role_policy = data.aws_iam_policy_document.nodegroup_assume.json
  tags               = local.base_tags
}

resource "aws_iam_role_policy_attachment" "node_AmazonEKSWorkerNodePolicy" {
  role       = aws_iam_role.nodegroup.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_AmazonEC2ContainerRegistryReadOnly" {
  role       = aws_iam_role.nodegroup.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "node_AmazonEKS_CNI_Policy" {
  role       = aws_iam_role.nodegroup.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_AmazonSSMManagedInstanceCore" {
  role       = aws_iam_role.nodegroup.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

###############################################
# UNIQUE NODEGROUP — SPOT + DIVERSIFICATION
###############################################
resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "default"
  node_role_arn   = aws_iam_role.nodegroup.arn
  subnet_ids      = var.private_subnet_ids

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  capacity_type  = "SPOT"
  instance_types = var.instance_types # Exemple: ["t3.large", "t3a.large", "m5.large", "m5a.large"]

  disk_size = var.disk_size
  ami_type  = "AL2023_x86_64_STANDARD" # requis pour k8s >= 1.33

  labels = {
    intent = "apps"
  }

  taint {
    key    = "spotInstance"
    value  = "true"
    effect = "PREFER_NO_SCHEDULE"
  }

  update_config {
    max_unavailable = 1
  }

  tags = local.base_tags

  depends_on = [
    aws_eks_cluster.this,
    aws_iam_role_policy_attachment.node_AmazonEKSWorkerNodePolicy,
    aws_iam_role_policy_attachment.node_AmazonEC2ContainerRegistryReadOnly,
    aws_iam_role_policy_attachment.node_AmazonEKS_CNI_Policy,
    aws_iam_role_policy_attachment.node_AmazonSSMManagedInstanceCore,
  ]
}

###############################################
# OIDC PROVIDER / IRSA — conditionnel
###############################################
data "tls_certificate" "oidc" {
  count = var.enable_post_cluster ? 1 : 0
  url   = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  count           = var.enable_post_cluster ? 1 : 0
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [one(data.tls_certificate.oidc[*].certificates[0].sha1_fingerprint)]
  tags            = local.base_tags
}

###############################################
# MANAGED ADD-ONS (gérés en update/overwrite)
###############################################
resource "aws_eks_addon" "vpc_cni" {
  cluster_name = aws_eks_cluster.this.name
  addon_name   = "vpc-cni"

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  lifecycle {
    ignore_changes = [
      addon_version,
      configuration_values
    ]
  }

  depends_on = [aws_eks_cluster.this]
}

resource "aws_eks_addon" "coredns" {
  cluster_name = aws_eks_cluster.this.name
  addon_name   = "coredns"

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  lifecycle {
    ignore_changes = [
      addon_version, # évite les conflits si AWS met à jour l’addon
      configuration_values
    ]
  }

  depends_on = [aws_eks_cluster.this]
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name = aws_eks_cluster.this.name
  addon_name   = "kube-proxy"

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  lifecycle {
    ignore_changes = [
      addon_version,
      configuration_values
    ]
  }

  depends_on = [aws_eks_cluster.this]
}

###############################################
# ACCESS ENTRIES (aws-auth V2)
###############################################
resource "aws_eks_access_entry" "gitlab_ci_deploiement" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = "arn:aws:iam::489575506572:role/Gitlab-CI-deploiement"
  type          = "STANDARD"

  lifecycle { create_before_destroy = true }
  depends_on = [aws_eks_cluster.this]
}

resource "aws_eks_access_policy_association" "gitlab_ci_deploiement_admin" {
  cluster_name  = aws_eks_cluster.this.name
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  principal_arn = "arn:aws:iam::489575506572:role/Gitlab-CI-deploiement"

  access_scope { type = "cluster" }
  lifecycle { create_before_destroy = true }
}

resource "aws_eks_access_entry" "gitlab_ci_runner" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = "arn:aws:iam::489575506572:role/GitLab-CI"
  type          = "STANDARD"

  lifecycle { create_before_destroy = true }
  depends_on = [aws_eks_cluster.this]
}

# resource "aws_eks_access_policy_association" "gitlab_ci_runner_admin" {
#   cluster_name  = aws_eks_cluster.this.name
#   policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
#   principal_arn = "arn:aws:iam::489575506572:role/GitLab-CI"

#   access_scope { type = "cluster" }
#   lifecycle { create_before_destroy = true }
# }

# resource "aws_eks_access_entry" "fatima_local" {
#   cluster_name  = aws_eks_cluster.this.name
#   principal_arn = "arn:aws:iam::489575506572:user/Fatima"
#   type          = "STANDARD"

#   lifecycle { create_before_destroy = true }
#   depends_on = [aws_eks_cluster.this]
# }

# resource "aws_eks_access_policy_association" "fatima_local_admin" {
#   cluster_name  = aws_eks_cluster.this.name
#   policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
#   principal_arn = "arn:aws:iam::489575506572:user/Fatima"

#   access_scope { type = "cluster" }
#   lifecycle { create_before_destroy = true }
# }

resource "aws_eks_access_entry" "local_admin" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = "arn:aws:iam::489575506572:user/terraform-infra"
  type          = "STANDARD"

  lifecycle { create_before_destroy = true }
  depends_on = [aws_eks_cluster.this]
}

resource "aws_eks_access_policy_association" "local_admin_policy" {
  cluster_name  = aws_eks_cluster.this.name
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  principal_arn = "arn:aws:iam::489575506572:user/terraform-infra"

  access_scope { type = "cluster" }
  lifecycle { create_before_destroy = true }
}
