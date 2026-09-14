<!--
Sync Impact Report
- Version change: 1.0.0 → 2.0.0
- Rationale: docs/proposal.md 4.3節の改定(Step 0「無防備な状態で動かして危険を体感する」の
  廃止)に追随するMAJOR改定。実運用中のAWSアカウントでは「危険を体感してから直す」ことの
  実害(コスト超過・セキュリティ露出)が教育的価値を上回るため、Principle III(NON-NEGOTIABLE)
  が定めていた段階的構築の順序を、Step 0を含む5段階から、①権限制御・②暴走防止を初回
  リリース時点から同時に満たすStep 1〜3の3段階へ後方非互換に再定義した。
- Modified principles:
  - III. 段階的構築の順序を守る(NON-NEGOTIABLE) — Step 0(無防備な状態で動かす)の実行を
    前提とした記述を削除し、「①権限制御・②暴走防止は初回リリース時点から同時に満たす」
    という要件を追加。根拠も「危険な状態を体感してから対策を追加する」から「実運用中の
    AWSアカウントでは実害が教育的価値を上回る」に更新
- Added sections: なし
- Removed sections: なし(「Phase 2 安全設計ワークフロー」節はStep構成を5段階→3段階に
  更新のうえ維持)
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — Constitution Check セクションは本憲法の原則を
    参照する一般的な記述のみで、追随の要否は各実行時に本ファイルを読み直して判断される
    ため変更不要
  - ✅ .specify/templates/spec-template.md — 本憲法固有の記述なし、変更不要
  - ✅ .specify/templates/tasks-template.md — 本憲法固有の記述なし、変更不要
  - ✅ specs/002-agent-safe-operation/spec.md — 既にStep 0なしの新方針(FR-007等)で
    作成済みのため、本改定と整合している
- Follow-up TODOs: なし
-->

# serverless-core-agent-aws Constitution

## Core Principles

### I. コスト意識ファースト(NON-NEGOTIABLE)
RDS・EC2・Auroraは使用しない。理由は、これらが起動しているだけで常時課金が発生する
サービスであり、学習用リポジトリの運用コストを不必要に増大させるため。新しいAWSリソースを
追加提案する際は、**常時課金が発生しないか**(起動しているだけで課金され続けるものでないか)
を必ず先に確認してから進めなければならない(MUST)。リソース追加時はAWS Budgetsの
アラート設定を意識すること。

**根拠**: 本リポジトリは学習目的であり、想定外の課金は継続的な学習・実験の妨げになる。
コストの安全性を機能追加より優先する。

### II. Infrastructure as Code(Terraform統一)
すべてのAWSリソースはTerraformで定義しなければならない(MUST)。手動でのコンソール
操作によるリソース作成は、ブートストラップ用途に限り許容されるが、その場合は
`ManagedBy = "manual-bootstrap"` タグを付与し、手動作成である旨を明示しなければならない。

**根拠**: 再現性のある環境構築と、変更履歴の追跡可能性を確保するため。IaCの一貫性が
崩れると、Phase 2で扱う「監査・検証」の学習目的そのものが損なわれる。

### III. 段階的構築の順序を守る(NON-NEGOTIABLE)
Phase 1(サーバーレス基幹システム)→ Phase 2(エージェント安全運用)の順に進めなければ
ならない(MUST)。Phase 2はPhase 1が完了するまで着手しない。Phase 2内では、
docs/proposal.md に記載のStep 1〜3(安全設計を段階的に積み上げる順序)を厳守し、
各Stepごとに動作確認してから次のStepに進まなければならない(MUST NOT skip ahead)。
ただし、①権限制御・②暴走防止については、無防備な状態を経ずに初回リリース時点から
同時に満たさなければならない(MUST)。「危険な状態を体感してから直す」進め方は
取らない(MUST NOT)。

**根拠**: 実運用中のAWSアカウント上でエージェントを動かす以上、権限の過大付与や
コスト暴走を実際に体感してから直すアプローチは、コスト超過・セキュリティ露出という
実害を伴い、その実害は教育的価値を上回る。そのため権限制御・暴走防止は初回リリース
時点から同時に満たした上で、③検証・監査、④人間承認をその後の段階として積み上げる。

