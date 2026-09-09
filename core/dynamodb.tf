# core/dynamodb.tf
# チケット管理システムのシングルテーブル(data-model.md参照)

resource "aws_dynamodb_table" "tickets" {
  name         = "core-tickets"
  billing_mode = "PAY_PER_REQUEST" # オンデマンドモード(常時課金を避ける、原則I)

  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }
}
