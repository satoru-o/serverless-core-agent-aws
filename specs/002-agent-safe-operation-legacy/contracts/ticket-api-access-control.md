# Contract: Ticket API アクセス制御

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)

Phase 1のTicket API([001の契約](../../001-ticket-management/contracts/api.md))自体の
リクエスト/レスポンス形式は変更しない。本フィーチャーが変更するのは**認可方式**のみ。

## core/api_gateway.tf の変更内容

全メソッドの `authorization` を `"NONE"` から `"AWS_IAM"` に変更する。

| リソース | メソッド | 変更前 | 変更後 |
|---|---|---|---|
| `/tickets` | POST | `NONE` | `AWS_IAM` |
| `/tickets` | GET | `NONE` | `AWS_IAM` |
| `/tickets/{ticket_id}` | GET | `NONE` | `AWS_IAM` |
| `/tickets/{ticket_id}/status` | PATCH | `NONE` | `AWS_IAM` |
| `/tickets/{ticket_id}/history` | GET | `NONE` | `AWS_IAM` |

`AWS_IAM`化に伴い、呼び出し元は各リクエストをSigV4署名しなければならない
(署名対象リージョン: `ap-northeast-1`、サービス名: `execute-api`)。

## core/outputs.tf への追加

```
output "ticket_api_execution_arn" {
  description = "agent/側のIAMポリシーからexecute-api:Invokeの対象を指定するためのARN"
  value       = aws_api_gateway_rest_api.this.execution_arn
}
```

## agent/側に許可するメソッドARN(IAMポリシーのResource)

`{execution_arn}/{stage}/{METHOD}/{path}` の形式で、ロールごとに以下のみを許可する
(data-model.md「IAMロールと許可操作の対応表」に対応):

| ロール | Resource(execute-api:Invoke) |
|---|---|
| `decision` | `${execution_arn}/v1/GET/tickets`, `${execution_arn}/v1/GET/tickets/*`, `${execution_arn}/v1/PATCH/tickets/*/status` |
| `apply_decision` | `${execution_arn}/v1/PATCH/tickets/*/status` |
| `apply_rejection` | `${execution_arn}/v1/PATCH/tickets/*/status` |

`POST /tickets`(作成)・`GET /tickets/{id}/history`(履歴取得)はいずれのエージェント側
ロールにも許可しない(エージェントの役割は既存チケットの参照・状態変更に限定する、
spec.md Assumptions)。

## 許可範囲外の呼び出しを試みた場合の挙動

`AWS_IAM`化後、ポリシーで許可されていないメソッド・リソースへの呼び出しはAPI Gatewayが
署名検証の時点で `403 Forbidden` を返す(Ticket API Lambda本体には到達しない)。エージェント
側のクライアントコード(`ticket_client.py`)はこの `403` を検知し、
`UNAUTHORIZED_ATTEMPT` としてCloudWatch Logsに記録する(data-model.md「操作記録」、FR-009)。

## 既存ドキュメント(001)への影響

`specs/001-ticket-management/quickstart.md` の curl 手順は、認可方式変更後は無署名では
動作しなくなる。本フィーチャーの実装(tasks.md)にて、SigV4署名済みリクエストを送る手順
(例: `awscurl` の利用、または `aws apigateway test-invoke-method` を使った代替手順)に
更新する。Ticket API自体のリクエスト/レスポンス形式(001の契約)は変更しないため、
書き換えは認証ヘッダの付与方法のみに限定される。
