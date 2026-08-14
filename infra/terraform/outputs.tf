output "alb_dns_name" {
  value = module.alb.dns_name
}

output "api_repository_url" {
  value = module.ecr_api.repository_url
}

output "api_service_name" {
  value = module.ecs_service_api.service_name
}

output "api_cluster_name" {
  value = module.ecs_service_api.cluster_name
}

