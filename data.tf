data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

data "aws_cloudwatch_log_group" "logs" {
  name = var.cloudtrail_cw_log_group
}
