module "network" {
  source = "./modules/network"

  name_prefix = local.name_prefix
}

module "ecr_api" {
  source = "./modules/ecr"

  name = var.service_name_api
}

module "api_log_group" {
  source = "./modules/log_group"

  name              = "/ecs/${local.name_prefix}/${var.service_name_api}"
  retention_in_days = 14
}

module "alb" {
  source = "./modules/alb"

  name_prefix       = local.name_prefix
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
  container_port    = var.api_container_port
  health_check_path = var.api_health_check_path
}

module "ecs_service_api" {
  source = "./modules/ecs_service"

  name                   = var.service_name_api
  cluster_name           = local.name_prefix
  vpc_id                 = module.network.vpc_id
  private_subnet_ids     = module.network.private_subnet_ids
  target_group_arn       = module.alb.target_group_arn
  alb_security_group_id  = module.alb.security_group_id
  container_port         = var.api_container_port
  cpu                    = var.api_cpu
  memory                 = var.api_memory
  min_capacity           = var.api_min_capacity
  max_capacity           = var.api_max_capacity
  log_group_name         = module.api_log_group.name
  image                  = "${module.ecr_api.repository_url}:${var.api_image_tag}"
  environment_variables = {
    ENV  = var.environment_name
    PORT = tostring(var.api_container_port)
  }
}

