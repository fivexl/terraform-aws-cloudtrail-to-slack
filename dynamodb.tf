module "cloudtrail_to_slack_dynamodb_table" {
  count   = var.slack_bot_token != null ? 1 : 0
  source  = "terraform-aws-modules/dynamodb-table/aws"
  version = "3.3.0"
  name    = var.dynamodb_table_name

  hash_key           = "principal_structure_and_action_hash"
  ttl_attribute_name = "ttl"
  ttl_enabled        = true

  attributes = [
    {
      name = "principal_structure_and_action_hash"
      type = "S"
    },
  ]
  tags = var.tags

}

