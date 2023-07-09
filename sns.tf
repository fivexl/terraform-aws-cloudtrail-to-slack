resource "aws_sns_topic" "events_to_sns" {
  count             = var.default_sns_topic_arn == null && length(var.aws_sns_topic_subscriptions) > 0 ? 1 : 0
  name              = var.function_name
  kms_master_key_id = "alias/aws/sns" # tfsec:ignore:aws-sns-topic-encryption-use-cmk
  tags              = var.tags
}

resource "aws_sns_topic_subscription" "events_to_sns" {
  for_each  = var.aws_sns_topic_subscriptions
  topic_arn = aws_sns_topic.events_to_sns[0].arn
  protocol  = each.value
  endpoint  = each.key
}
