# core/lambda.tf
# ticket-api Lambda関数。src/ を丸ごとZIP化し、ticket_api/ パッケージとしてデプロイする
# (ticket_api.errors 等のパッケージ修飾importをローカルテスト・Lambda実行時の両方で
# 一貫させるため、ハンドラは "ticket_api.handler.lambda_handler" とする)

data "archive_file" "ticket_api" {
  type        = "zip"
  source_dir  = "${path.module}/src"
  output_path = "${path.module}/.build/ticket_api.zip"
  excludes    = ["**/__pycache__", "**/__pycache__/**"]
}

resource "aws_lambda_function" "ticket_api" {
  function_name = "core-ticket-api"
  role          = aws_iam_role.ticket_api_lambda.arn
  handler       = "ticket_api.handler.lambda_handler"
  runtime       = "python3.13"
  timeout       = 10
  memory_size   = 128

  filename         = data.archive_file.ticket_api.output_path
  source_code_hash = data.archive_file.ticket_api.output_base64sha256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.tickets.name
    }
  }
}
