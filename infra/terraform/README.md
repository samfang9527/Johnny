# Terraform

This template provides a more realistic Terraform layout for an AWS ECS deployment:

- root composition under `infra/terraform`
- reusable child modules under `infra/terraform/modules`
- environment overlays under `infra/terraform/environments/dev` and `infra/terraform/environments/prod`

Current scope:
- VPC and subnet layout
- ECS cluster and API service shape
- ALB skeleton
- ECR repository
- CloudWatch log group

The API service defaults to ECS Fargate with `min_capacity = 1` to avoid scale-from-zero cold starts.
