# agent/eventbridge.tf
# decision Lambdaを定期実行するスケジュールルール(research.md §9)。
# budget_stop(agent/iam.tf T022)がこのルールを無効化することでコスト超過時の
# 新規実行停止(FR-005)を実現するため、budget_stopロールより前に定義する
# (/speckit-analyze F2対応)。

resource "aws_cloudwatch_event_rule" "decision_schedule" {
  name                = "agent-decision-schedule"
  schedule_expression = var.eventbridge_schedule
}

resource "aws_cloudwatch_event_target" "decision" {
  rule = aws_cloudwatch_event_rule.decision_schedule.name
  arn  = aws_lambda_function.decision.arn
}

resource "aws_lambda_permission" "eventbridge_invoke_decision" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.decision.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.decision_schedule.arn
}
