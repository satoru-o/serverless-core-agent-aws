# Implementation Plan: チケット管理エージェントの安全運用基盤

**Branch**: `002-agent-safe-operation` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-agent-safe-operation/spec.md`

## Summary

Phase 1のチケット管理システムを操作するAIエージェントを、権限制御・暴走防止(P1)を
初回リリース時点から同時に備えた状態で構築し、その上に操作履歴の追跡(P2)、重大操作の
人間承認(P3)を積み上げる。中核となる設計判断は次の3点。

1. Phase 1のTicket APIの認可方式を `NONE` から `AWS_IAM` に変更し(ユーザー承認済み)、
   エージェント側のIAMロールによる呼び出し制御を実効あるものにする
2. 責務ごとに4つのLambda関数・IAMロールに分離し、「重大操作(チケット完了)を発行できる
   コードパス」を承認後にしか呼ばれないLambdaだけに限定することでFR-011を担保する
3. 重大操作の承認はStep Functionsのwait-for-task-tokenパターン + SNS通知 + 承認コールバック
   用API Gatewayで実現し、承認・却下・タイムアウトの3分岐すべてでチケットが安全な状態に
   保たれるようにする。承認/却下の通知リンクはメールクライアント等によるプリフェッチだけで
   実行されないよう2段階確認方式とし、実際の状態変更は確認ページ上での明示的なクリックを
   経て初めて発生させる(FR-016)

すべてのAWSリソースは `agent/` 配下のTerraformで定義し、`core/` 側の変更は認可方式の変更
(および出力の追加)のみに留める。

## Technical Context

**Language/Version**: Python 3.13(AWS Lambda マネージドランタイム、`core/`と統一)

**Primary Dependencies**: `boto3`/`botocore`(Lambdaランタイムに標準同梱、追加レイヤー不要。
SigV4署名に`botocore.auth.SigV4Auth`を利用)。エージェントの判断ロジックは`boto3`の
`bedrock-runtime`クライアント(Converse API)でAmazon Bedrock(Amazon Nova Micro)を呼び出す。
テスト用に`pytest` + `moto`(開発依存のみ)

**Storage**: チケット本体・履歴は引き続き`core/`のDynamoDBテーブルに存在し、エージェントは
Ticket API経由でのみアクセスする(直接のDynamoDB権限は与えない、data-model.md参照)。
操作記録はCloudWatch Logs、承認依頼の状態は基本的にStep Functions実行そのものに実体化する。
例外として、承認/却下リンクのプリフェッチ対策(2段階確認方式、research.md §11)のために、
小さなDynamoDBテーブル `agent-approval-links`(オンデマンドモード、TTL設定)を1つ新設する

**Testing**: `pytest`(単体テスト)+ `moto`(IAM境界・AWSサービス呼び出しのモック)。
実AWSリソースには接続しない

**Target Platform**: AWS Lambda(Python)+ Step Functions(Standard)+ EventBridge(スケジュール)
+ API Gateway(REST、承認コールバック用)+ SNS + AWS Budgets、リージョン`ap-northeast-1`

**Project Type**: サーバーレスの安全運用基盤(複数Lambda + ステートマシンによる責務分離構成)

**Performance Goals**: 学習用途の低トラフィックシステム。`decision`実行1回あたりの処理は
タイムアウト60秒以内に収まることを目安とする。高スループット要件はなし

**Constraints**:
- RDS・EC2・Aurora不使用(constitution原則I)
- 全リソースにTerraformでのタグ付け必須(Phase="agent"、原則IV)
- LLM呼び出しはAmazon Bedrock(IAM権限のみで呼び出し可能)を使い、APIキーの発行・保管
  (Secrets Manager等)は行わない
- Amazon Nova Microは`ap-northeast-1`では直接呼び出せず、クロスリージョン推論プロファイル
  経由でのみ利用可能(research.md §2)
- `core/`への変更はTicket APIの認可方式変更(`NONE→AWS_IAM`)と出力追加のみに限定し、
  業務ロジック(状態遷移ルール等)は変更しない(spec.mdスコープ外要件)
- tfstateは`core/`と同じS3バックエンド(`sca-aws-tfstate`)・プロファイル(`sca-aws`)を使うが
  `key`は`agent/terraform.tfstate`として分離する
- 実行回数上限・タイムアウト・コストしきい値は初期値を小さく設定し、Terraform変数として
  調整可能にする(固定値のハードコードを避ける)

**Scale/Scope**: 単一エージェントが単一のチケット管理システムを操作する構成(複数エージェント
の並行運用はスコープ外)。EventBridgeスケジュールは`rate(5 minutes)`を初期値とする

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 根拠 |
|---|---|---|
| I. コスト意識ファースト(NON-NEGOTIABLE) | PASS | RDS/EC2/Aurora不使用。Lambda・Step Functions(Standard、無料枠月4,000状態遷移)・EventBridge・SNS・CloudWatch・CloudTrail・AWS Budgets・DynamoDB(オンデマンドモード)・Amazon Bedrock(従量課金、常時起動コストなし)はいずれも常時課金が発生しないサービス。プリフェッチ対策用に新設する`agent-approval-links`テーブルもオンデマンドモード+TTLによる自動削除でコストを抑える。BedrockはIAM権限のみで呼び出せるため、APIキー管理用のSecrets Manager(固定費あり)・SSM Parameter Storeいずれも不要になった。AWS Budgetsを初回リリース時点から導入し、Phase 2(タグ`Phase=agent`)のコストのみを対象にしきい値超過で自動停止する構成とした |
| II. Infrastructure as Code(Terraform統一) | PASS | 新規AWSリソース(Lambda×4、Step Functions、EventBridge、SNS、AWS Budgets、承認コールバック用API Gateway、IAMロール)はすべて`agent/`配下のTerraformで定義する。`core/`側の変更(認可方式・出力追加)もTerraformで行い手動変更はしない |
| III. 段階的構築の順序を守る(NON-NEGOTIABLE) | PASS | Phase 1は完了済み(specs/001-ticket-management/tasks.mdの全40タスクが完了)。本フィーチャーはPhase 2のStep 1(①権限制御+②暴走防止の同時適用)〜Step 3(④人間承認)の設計を一括で行うが、実装(tasks.md)の着手順序はStep 1→Step 2→Step 3(spec.mdのUser Story P1→P2→P3)を厳守する。P1(権限制御・暴走防止)を経ずにP3(人間承認)から着手することはしない |
| IV. リソースタグ付けの必須化 | PASS | `agent/providers.tf`の`provider "aws"`に`default_tags`(Project="serverless-core-agent-aws", ManagedBy="terraform", Phase="agent")を設定し、`agent/`配下の新規リソースは明示的な`tags`指定なしでも自動的にタグ付けされる |
| V. コミットメッセージ規約 | N/A(実装フェーズで適用) | 実装時のコミットは日本語で簡潔に記述する運用を継続する |

**Phase 1(`core/`)への影響に関する補足**: 本フィーチャーはPhase 1完了後に`core/api_gateway.tf`
(認可方式の変更)と`core/outputs.tf`(出力追加)に手を入れる。これは業務ロジックの変更では
なくアクセス制御方式の変更であり、ユーザーに確認・承認を得た上での判断(理由:
`authorization = "NONE"`のままではエージェント側IAMロールの絞り込みが技術的に無意味になる
ため)。あわせて`specs/001-ticket-management/quickstart.md`のcurl手順(無署名呼び出し)が
そのままでは動作しなくなるため、実装時にSigV4署名を伴う手順に更新する
(contracts/ticket-api-access-control.md参照)。

**Gate結果**: 違反なし。Complexity Trackingへの記載は不要。

## Project Structure

### Documentation (this feature)

```text
specs/002-agent-safe-operation/
├── plan.md                          # This file (/speckit-plan command output)
├── research.md                      # Phase 0 output
├── data-model.md                    # Phase 1 output
├── quickstart.md                    # Phase 1 output
├── contracts/
│   ├── ticket-api-access-control.md # Phase 1 output
│   ├── approval-flow.md             # Phase 1 output
│   └── budget-circuit-breaker.md    # Phase 1 output
├── checklists/
│   └── requirements.md
└── tasks.md                          # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

