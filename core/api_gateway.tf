# core/api_gateway.tf
# チケット管理APIのAPI Gateway(REST API)。各ユーザーストーリーのメソッドはこのファイルに
# 追記していく。api_gateway.tf の変更は aws_api_gateway_deployment のtriggerで検知され、
# `terraform apply` のたびに自動的に再デプロイされる。
#
# 002-agent-safe-operation (T004): 全メソッドの authorization を NONE から AWS_IAM に変更。
# エージェント側のIAMロールによる呼び出し制御(execute-api:Invoke)を実効あるものにするため。
# 呼び出し元はSigV4署名が必須になる(specs/002-agent-safe-operation/contracts/
# ticket-api-access-control.md参照)。

# --- T011: REST API本体 + 共通の親リソース /tickets ---

resource "aws_api_gateway_rest_api" "this" {
  name = "core-ticket-api"
}

resource "aws_api_gateway_resource" "tickets" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "tickets"
}

# --- T019: POST /tickets(US1) + Lambda呼び出し許可 ---
# aws_lambda_permission はAPI Gateway全体(全メソッド・全ステージ)をカバーするワイルド
# カードで1回だけ作成する。US2〜US5でメソッドを追加する際にこの権限を再作成する必要はない。

resource "aws_api_gateway_method" "tickets_post" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.tickets.id
  http_method   = "POST"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "tickets_post" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.tickets.id
  http_method             = aws_api_gateway_method.tickets_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ticket_api.invoke_arn
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ticket_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/*/*"
}

# --- T037: GET /tickets/{ticket_id}/history(US5、履歴取得) ---
# {ticket_id} リソースはT025で作成済みのものを再利用する。
# aws_lambda_permission もT019で作成済みのため再作成不要。

resource "aws_api_gateway_resource" "ticket_history" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.ticket_id.id
  path_part   = "history"
}

resource "aws_api_gateway_method" "ticket_history_get" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.ticket_history.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "ticket_history_get" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.ticket_history.id
  http_method             = aws_api_gateway_method.ticket_history_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ticket_api.invoke_arn
}

# --- T033: GET /tickets/{ticket_id}(US4、単体取得) ---
# {ticket_id} リソースはT025で作成済みのものを再利用する。
# aws_lambda_permission もT019で作成済みのため再作成不要。

resource "aws_api_gateway_method" "ticket_get" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.ticket_id.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "ticket_get" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.ticket_id.id
  http_method             = aws_api_gateway_method.ticket_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ticket_api.invoke_arn
}

# --- T029: GET /tickets(US3、一覧取得) ---
# aws_lambda_permission はT019で作成済みのため再作成不要。

resource "aws_api_gateway_method" "tickets_get" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.tickets.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "tickets_get" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.tickets.id
  http_method             = aws_api_gateway_method.tickets_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ticket_api.invoke_arn
}

# --- T025: PATCH /tickets/{ticket_id}/status(US2) ---
# {ticket_id} リソースはUS2〜US5で共有するため、ここで一度だけ作成する。

resource "aws_api_gateway_resource" "ticket_id" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.tickets.id
  path_part   = "{ticket_id}"
}

resource "aws_api_gateway_resource" "ticket_status" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.ticket_id.id
  path_part   = "status"
}

resource "aws_api_gateway_method" "ticket_status_patch" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.ticket_status.id
  http_method   = "PATCH"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "ticket_status_patch" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.ticket_status.id
  http_method             = aws_api_gateway_method.ticket_status_patch.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ticket_api.invoke_arn
}

# --- T012: デプロイ・ステージ ---
# api_gateway.tf 全体のハッシュをtriggerにすることで、以降のストーリーでメソッドを
# 追加するたびに自動的に再デプロイされる。

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = filemd5("${path.module}/api_gateway.tf")
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_method.tickets_post,
    aws_api_gateway_integration.tickets_post,
    aws_api_gateway_method.tickets_get,
    aws_api_gateway_integration.tickets_get,
    aws_api_gateway_method.ticket_status_patch,
    aws_api_gateway_integration.ticket_status_patch,
    aws_api_gateway_method.ticket_get,
    aws_api_gateway_integration.ticket_get,
    aws_api_gateway_method.ticket_history_get,
    aws_api_gateway_integration.ticket_history_get,
  ]
}

resource "aws_api_gateway_stage" "v1" {
  deployment_id = aws_api_gateway_deployment.this.id
  rest_api_id   = aws_api_gateway_rest_api.this.id
  stage_name    = "v1"
}
