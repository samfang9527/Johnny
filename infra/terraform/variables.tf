variable "aws_region" {
  type    = string
  default = "ap-northeast-1"
  validation {
    condition     = var.aws_region == "ap-northeast-1"
    error_message = "The production v1 deployment runs in ap-northeast-1 (Tokyo)."
  }
}
variable "project_name" {
  type    = string
  default = "johnny"
}
variable "environment_name" {
  type    = string
  default = "production"
}
variable "domain_name" { type = string }
variable "route53_zone_id" { type = string }
variable "certificate_email" { type = string }
variable "google_oauth_client_id" { type = string }
variable "llm_model" { type = string }
variable "github_repository" { type = string }
variable "github_oidc_provider_arn" {
  type    = string
  default = ""
}
variable "instance_type" {
  type    = string
  default = "t4g.small"
}
variable "data_volume_gb" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
