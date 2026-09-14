# Quickstart: チケット管理エージェントの安全運用基盤の動作確認

**Feature**: [spec.md](./spec.md) | **Contracts**: [contracts/](./contracts/)

このガイドは、実装完了後にP1(権限制御+暴走防止)・P2(操作履歴の追跡)・P3(人間承認)が
仕様どおり動くことをエンドツーエンドで確認するための手順。詳細な設計は
[research.md](./research.md)・[data-model.md](./data-model.md)・[contracts/](./contracts/)
を参照。

## 前提条件

- AWS CLIプロファイル `sca-aws` が設定済み
- Terraform `~> 1.16` がインストール済み
- Python 3.13
- `specs/001-ticket-management` のPhase 1実装がデプロイ済み(完了条件を満たしている)
- AWSコンソールのBedrock Model accessで `amazon.nova-micro-v1:0` のモデルアクセスが有効化
  済み(クロスリージョン推論プロファイル経由での呼び出しに必要、research.md §2)
- `core/`(認可方式のAWS_IAM化)・`agent/`(本フィーチャー)の実装がいずれも完了している

## 1. 単体テストの実行(デプロイ前の確認)

```bash
cd agent
python -m pytest tests/ -v
```

**期待結果**: 実行回数上限・タイムアウトの判定ロジック、Ticket APIクライアントの
SigV4署名付与、各Lambdaの権限分離(モックしたIAM境界)に関するテストがすべて成功する。

## 2. Terraformでのデプロイ

```bash
# 2.1 core/: Ticket APIの認可方式変更(NONE → AWS_IAM)を反映
cd core
terraform plan
terraform apply

# 2.2 agent/: 新規リソース一式
cd ../agent
terraform init
terraform plan
terraform apply
```

**期待結果**:
- `core/`側: 既存の `aws_api_gateway_method` の `authorization` が `AWS_IAM` に変わる
  (リソースの作成・削除は発生せず、属性の更新のみ)
- `agent/`側: Lambda関数4つ、EventBridgeルール、Step Functionsステートマシン、SNSトピック、
  AWS Budgets、承認コールバック用API Gatewayが新規作成される
- いずれのリソースも `terraform plan` の差分にタグなしリソース(constitution原則IV違反)が
  含まれない

## 3. P1: 権限制御・暴走防止の確認

### 3.1 許可されていない操作が拒否されること(FR-001, FR-002, SC-002)

`decision` ロールの認証情報を使って、許可されていないメソッド(例: `POST /tickets`)を
SigV4署名付きで呼び出す。

**期待結果**: `403 Forbidden`(API Gatewayの認可レベルで拒否される)。CloudWatch Logsに
`UNAUTHORIZED_ATTEMPT` の操作記録が残る(手順4で確認)。

### 3.2 実行回数上限(FR-003)

テスト用に大量(上限を超える件数)の対応待ちチケットを作成した状態で `decision` Lambdaを
手動実行する。

**期待結果**: 上限(既定20回)に達した時点でTicket API呼び出しが止まり、
`EXECUTION_LIMIT_REACHED` の操作記録が残る。Lambda自体は異常終了せず正常終了する。

### 3.3 コストしきい値超過時の自動停止(FR-005, FR-006, SC-003)

`aws_budgets_budget` のしきい値をテスト用に低い値に一時変更するか、SNSトピックへ
100%到達相当のテストメッセージを手動発行して `budget_stop` Lambdaを実行させる。

**期待結果**: `decision` Lambdaをトリガーしていた EventBridge ルールが `DISABLED` になる。
運用者向けの停止通知が届く。

### 3.4 初回リリース時点からの同時有効性(FR-007, SC-001)

上記3.1〜3.3の設定が、`agent/` の初回 `terraform apply` 直後から(追加のフラグ変更等
なしに)有効であることを確認する。

## 4. P2: 操作履歴の追跡の確認(FR-008〜FR-010, SC-004)

```bash
aws logs start-query \
  --profile sca-aws \
  --log-group-name /aws/lambda/agent-decision \
  --start-time <過去1週間のUNIX時刻> \
  --end-time <現在のUNIX時刻> \
  --query-string 'fields @timestamp, actor, ticket_id, action, result | sort @timestamp asc'
```

**期待結果**: 指定した期間内にエージェントが実際に行った操作(状態変更)・拒否された操作
(手順3.1のUNAUTHORIZED_ATTEMPT含む)が漏れなく確認できる。

## 5. P3: 人間承認フローの確認(FR-011〜FR-015, SC-005, SC-006)

### 5.1 承認依頼が発行されること

対応中(`IN_PROGRESS`)のチケットについて、エージェントが「完了させるべき」と判断する
状況を作る(または承認用ステートマシンを直接 `StartExecution` する)。

**期待結果**: 対象チケットは `DONE` にならず、運用者にSNS通知(承認リンク・却下リンク)が
届く。

### 5.2 通知リンクへの単純なアクセス(プリフェッチ相当)だけでは実行されないこと(FR-016)

通知内の承認リンク(`GET /approvals?token=...&decision=approve`)に、確認ページ上の
リンクをクリックせずアクセスするだけの状態を作る(例: `curl`でGETするだけ)。

**期待結果**: `200`で確認ページ(HTML)が返るが、チケットは`IN_PROGRESS`のまま変化しない。
Step Functionsの実行は`RequestApproval`で待機したまま。操作記録にチケットの状態変更は
記録されない。

### 5.3 承認した場合

手順5.2の確認ページに含まれる2段階目のリンク(`GET /approvals/confirm?token=...`)に
アクセスする。

**期待結果**: チケットが `IN_PROGRESS → DONE` に遷移する。操作記録に `APPROVE` /
`TRANSITION_DONE` が残る。同じ確認リンクに再度アクセスしても「既に処理済みです」が返り、
チケットは変化しない。

### 5.4 却下した場合

別のチケットに対して、却下リンク(`decision=reject`)への初回アクセス(手順5.2相当)を経て、
確認ページの2段階目のリンクにアクセスする。

**期待結果**: チケットが `IN_PROGRESS → OPEN`(差し戻し)に遷移する。操作記録に `REJECT` /
`TRANSITION_OPEN` が残る。

### 5.5 タイムアウトした場合(Step 1のみで放置、またはStep 1すら行わずに放置)

承認依頼を発行したまま24時間放置する(またはテスト用に`TimeoutSeconds`を短く設定した
別実行で確認する)。手順5.2相当(Step 1のみ)を行った後に確認ページのリンクをクリックせず
放置した場合も同じ結果になることをあわせて確認する。

**期待結果**: チケットの状態は変化しない(保留のまま)。操作記録に `TIMEOUT` が残り、
`DONE`にも`OPEN`にも遷移していないことをチケット単体取得で確認する。

## 6. 完了条件チェック(spec.mdとの対応)

- [ ] SC-001: 権限制限・実行回数上限・コスト超過時の自動停止が初回リリース時点から
      有効(手順3.4)
- [ ] SC-002: 許可されていない操作が例外なく拒否される(手順3.1)
- [ ] SC-003: コストしきい値超過から一定時間以内に新規実行が停止する(手順3.3)
- [ ] SC-004: 任意の過去期間についてエージェントの操作を漏れなく確認できる(手順4)
- [ ] SC-005: 重大操作は人間の承認なしには実行されない(手順5.1, 5.2)
- [ ] SC-006: 却下・タイムアウト時にチケットが安全な状態に保たれる(手順5.4, 5.5)
