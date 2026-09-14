# agent/variables.tf
# 権限制御・暴走防止・承認フローの各種しきい値。運用しながら調整可能な設定値として
# 変数化し、コードやTerraformリソースへの固定値埋め込みを避ける(spec.md Assumptions)。

variable "execution_limit" {
  description = "decision Lambdaの1回の実行あたりのTicket API呼び出し回数上限"
  type        = number
  default     = 20
}

variable "decision_timeout_seconds" {
  description = "decision Lambdaの実行時間タイムアウト(秒)"
  type        = number
  default     = 60
}

variable "eventbridge_schedule" {
  description = "decision Lambdaを起動するEventBridgeスケジュール式"
  type        = string
  default     = "rate(5 minutes)"
}

variable "budget_limit_usd" {
  description = "エージェント運用(タグPhase=agent)の月次コスト上限(USD)"
  type        = string
  default     = "5"
}

variable "notification_email" {
  description = "コスト超過アラート・承認依頼の通知先メールアドレス"
  type        = string
}

variable "approval_timeout_seconds" {
  description = "承認依頼(wait-for-task-token)のタイムアウト(秒)。既定24時間"
  type        = number
  default     = 86400
}

variable "log_retention_days" {
  description = "各LambdaのCloudWatch Logsロググループの保持日数"
  type        = number
  default     = 30
}

variable "bedrock_inference_profile_id" {
  description = <<-EOT
    Amazon Nova Microのクロスリージョン推論プロファイルID。ap-northeast-1では
    Nova Microを直接呼び出せないため、このプロファイル経由で呼び出す(research.md §2)。
  EOT
  type        = string
  default     = "apac.amazon.nova-micro-v1:0"
}

variable "bedrock_foundation_model_id" {
  description = "上記推論プロファイルがルーティングする先の基盤モデルID(IAMリソース指定用)"
  type        = string
  default     = "amazon.nova-micro-v1:0"
}
