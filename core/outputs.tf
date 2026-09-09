# core/outputs.tf

output "ticket_api_endpoint" {
  description = "チケット管理APIのベースURL(quickstart.mdのAPI_URLに対応)"
  value       = aws_api_gateway_stage.v1.invoke_url
}
