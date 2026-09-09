# Implementation Plan: チケット管理基幹システム

**Branch**: `main` (専用フィーチャーブランチは未作成。仕様ディレクトリ `specs/001-ticket-management` で管理) | **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ticket-management/spec.md`

## Summary

チケットを「発行(OPEN)→対応中(IN_PROGRESS)→完了(DONE)」というシンプルな状態遷移で管理する
サーバーレスAPI。API Gateway(REST)+ 単一のLambda関数(Python)+ DynamoDB(シングルテーブル、
オンデマンドモード)で構成し、状態遷移のバリデーションはLambda内のアプリケーションロジックで
行う(Step Functionsは今回見送り)。全ての状態変更は履歴として同一テーブルに記録し、専用API
(`GET /tickets/{id}/history`)で後から追跡できるようにする。すべてのAWSリソースは
`core/` 配下のTerraformで定義し、既存の `sca-aws-tfstate` バックエンド・`sca-aws` プロファイル・
`default_tags`(Project/ManagedBy/Phase)をそのまま利用する。

## Technical Context

**Language/Version**: Python 3.13(AWS Lambda マネージドランタイム)

**Primary Dependencies**: `boto3`(Lambdaランタイムに標準同梱、追加レイヤー不要)。テスト用に
`pytest` + `moto`(開発依存のみ、デプロイパッケージには含めない)

**Storage**: DynamoDB(シングルテーブル設計、オンデマンドキャパシティモード、GSI `StatusIndex` 1本)

**Testing**: `pytest`(単体テスト)+ `moto`(DynamoDBモック)。実AWSリソースには接続しない

**Target Platform**: AWS Lambda(Python) + API Gateway(REST API)、リージョン `ap-northeast-1`

**Project Type**: サーバーレスWebサービス(API Gateway + Lambda + DynamoDB、単一プロジェクト構成)

**Performance Goals**: 学習用途の低トラフィックシステム(想定同時利用者は当面ごく少数の人手+
後続フェーズのエージェント1体程度)。明示的な高スループット要件はなし。API応答は通常時1〜2秒
以内を目安とする(SC-001〜SC-005を満たす範囲で十分)

**Constraints**:
- RDS・EC2・Aurora不使用(constitution原則I)
- 全リソースにTerraformでのタグ付け必須(Project/ManagedBy/Phase、原則IV)
- 状態遷移バリデーションはLambda内ロジックで実施、Step Functions不使用(ユーザー指定制約)
- tfstateは既存のS3バックエンド(`sca-aws-tfstate`, key `core/terraform.tfstate`)を使用
- AWSプロファイルは `sca-aws` を使用
- リソースはすべて `core/` ディレクトリ配下に配置

**Scale/Scope**: 学習用リポジトリのPhase 1基幹システム。チケット件数は数百〜数千件オーダーを想定。
APIエンドポイントは5つ(作成・一覧・単体取得・状態変更・履歴取得)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 根拠 |
|---|---|---|
| I. コスト意識ファースト(NON-NEGOTIABLE) | PASS | RDS/EC2/Aurora不使用。Lambda(実行課金)、API Gateway REST(リクエスト課金)、DynamoDBオンデマンド(使用量課金)はいずれも常時課金が発生しない。既存の `sca-aws-tfstate` バックエンドを再利用し新規の常時課金リソースは追加しない |
| II. Infrastructure as Code(Terraform統一) | PASS | 新規AWSリソース(DynamoDBテーブル、Lambda関数、API Gateway、IAMロール等)はすべて `core/` 配下のTerraformで定義する。手動作成のリソースはなし |
| III. 段階的構築の順序を守る(NON-NEGOTIABLE) | PASS | 本フィーチャーはPhase 1(サーバーレス基幹システム)のみを対象とし、Phase 2には着手しない。docs/proposal.md 3.3節では将来的な想定サービスとしてStep Functionsが挙げられているが、本フィーチャーはユーザー指示により明示的にStep Functionsを見送り、Lambda内ロジックで簡易実装する(spec.md Assumptionsに明記済み)。この判断はPhase 1内部の実装方式選択であり、Phase 1→Phase 2の順序やPhase 2内のStep 0〜4には影響しない |
| IV. リソースタグ付けの必須化 | PASS | `core/providers.tf` の `provider "aws"` に `default_tags`(Project="serverless-core-agent-aws", ManagedBy="terraform", Phase="core")が設定済みのため、`core/` 配下に追加する新規リソースは明示的な `tags` 指定なしでも自動的にタグ付けされる |
| V. コミットメッセージ規約 | N/A(実装フェーズで適用) | 実装時のコミットは日本語で簡潔に記述する運用を継続する |

**補足(ブロッキングではない推奨事項)**: docs/proposal.md 5節は「AWS Budgetsを最初から導入」する
方針を示している。本フィーチャーのスコープ(チケット管理APIの実装)には含めないが、Lambda/API
Gateway/DynamoDBのオンデマンド課金は使用量に応じて発生するため、実装完了後の早い段階で
AWS Budgetsアラートを別途設定することを推奨する(constitution原則Iの「リソース追加時は
AWS Budgetsのアラート設定を意識すること」に対応。別タスクとして扱う)。

**Gate結果**: 違反なし。Complexity Trackingへの記載は不要。

## Project Structure

### Documentation (this feature)

```text
specs/001-ticket-management/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.md           # Phase 1 output
├── checklists/
│   └── requirements.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

constitution(CLAUDE.md)の規約により、Phase 1のTerraform・Lambdaコードはすべて `core/` 配下に
配置する(リポジトリ直下の `src/` は使わない)。

```text
core/
├── providers.tf              # 既存(backend "s3" / provider "aws" / default_tags)。変更なし
├── main.tf                   # 既存(リハビリ用S3バケット)。変更なし
├── dynamodb.tf                # 新規: チケットテーブル + GSI(StatusIndex)
├── lambda.tf                  # 新規: ticket-api Lambda関数 + アーカイブ + IAMロール/ポリシー
├── api_gateway.tf             # 新規: REST API、リソース/メソッド、Lambdaプロキシ統合
├── outputs.tf                  # 新規: API GatewayエンドポイントURL等の出力
├── src/
│   └── ticket_api/
│       ├── handler.py         # Lambdaエントリポイント(ルーティング)
│       ├── models.py          # Ticket / HistoryEntry のデータ構造・入力バリデーション
│       ├── state_machine.py   # 許可された状態遷移の定義・判定ロジック
│       ├── repository.py      # DynamoDBアクセス層(Put/Get/Query/Scan/TransactWrite)
│       └── errors.py          # ドメインエラー型(ValidationError/NotFoundError/InvalidTransitionError)
└── tests/
    └── ticket_api/
        ├── unit/
        │   ├── test_state_machine.py
        │   ├── test_models.py
        │   └── test_handler.py
        └── integration/
            └── test_repository.py   # moto使用、DynamoDB操作の結合テスト
```

**Structure Decision**: 単一プロジェクト構成(Option 1相当)を `core/` 配下に配置する。API面が
5エンドポイントと小規模であるため、Lambda関数は分割せず単一関数+内部ルーティングとする
(詳細はresearch.md 1節)。Terraformリソースはファイル種別ごとに分割し(`dynamodb.tf` /
`lambda.tf` / `api_gateway.tf`)、既存の `providers.tf` / `main.tf` には手を入れない。

## Complexity Tracking

*Constitution Checkに違反なし。本セクションへの記載事項なし。*
