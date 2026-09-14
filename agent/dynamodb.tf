# agent/dynamodb.tf
# 承認/却下リンクの消費状態(research.md §11、data-model.md「承認リンク消費状態」)。
# プリフェッチ対策の2段階確認方式で、通知リンクへの初回アクセスを記録するためだけに
# 使う小さなテーブル。TTL属性で承認タイムアウトより長く保持したのち自動削除する。

resource "aws_dynamodb_table" "approval_links" {
  name         = "agent-approval-links"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "task_token"

  attribute {
    name = "task_token"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
