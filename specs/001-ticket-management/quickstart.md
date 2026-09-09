# Quickstart: チケット管理基幹システムの動作確認

**Feature**: [spec.md](./spec.md) | **API Contract**: [contracts/api.md](./contracts/api.md)

このガイドは、実装完了後に「仕様通り動くこと」をエンドツーエンドで確認するための手順。
リクエスト/レスポンスの詳細スキーマは [contracts/api.md](./contracts/api.md)、状態遷移ルールは
[data-model.md](./data-model.md) を参照。

## 前提条件

- AWS CLIプロファイル `sca-aws` が設定済み(`~/.aws/credentials` / `~/.aws/config`)
- Terraform `~> 1.16` がインストール済み
- Python 3.13(ローカルでの単体テスト実行用)
- `core/` 配下にこのフィーチャーの実装(Terraformリソース + Lambdaソース)が完了している

## 1. 単体テストの実行(デプロイ前の確認)

```bash
cd core
python -m pytest tests/ -v
```

**期待結果**: 状態遷移ロジック(許可される3遷移・禁止される遷移の拒否)、必須項目バリデーション、
DynamoDBアクセス層(moto使用)のテストがすべて成功する。

## 2. Terraformでのデプロイ

```bash
cd core
terraform init
terraform plan
terraform apply
```

**期待結果**:
- `aws_dynamodb_table`、`aws_lambda_function`、`aws_api_gateway_rest_api` 等が新規作成される
- `terraform plan` の差分に、constitution原則IV(タグ付け必須化)に反するリソース(タグなし)が
  含まれない(`default_tags` により Project/ManagedBy/Phase が自動付与されていることを確認)
- `terraform apply` 完了後、出力(output)としてAPI GatewayのエンドポイントURLが表示される

## 3. API経由での動作確認(curl例)

以下、`API_URL` はTerraform出力のAPI GatewayエンドポイントURLに読み替える。

### 3.1 チケット作成(US1)

```bash
curl -sX POST "$API_URL/tickets" \
  -H "Content-Type: application/json" \
  -d '{"title": "サンプルチケット", "description": "動作確認用", "assignee": "satoru-o"}'
```

**期待結果**: `201`、`status: "OPEN"` のチケットが返る。レスポンスの `ticket_id` を以降の手順で使う。

### 3.2 単体取得(US4)

```bash
curl -s "$API_URL/tickets/<ticket_id>"
```

**期待結果**: `200`、手順3.1で作成した内容と一致するチケットが返る(SC-001)。

### 3.3 一覧取得・状態フィルタ(US3)

```bash
curl -s "$API_URL/tickets"
curl -s "$API_URL/tickets?status=OPEN"
curl -s "$API_URL/tickets?status=INVALID"
```

**期待結果**: 1件目は登録済み全チケット、2件目は `OPEN` のチケットのみ、3件目は `400`
(不正な状態フィルタ、FR-007)。

### 3.4 正しい状態遷移(US2)

```bash
curl -sX PATCH "$API_URL/tickets/<ticket_id>/status" \
  -H "Content-Type: application/json" -d '{"status": "IN_PROGRESS"}'

curl -sX PATCH "$API_URL/tickets/<ticket_id>/status" \
  -H "Content-Type: application/json" -d '{"status": "OPEN"}'

curl -sX PATCH "$API_URL/tickets/<ticket_id>/status" \
  -H "Content-Type: application/json" -d '{"status": "IN_PROGRESS"}'

curl -sX PATCH "$API_URL/tickets/<ticket_id>/status" \
  -H "Content-Type: application/json" -d '{"status": "DONE"}'
```

**期待結果**: 4回とも `200`。それぞれ `OPEN→IN_PROGRESS→OPEN(差し戻し)→IN_PROGRESS→DONE` と
状態が遷移する。

### 3.5 定義されていない遷移の拒否(US2 / SC-002)

```bash
curl -sX PATCH "$API_URL/tickets/<ticket_id>/status" \
  -H "Content-Type: application/json" -d '{"status": "OPEN"}'
```
(直前の手順で `<ticket_id>` は `DONE` になっている想定)

**期待結果**: `409`(`INVALID_TRANSITION`)。手順3.2で単体取得すると、状態が `DONE` のまま
変化していないことを確認する。

### 3.6 履歴の追跡(US5 / SC-003)

```bash
curl -s "$API_URL/tickets/<ticket_id>/history"
```

**期待結果**: `200`。作成時の記録(`from_status: null, to_status: "OPEN"`)を含め、手順3.4で
成立した4回の遷移が発生順に記録されている。手順3.5で拒否された遷移は含まれていないこと
(FR-015)を確認する。

### 3.7 存在しないIDへのアクセス

```bash
curl -s "$API_URL/tickets/00000000-0000-0000-0000-000000000000"
```

**期待結果**: `404`(`NOT_FOUND`、FR-009)。

## 4. 完了条件チェック(spec.mdとの対応)

- [ ] SC-001: 作成直後の一覧・単体取得で内容が確認できる(手順3.1〜3.3)
- [ ] SC-002: 未定義遷移が100%拒否され状態が変化しない(手順3.5)
- [ ] SC-003: すべての成立した状態変更が履歴から追跡できる(手順3.6)
- [ ] SC-004: UIなしでAPI呼び出しのみで一連の操作が完結する(本ガイド全体がcurlのみで完結)
- [ ] SC-005: 不正な入力(存在しないID・不正フィルタ)に対し分かりやすいエラーが返る
      (手順3.3, 3.7)
