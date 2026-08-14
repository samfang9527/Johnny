locals {
  name_prefix = "${var.project_name}-${var.environment_name}"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment_name
      ManagedBy   = "terraform"
      Template    = "scaffold-cli"
    },
    var.tags
  )
}

