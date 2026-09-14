# agent/budgets.tf
# タグPhase=agentのコストのみを対象にした月次予算(contracts/budget-circuit-breaker.md)。
# 80%到達で警告のみ、100%到達でSNS経由budget_stop Lambdaが新規実行を停止する(FR-005/006)。

resource "aws_budgets_budget" "agent" {
  name         = "agent-monthly-cost"
  budget_type  = "COST"
  limit_amount = var.budget_limit_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Phase$agent"]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alert.arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alert.arn]
  }
}
