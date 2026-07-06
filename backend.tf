terraform {
  backend "s3" {
    bucket       = "tfstate-s3-projet-devops"
    key          = "infra/prod/terraform.tfstate"
    region       = "eu-west-3"
    use_lockfile = true
    encrypt      = true
  }
}
