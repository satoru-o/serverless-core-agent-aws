# agent/outputs.tf

output "decision_lambda_name" {
  description = "手動復旧・動作確認用: decision Lambda関数名"
  value       = aws_lambda_function.decision.function_name
}

output "decision_schedule_rule_name" {
  description = "手動復旧用(コスト超過停止からの再開): decision LambdaをトリガーするEventBridgeルール名"
  value       = aws_cloudwatch_event_rule.decision_schedule.name
}

output "approval_callback_base_url" {
  description = "承認コールバックAPIのベースURL(SNS通知の承認/却下リンクの構築元)"
  value       = aws_api_gateway_stage.approvals.invoke_url
}
