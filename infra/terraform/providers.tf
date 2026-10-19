provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# CloudFront accepts ACM viewer certificates only from us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
