locals {
  name_prefix = "${lower(var.project_name)}-${lower(var.environment_name)}"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment_name
      ManagedBy   = "terraform"
    },
    var.tags
  )
}
