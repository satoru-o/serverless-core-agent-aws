# agent/sns.tf

# --- T024: agent-budget-alert トピック(コスト超過通知、FR-006) ---

resource "aws_sns_topic" "budget_alert" {
  name = "agent-budget-alert"
}

resource "aws_sns_topic_subscription" "budget_alert_email" {
  topic_arn = aws_sns_topic.budget_alert.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

resource "aws_sns_topic_subscription" "budget_alert_lambda" {
  topic_arn = aws_sns_topic.budget_alert.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.budget_stop.arn
}

resource "aws_lambda_permission" "sns_invoke_budget_stop" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.budget_stop.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.budget_alert.arn
}

# --- T045: agent-approval-request トピック(重大操作の承認依頼通知) ---
# 承認ステートマシン(agent/step_functions.tf)がwaitForTaskToken統合でこのトピックに
# 発行する。運用者のメール(またはSlack連携用サブスクリプションを別途追加)。

resource "aws_sns_topic" "approval_request" {
  name = "agent-approval-request"
}

resource "aws_sns_topic_subscription" "approval_request_email" {
  topic_arn = aws_sns_topic.approval_request.arn
  protocol  = "email"
  endpoint  = var.notification_email
}
