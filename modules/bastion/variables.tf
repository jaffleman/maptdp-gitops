variable "vpc_id" {
  type = string
}

variable "public_subnet_id" {
  type = string
}

variable "allowed_ip" {
  type        = string
  description = "Ton IP publique en /32 pour SSH"
}

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}
variable "ssh_public_keys" {
  description = "Liste des clés publiques pour les utilisateurs du bastion"
  type        = list(string)
}
