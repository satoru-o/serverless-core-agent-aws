# Contract: コスト超過時の自動停止(暴走防止)

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)

## AWS Budgetsの設定

```
resource "aws_budgets_budget" "agent" {
  name         = "agent-monthly-cost"
  budget_type  = "COST"
  limit_amount = var.agent_budget_limit_usd   # 例: "5"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Phase$agent"]
  }

  notification {
    comparison_operator      = "GREATER_THAN"
    threshold                = 80
    threshold_type           = "PERCENTAGE"
    notification_type        = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alert.arn]
  }

  notification {
    comparison_operator      = "GREATER_THAN"
    threshold                = 100
    threshold_type           = "PERCENTAGE"
    notification_type        = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alert.arn]
  }
}
```

- 80%到達: 運用者への警告通知のみ(自動停止はしない)
- 100%到達: 運用者への通知に加えて `budget_stop` Lambdaを起動し、エージェントの新規実行を
  自動的に停止する(FR-005, FR-006)

## SNSメッセージから`budget_stop` Lambdaの処理まで

AWS Budgetsが送信するSNS通知(実際コストがしきい値を超過した旨)を`budget_stop` Lambdaが
サブスクライブする。メッセージの`threshold`が100%通知であることを確認したうえで、以下を行う:

1. `events:DisableRule` で `decision` Lambdaをトリガーしている EventBridge ルールを無効化する
2. `BUDGET_STOP` の操作記録(data-model.md)をCloudWatch Logsに記録する
3. 運用者向けにSNS(`agent-approval-request`と同じ、または別途の通知用トピック)へ
   「コストしきい値超過のためエージェントの新規実行を停止しました」という通知を送る(FR-006)

## 復旧手順

自動停止は新規実行の受付(EventBridgeルール)のみを止める設計であり、自動復旧は行わない
(spec.md Assumptions: 復旧には運用者の判断を要するため)。運用者がコスト超過の原因を確認した
上で、手動で以下のいずれかを実行して復旧する:

- Terraform管理下のEventBridgeルールを再度有効化する(`aws events enable-rule` または
  Terraform側のフラグ変数を元に戻して`terraform apply`)
- 予算上限(`agent_budget_limit_usd`)自体を見直す場合は、Terraform変数を変更して
  `terraform apply` する

## 既に進行中の処理への影響

停止時点で実行中の `decision` Lambda呼び出しや、承認待ちのStep Functions実行は強制終了
しない(spec.md Edge Cases: 承認待ちの重大操作はそのまま保留され続ける)。