### IV. リソースタグ付けの必須化
全てのAWSリソースに以下のタグを必須で付与しなければならない(MUST):
- `Project` = `"serverless-core-agent-aws"`
- `ManagedBy` = `"terraform"`(手動作成のブートストラップリソースは `"manual-bootstrap"`)
- `Phase` = `"core"` または `"agent"`(該当するフェーズ)

**根拠**: タグ付けにより、コスト監視・監査証跡・フェーズ別のリソース棚卸しが容易になる。
Phase 2で学習する「検証・監査」の柱とも直接連動する。

### V. コミットメッセージ規約
コミットメッセージは日本語で簡潔に書かなければならない(MUST)(例: "feat: DynamoDB
テーブル定義を追加")。

**根拠**: 本リポジトリの設計判断・議論はすべて日本語(docs/proposal.md、CLAUDE.md)で
記録されており、コミット履歴も同じ言語で一貫させることで、後から経緯を追いやすくする。

## 使用技術・ディレクトリ構成

**中心となるサービス**: Lambda、DynamoDB、API Gateway、Step Functions、EventBridge、
SQS、CloudWatch、CloudTrail、AWS Budgets、SNS。これら以外のサービス(特に常時課金の
発生するもの)を追加する場合は、原則Iに基づき常時課金の有無を確認すること。

**ディレクトリの役割**:
- `core/` : Phase 1(タスク管理の基幹システム)のTerraform・Lambdaコード
- `agent/` : Phase 2(エージェント安全運用)のTerraform・Lambdaコード
- `docs/` : 企画書・設計判断の記録

## Phase 2 安全設計ワークフロー

Phase 2は、権限制御・暴走防止・検証/監査・人間承認の4本柱を、以下の順序で段階的に
積み上げる(docs/proposal.md 4.3参照)。①権限制御・②暴走防止は無防備な初期状態を
経ずに初回リリース時点から同時に満たすため、両者を分けたStepは設けない:

1. Step 1: IAMロールをタスクに必要な範囲まで絞り込み(権限制御)、実行回数上限・
   タイムアウト・AWS Budgets連動の自動停止(暴走防止)とあわせて、初回リリース時点
   から同時に組み込む
2. Step 2: CloudTrail + CloudWatch Logsで全操作を記録し、後から追跡できることを
   確認する(検証・監査)
3. Step 3: 重大操作(完了・差し戻し等)にStep Functions(waitForTaskToken)による
   人間承認フローを組み込む(人間の承認)

各Stepは、前のStepが動作確認済みであることを確認してから着手しなければならない(MUST)。

## Governance

本憲法は、このリポジトリにおけるコスト管理・IaC運用・段階的構築順序・タグ付け・
コミット規約に関する他のすべての慣行に優先する(supersedes all other practices)。

**改訂手続き**: 本憲法の改訂は `/speckit-constitution` コマンドを通じて行う。改訂内容は
Sync Impact Report として本ファイル冒頭にHTMLコメントで記録する。

**バージョニング方針**: セマンティックバージョニング(MAJOR.MINOR.PATCH)に従う。
- MAJOR: 既存原則の後方非互換な削除・再定義
- MINOR: 新しい原則・セクションの追加、または既存ガイダンスの実質的な拡張
- PATCH: 文言の明確化・誤字修正などの非意味的な修正

**コンプライアンスレビュー**: Terraformの変更・新規AWSリソースの追加提案時は、原則I
(コスト意識)・原則II(IaC統一)・原則IV(タグ付け)への準拠を確認すること。Phase 2の
実装作業は、原則III(段階的構築の順序)への準拠を都度確認すること。日常的な作業指針は
[CLAUDE.md](../../CLAUDE.md) を参照し、詳細な背景・設計判断は
[docs/proposal.md](../../docs/proposal.md) を参照すること。

**Version**: 2.0.0 | **Ratified**: 2026-09-05 | **Last Amended**: 2026-09-14
