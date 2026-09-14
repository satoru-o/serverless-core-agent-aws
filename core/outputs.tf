# core/outputs.tf

output "ticket_api_endpoint" {
  description = "チケット管理APIのベースURL(quickstart.mdのAPI_URLに対応)"
  value       = aws_api_gateway_stage.v1.invoke_url
}

output "ticket_api_execution_arn" {
  description = "agent/側のIAMポリシーからexecute-api:Invokeの対象を指定するためのARN(002-agent-safe-operation)"
  value       = aws_api_gateway_rest_api.this.execution_arn
}
