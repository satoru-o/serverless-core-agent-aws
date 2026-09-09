# core/iam.tf
# ticket-api Lambda実行用IAMロール・ポリシー(必要最小限のアクションのみ許可)

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ticket_api_lambda" {
  name               = "core-ticket-api-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "ticket_api_lambda" {
  statement {
    sid    = "DynamoDBAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:TransactWriteItems",
    ]
    resources = [
      aws_dynamodb_table.tickets.arn,
      "${aws_dynamodb_table.tickets.arn}/index/StatusIndex",
    ]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "ticket_api_lambda" {
  name   = "core-ticket-api-lambda-policy"
  role   = aws_iam_role.ticket_api_lambda.id
  policy = data.aws_iam_policy_document.ticket_api_lambda.json
}
