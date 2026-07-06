variable "enabled" {
  description = "Enable or disable Argo CD installation"
  type        = bool
  default     = true
}


variable "for_depends_on" {
  type    = list(any)
  default = []
}

variable "argocd_admin_password" {
  type      = string
  sensitive = true
}

variable "argocd_server_secretkey" {
  type      = string
  sensitive = true
}

variable "argocd_password_mtime" {
  type = string
}
