# agent/api_gateway.tf
# 承認コールバック用API Gateway(REST API)。GET /approvals・GET /approvals/confirm は
# いずれも authorization = "NONE"(署名不要の公開エンドポイント)。Step Functionsの
# タスクトークン自体が知識ベースの認可情報として機能する(contracts/approval-flow.md)。
# approval_callback Lambda(T050)に依存するため、そのLambda定義より後に定義する
# (/speckit-analyze F3対応)。

resource "aws_api_gateway_rest_api" "approvals" {
  name = "agent-approval-callback"
}

resource "aws_api_gateway_resource" "approvals" {
  rest_api_id = aws_api_gateway_rest_api.approvals.id
  parent_id   = aws_api_gateway_rest_api.approvals.root_resource_id
  path_part   = "approvals"
}

# --- Step 1: GET /approvals(確認ページの表示のみ、副作用なし) ---

resource "aws_api_gateway_method" "approvals_get" {
  rest_api_id   = aws_api_gateway_rest_api.approvals.id
  resource_id   = aws_api_gateway_resource.approvals.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "approvals_get" {
  rest_api_id             = aws_api_gateway_rest_api.approvals.id
  resource_id             = aws_api_gateway_resource.approvals.id
  http_method             = aws_api_gateway_method.approvals_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.approval_callback.invoke_arn
}

# --- Step 2: GET /approvals/confirm(確認ページ内のリンクからのみ到達) ---

resource "aws_api_gateway_resource" "approvals_confirm" {
  rest_api_id = aws_api_gateway_rest_api.approvals.id
  parent_id   = aws_api_gateway_resource.approvals.id
  path_part   = "confirm"
}

resource "aws_api_gateway_method" "approvals_confirm_get" {
  rest_api_id   = aws_api_gateway_rest_api.approvals.id
  resource_id   = aws_api_gateway_resource.approvals_confirm.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "approvals_confirm_get" {
  rest_api_id             = aws_api_gateway_rest_api.approvals.id
  resource_id             = aws_api_gateway_resource.approvals_confirm.id
  http_method             = aws_api_gateway_method.approvals_confirm_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.approval_callback.invoke_arn
}

resource "aws_lambda_permission" "apigw_invoke_approval_callback" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.approval_callback.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.approvals.execution_arn}/*/*/*"
}

resource "aws_api_gateway_deployment" "approvals" {
  rest_api_id = aws_api_gateway_rest_api.approvals.id

  triggers = {
    redeployment = filemd5("${path.module}/api_gateway.tf")
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_method.approvals_get,
    aws_api_gateway_integration.approvals_get,
    aws_api_gateway_method.approvals_confirm_get,
    aws_api_gateway_integration.approvals_confirm_get,
  ]
}

resource "aws_api_gateway_stage" "approvals" {
  deployment_id = aws_api_gateway_deployment.approvals.id
  rest_api_id   = aws_api_gateway_rest_api.approvals.id
  stage_name    = "v1"
}
