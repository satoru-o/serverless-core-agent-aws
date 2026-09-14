# agent/cloudwatch.tf
# 各LambdaのロググループはTerraformで明示的に定義し、保持期間(retention_in_days)を
# 設定する。既定(Terraformで定義しない場合)は無期限保持となり、不要なログ保持コストが
# 発生し続けるため(FR-010、spec.md Assumptions「数週間〜1か月」)。

# --- T030: decision / budget_stop Lambdaのロググループ ---

resource "aws_cloudwatch_log_group" "decision" {
  name              = "/aws/lambda/${aws_lambda_function.decision.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "budget_stop" {
  name              = "/aws/lambda/${aws_lambda_function.budget_stop.function_name}"
  retention_in_days = var.log_retention_days
}

# --- T031: 操作記録の期間指定検索用Insightsクエリ(FR-010) ---

resource "aws_cloudwatch_query_definition" "agent_operation_history" {
  name = "agent-operation-history"

  log_group_names = [
    aws_cloudwatch_log_group.decision.name,
    aws_cloudwatch_log_group.budget_stop.name,
    aws_cloudwatch_log_group.apply_decision.name,
    aws_cloudwatch_log_group.apply_rejection.name,
    aws_cloudwatch_log_group.approval_callback.name,
  ]

  query_string = <<-EOT
    fields timestamp, actor, ticket_id, action, result, detail
    | sort timestamp asc
  EOT
}

# --- T056: apply_decision / apply_rejection / approval_callback Lambdaのロググループ ---

resource "aws_cloudwatch_log_group" "apply_decision" {
  name              = "/aws/lambda/${aws_lambda_function.apply_decision.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "apply_rejection" {
  name              = "/aws/lambda/${aws_lambda_function.apply_rejection.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "approval_callback" {
  name              = "/aws/lambda/${aws_lambda_function.approval_callback.function_name}"
  retention_in_days = var.log_retention_days
}