constitution(CLAUDE.md)の規約により、Phase 2のTerraform・Lambdaコードはすべて `agent/`
配下に配置する。`core/`は認可方式の変更・出力追加のみ行う。

```text
agent/
├── providers.tf                  # 新規: backend "s3"(key="agent/terraform.tfstate")、
│                                    provider(default_tags Phase="agent")、
│                                    terraform_remote_state("core")
├── iam.tf                         # 新規: decision / apply_decision / apply_rejection /
│                                    approval_callback / budget_stop の各実行ロール・ポリシー
├── lambda.tf                      # 新規: 上記5つのLambda関数
├── eventbridge.tf                 # 新規: decisionの定期実行ルール(rate(5 minutes))
├── step_functions.tf              # 新規: 承認ステートマシン(wait-for-task-token)
├── sns.tf                         # 新規: agent-approval-request / agent-budget-alert トピック
├── budgets.tf                     # 新規: aws_budgets_budget(タグPhase=agentでフィルタ)
├── dynamodb.tf                    # 新規: agent-approval-links(承認リンク消費状態、TTL設定)
├── api_gateway.tf                 # 新規: 承認コールバック用API Gateway
│                                    (GET /approvals, GET /approvals/confirm)
├── outputs.tf                     # 新規: 承認コールバックURL等
├── src/
│   └── ticket_agent/
│       ├── __init__.py
│       ├── ticket_client.py       # SigV4署名付きTicket APIクライアント(GET/PATCH限定)
│       ├── decision.py            # Bedrock(Converse API、Amazon Nova Micro)呼び出し・
│       │                            対応方針の判断ロジック
│       ├── decision_handler.py    # EventBridgeトリガーのLambdaエントリポイント
│       ├── apply_decision_handler.py   # 承認後: PATCH .../status=DONE
│       ├── apply_rejection_handler.py  # 却下後: PATCH .../status=OPEN
│       ├── approval_callback_handler.py # API Gatewayトリガー: 2段階確認(確認ページ表示→
│       │                                  SendTaskSuccess/Failure、research.md §11)
│       ├── budget_stop_handler.py       # SNSトリガー: EventBridgeルール無効化
│       ├── audit_log.py           # 構造化ログ出力(data-model.md「操作記録」フォーマット)
│       └── errors.py
└── tests/
    └── ticket_agent/
        ├── unit/
        │   ├── test_decision.py
        │   ├── test_ticket_client.py
        │   └── test_audit_log.py
        └── integration/
            └── test_iam_boundaries.py   # moto使用、ロールごとの許可/拒否境界の検証

core/
├── api_gateway.tf   # 変更: 各aws_api_gateway_methodのauthorizationを"AWS_IAM"に変更
└── outputs.tf        # 変更: ticket_api_execution_arn を追加
```

**Structure Decision**: `core/`と対になる単一プロジェクト構成を`agent/`配下に置く。責務分離
(research.md §3)のためLambda関数を5つに分けるが、Terraformリソースはファイル種別ごとに
まとめ(`iam.tf` / `lambda.tf` / `step_functions.tf` 等)、`core/`と同じ構成方針を踏襲する。
`core/`への変更は認可方式と出力の2点のみに限定する。

## Complexity Tracking

*Constitution Checkに違反なし。本セクションへの記載事項なし。*
