terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.27"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.10"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "aws" {
  region = var.region
}

# ------------------------------------------------------------
# EKS connectivity (via outputs du module EKS)
# ------------------------------------------------------------
# try() évite un plantage au moment du plan si le module n’est pas encore calculable
locals {
  k8s_host = try(module.eks.cluster_endpoint, null)
  k8s_ca   = try(base64decode(module.eks.cluster_certificate_authority_data), null)
  k8s_name = try(module.eks.cluster_name, null)
}

# Provider Kubernetes : Auth via AWS CLI token (OIDC)
provider "kubernetes" {
  host                   = local.k8s_host
  cluster_ca_certificate = local.k8s_ca

  # Évite tout fallback implicite vers ~/.kube/config
  config_path    = null
  config_context = null

  exec {
    api_version = "client.authentication.k8s.io/v1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--cluster-name", local.k8s_name,
      "--region", var.region,
    ]
  }
}

# Provider Helm avec bloc kubernetes intégré (mêmes creds)
provider "helm" {
  kubernetes {
    host                   = local.k8s_host
    cluster_ca_certificate = local.k8s_ca

    # Ne PAS définir load_config_file/config_path/config_context ici en v2.13
    exec {
      api_version = "client.authentication.k8s.io/v1"
      command     = "aws"
      args = [
        "eks",
        "get-token",
        "--cluster-name", local.k8s_name,
        "--region", var.region,
      ]
    }
  }
}


provider "vault" {
  address = "https://vault.jaffleman.tech"

  skip_child_token = true

  auth_login {
    path = "auth/approle/login"

    parameters = {
      role_id   = var.vault_role_id
      secret_id = var.vault_secret_id
    }
  }
}

