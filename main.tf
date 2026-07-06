########################################
# LOCALS
########################################

locals {
  cluster_name = "${var.project_name}-eks-${var.environment}"

  common_tags = {
    Owner       = "OFS-DevOps"
    Environment = var.environment
  }
}

########################################
# VAULT SECRETS
########################################

data "vault_kv_secret_v2" "rds" {
  mount = "kv-aws"
  name  = "maptdp/prod/rds-config"
}

data "vault_kv_secret_v2" "argocd" {
  mount = "kv-aws"
  name  = "maptdp/${var.environment}/argocd"
}

########################################
# NETWORK
########################################

module "network" {
  source = "./modules/network"

  region   = var.region
  vpc_cidr = "10.0.0.0/16"
  az_count = 2

  project          = var.project_name
  environment      = var.environment
  eks_cluster_name = local.cluster_name

  tags = merge(
    local.common_tags,
    {
      CostCenter = "EKS-WORDPRESS"
    }
  )
}

########################################
# EKS
########################################

module "eks" {
  source = "./modules/eks"

  region             = var.region
  cluster_name       = local.cluster_name
  kubernetes_version = "1.30"

  private_subnet_ids = module.network.private_workers_subnet_ids

  environment  = var.environment
  project_name = var.project_name

  # Spot diversification
  instance_types = [
    "t3.large",
    "t3a.large",
    "m5.large",
    "m5a.large"
  ]

  node_min_size     = 1
  node_desired_size = 2
  node_max_size     = 3

  tags = local.common_tags
}

########################################
# SECURITY GROUP POUR CODEBUILD (À laisser à la racine)
########################################

resource "aws_security_group" "codebuild_sg" {
  name        = "${var.project_name}-codebuild-sg-${var.environment}"
  description = "Security group for database initialization container"
  vpc_id      = module.network.vpc_id # Totalement valide ici à la racine !

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = local.common_tags
}

########################################
# RDS
########################################

module "rds" {
  source = "./modules/rds"

  environment  = var.environment
  project_name = var.project_name

  db_instance_class = var.instance_class
  db_engine         = var.db_engine
  db_engine_version = var.db_engine_version
  allocated_storage = var.allocated_storage

  db_name     = data.vault_kv_secret_v2.rds.data["DB_NAME"]
  db_username = data.vault_kv_secret_v2.rds.data["DB_USER"]
  db_password = data.vault_kv_secret_v2.rds.data["DB_PASSWORD"]

  app_sg_ids = [
    module.eks.cluster_security_group_id,
    aws_security_group.codebuild_sg.id
  ]

  network = {
    vpc_id                 = module.network.vpc_id
    private_rds_subnet_ids = module.network.private_rds_subnet_ids
  }
}

resource "vault_kv_secret_v2" "rds_endpoint" {
  mount = "kv-aws"
  name  = "maptdp/${var.environment}/rds-config"

  data_json = jsonencode({
    DB_HOST     = module.rds.rds_endpoint
    DB_PORT     = "5432"
    DB_NAME     = data.vault_kv_secret_v2.rds.data["DB_NAME"]
    DB_USER     = data.vault_kv_secret_v2.rds.data["DB_USER"]
    DB_PASSWORD = data.vault_kv_secret_v2.rds.data["DB_PASSWORD"]
  })
}

########################################
# CONFIGURATION S3 EXISTANTE (DATA)
########################################

data "aws_s3_bucket" "db_assets" {
  bucket = var.s3_bucket_name
}

########################################
# DATABASE INITIALIZATION
########################################

module "db_initialization" {
  source = "./modules/db_initializer"

  project_name = var.project_name

  # Infos RDS
  rds_instance_id = module.rds.rds_address
  rds_address     = module.rds.rds_address
  rds_db_name     = data.vault_kv_secret_v2.rds.data["DB_NAME"]
  rds_username    = data.vault_kv_secret_v2.rds.data["DB_USER"]
  rds_password    = data.vault_kv_secret_v2.rds.data["DB_PASSWORD"]

  # Infos S3 Sécurisées
  bucket_id     = data.aws_s3_bucket.db_assets.id
  bucket_arn    = data.aws_s3_bucket.db_assets.arn
  sql_file_key  = "version-originelle/clean-Origine.sql" # Écrit en dur, plus de dépendance directe
  sql_file_etag = "static-v1"                            # <-- En mettant une chaîne fixe, Terraform ne relancera JAMAIS CodeBuild, même si le fichier dans S3 change !

  # Infos Réseau
  vpc_id                       = module.network.vpc_id
  private_subnet_ids           = module.network.private_workers_subnet_ids
  codebuild_security_group_ids = [aws_security_group.codebuild_sg.id]
}

########################################
# EKS ACCESS WAIT
########################################

resource "time_sleep" "wait_for_eks_access" {
  create_duration = "60s"

  depends_on = [
    module.eks
  ]
}

########################################
# VAULT AUTH
########################################

module "vault_kubernetes_auth" {
  source = "./modules/vault_kubernetes_auth"

  cluster_endpoint = module.eks.cluster_endpoint
  cluster_ca_data  = module.eks.cluster_certificate_authority_data

  depends_on = [
    time_sleep.wait_for_eks_access
  ]
}

########################################
# EBS CSI DRIVER
########################################

module "ebs_csi" {
  source = "./modules/ebs_csi"

  project_name = var.project_name
  environment  = var.environment

  cluster_name        = module.eks.cluster_name
  cluster_oidc_issuer = module.eks.cluster_oidc_issuer

  depends_on = [
    module.eks
  ]
}


########################################
# VAULT SECRETS OPERATOR
########################################

module "vso" {
  source = "./modules/vso"

  depends_on = [
    module.vault_kubernetes_auth
  ]
}

########################################
# ARGOCD
########################################

module "argocd" {
  source  = "./modules/argocd"
  enabled = true

  argocd_admin_password   = data.vault_kv_secret_v2.argocd.data["admin.password"]
  argocd_server_secretkey = data.vault_kv_secret_v2.argocd.data["server.secretkey"]
  argocd_password_mtime   = data.vault_kv_secret_v2.argocd.data["admin.passwordMtime"]

  depends_on = [
    time_sleep.wait_for_eks_access
  ]
}
