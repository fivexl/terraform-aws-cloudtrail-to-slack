# SNS Topic for S3 bucket notifications
resource "aws_sns_topic" "s3_notifications" {
  count = var.enable_s3_sns_notifications && var.s3_sns_topic_arn == null ? 1 : 0
  name  = var.s3_sns_topic_name != null ? var.s3_sns_topic_name : "${var.function_name}-s3-notifications"
  tags  = var.tags
}

# SNS Topic Policy to allow S3 to publish
resource "aws_sns_topic_policy" "s3_notifications" {
  count  = var.enable_s3_sns_notifications && var.s3_sns_topic_arn == null ? 1 : 0
  arn    = aws_sns_topic.s3_notifications[0].arn
  policy = data.aws_iam_policy_document.s3_sns_topic_policy[0].json
}

data "aws_iam_policy_document" "s3_sns_topic_policy" {
  count = var.enable_s3_sns_notifications && var.s3_sns_topic_arn == null ? 1 : 0

  statement {
    sid    = "AllowS3ToPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    actions = [
      "SNS:Publish",
    ]

    resources = [
      aws_sns_topic.s3_notifications[0].arn,
    ]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [data.aws_s3_bucket.cloudtrail.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# Lambda Permission for SNS to invoke Lambda
resource "aws_lambda_permission" "sns" {
  count         = var.enable_s3_sns_notifications ? 1 : 0
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "sns.amazonaws.com"
  source_arn    = var.s3_sns_topic_arn != null ? var.s3_sns_topic_arn : aws_sns_topic.s3_notifications[0].arn
}

# SNS Topic Subscription for Lambda
resource "aws_sns_topic_subscription" "lambda" {
  count     = var.enable_s3_sns_notifications ? 1 : 0
  topic_arn = var.s3_sns_topic_arn != null ? var.s3_sns_topic_arn : aws_sns_topic.s3_notifications[0].arn
  protocol  = "lambda"
  endpoint  = module.lambda.lambda_function_arn

  depends_on = [aws_lambda_permission.sns]
}
