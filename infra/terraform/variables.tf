variable "aws_region" {
  type    = string
  default = "ap-northeast-1"
}

variable "project_name" {
  type    = string
  default = "Johnny"
}

variable "environment_name" {
  type    = string
  default = "dev"
}

variable "service_name_api" {
  type    = string
  default = "Johnny-api"
}

variable "api_min_capacity" {
  type    = number
  default = 1
}

variable "api_max_capacity" {
  type    = number
  default = 2
}

variable "api_cpu" {
  type    = number
  default = 256
}

variable "api_memory" {
  type    = number
  default = 512
}

variable "api_container_port" {
  type    = number
  default = 8000
}

variable "api_health_check_path" {
  type    = string
  default = "/health"
}

variable "api_image_tag" {
  type    = string
  default = "latest"
}

variable "tags" {
  type    = map(string)
  default = {}
}
