# CLAUDE.md

このファイルは、このリポジトリでClaude Codeが作業する際に毎回参照する情報をまとめたものです。

## プロジェクトの位置づけ

サーバーレス基幹システム(タスク管理・Phase 1)と、それを安全に操るエージェント基盤(Phase 2)を
段階的に構築する学習用リポジトリです。詳細な背景・設計判断は [docs/proposal.md](docs/proposal.md) を参照してください。

## 使用技術・使用禁止事項

- **RDS・EC2・Auroraは使用しない**(常時課金を避けるため)
- 中心となるサービス: Lambda、DynamoDB、API Gateway、Step Functions、EventBridge、SQS、
  CloudWatch、CloudTrail、AWS Budgets、SNS
- IaCはTerraformで統一する

## コスト意識に関する注意

- 新しいAWSリソースを追加提案する際は、**常時課金が発生しないか**(起動しているだけで
  課金され続けるものでないか)を必ず先に確認してから進めること
- リソース追加時はAWS Budgetsのアラート設定を意識すること

## ディレクトリの役割

- `core/` : Phase 1(タスク管理の基幹システム)のTerraform・Lambdaコード
- `agent/` : Phase 2(エージェント安全運用)のTerraform・Lambdaコード
- `docs/` : 企画書・設計判断の記録

## 進め方の方針

- Phase 1 → Phase 2 の順で進める。Phase 2はPhase 1が完了するまで着手しない
- Phase 2内では、企画書に記載の Step 0〜4(安全設計を段階的に追加する順序)を守ること。
  いきなり全ての安全対策を実装せず、各Stepごとに動作確認してから次に進む

## コミットメッセージの言語

日本語で簡潔に書くこと(例: "feat: DynamoDBテーブル定義を追加")

## タグ付けルール

全てのAWSリソースに以下のタグを必須で付与すること:
- Project = "serverless-core-agent-aws"
- ManagedBy = "terraform"(手動作成のブートストラップリソースは "manual-bootstrap")
- Phase = "core" または "agent"（該当するフェーズ）