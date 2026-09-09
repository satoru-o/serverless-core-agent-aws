# Data Model: チケット管理基幹システム

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

## エンティティ

### Ticket(チケット)

| 属性 | 型 | 必須 | 説明 |
|---|---|---|---|
| `ticket_id` | string (UUID) | ○ | 一意識別子。作成時にサーバー側で自動採番(FR-002) |
| `title` | string | ○ | チケットのタイトル。空文字不可(FR-004) |
| `description` | string | – | チケットの説明。未指定時は空文字として保持(spec.md Assumptions) |
| `assignee` | string | ○ | 担当者。実在ユーザーとして検証しない自由文字列(FR-017)。空文字不可(FR-004) |
| `status` | enum(`OPEN` \| `IN_PROGRESS` \| `DONE`) | ○ | 現在の状態。作成時は必ず `OPEN`(FR-003) |
| `created_at` | string (ISO 8601, UTC) | ○ | 作成日時。以後不変 |
| `updated_at` | string (ISO 8601, UTC) | ○ | 直近の更新日時。状態変更のたびに更新 |

**バリデーションルール**:
- `title`・`assignee` はトリム後に空文字であってはならない(FR-004)
- `status` は `OPEN` / `IN_PROGRESS` / `DONE` の3値以外を取らない
- 作成APIでは `status` をクライアントから直接指定できない(常に `OPEN` で開始、FR-003)

### StatusChangeHistory(状態変更履歴)

| 属性 | 型 | 必須 | 説明 |
|---|---|---|---|
| `ticket_id` | string (UUID) | ○ | 対象チケットのID |
| `from_status` | enum \| null | ○ | 変更前の状態。チケット作成時のレコードは `null` |
| `to_status` | enum | ○ | 変更後の状態(作成時は `OPEN`) |
| `changed_at` | string (ISO 8601, UTC) | ○ | 変更が成立した日時 |

**ルール**:
- 実際に成立した状態変更(作成時の初期状態確定を含む)のみを記録する(FR-013, FR-015)
- 拒否された遷移の試みは記録しない(FR-015)
- 1つのチケットに対して時系列順に複数レコードを持ちうる(1:N)

## 状態遷移(ステートマシン)

```
        ┌────────────────────────────┐
        │                            │
        ▼                            │ 差し戻し
    [OPEN(発行)] ──対応開始──▶ [IN_PROGRESS(対応中)] ──完了──▶ [DONE(完了)]
```

**許可される遷移(この3つ以外は全てエラー / FR-011, FR-012)**:

| from | to | 意味 |
|---|---|---|
| `OPEN` | `IN_PROGRESS` | 対応開始 |
| `IN_PROGRESS` | `DONE` | 完了 |
| `IN_PROGRESS` | `OPEN` | 差し戻し |

**禁止される遷移の例(エラーとして拒否、対象チケットの状態は変化しない)**:
- `DONE` → `OPEN`(完了から発行への直接差し戻し)
- `DONE` → `IN_PROGRESS`
- `OPEN` → `DONE`(対応中を飛ばした直接完了)
- 同一状態への遷移(`OPEN` → `OPEN` 等、自己ループは定義された遷移集合に含まれないため拒否)

## DynamoDB 物理データモデル(シングルテーブル設計)

テーブル名: `core-tickets`(仮。Terraformで定義、詳細命名は実装時に確定)

| PK | SK | 用途 | 主な属性 |
|---|---|---|---|
| `TICKET#<ticket_id>` | `METADATA` | チケット本体 | `title`, `description`, `assignee`, `status`, `created_at`, `updated_at` |
| `TICKET#<ticket_id>` | `HISTORY#<ISO8601>#<uuid接尾辞>` | 状態変更履歴 | `ticket_id`, `from_status`, `to_status`, `changed_at` |

**GSI: `StatusIndex`**(状態フィルタ付き一覧取得用)

| GSI1PK | GSI1SK | 対象 |
|---|---|---|
| `STATUS#<status>` | `<created_at>#<ticket_id>` | `METADATA` レコードのみに付与(履歴レコードにはGSI属性を設定しない) |

**アクセスパターンとの対応**:

| ユーザーストーリー | 操作 | DynamoDB操作 |
|---|---|---|
| US1 作成 | チケット作成 | `PutItem`(METADATAレコード)+ `PutItem`(初回HISTORYレコード、`from_status=null, to_status=OPEN`)。整合性のため `TransactWriteItems` で2件を同時書き込み |
| US2 状態遷移 | 状態変更 | `GetItem` で現状態取得 → 遷移可否をアプリ側で判定 → 可の場合 `TransactWriteItems`(METADATAの`status`/`updated_at`更新 + 新規HISTORYレコード追加、`ConditionExpression`で書き込み時点の`status`が`GetItem`時点の値と一致することを確認)。この条件式はTOCTOU(GetItemとTransactWriteItemsの間に別リクエストが割り込むケース)を防ぐための必須のガードであり、FR-012(未定義遷移の拒否)・FR-013(履歴の`from_status`の正確性)を競合環境下でも成立させるための基本的な整合性担保であって、対象外とする高度なリトライ・分散ロックとは区別する(spec.md Assumptions参照)。条件不一致時の扱いはcontracts/api.mdを参照 |
| US3 一覧取得(フィルタなし) | 全件取得 | `Scan` + `FilterExpression begins_with(SK, "METADATA")` |
| US3 一覧取得(状態フィルタ) | 状態別取得 | `Query` on `StatusIndex`(`GSI1PK = STATUS#<status>`) |
| US4 単体取得 | ID指定取得 | `GetItem`(`PK=TICKET#<id>, SK=METADATA`) |
| US5 履歴取得 | ID指定で履歴一覧 | `Query`(`PK=TICKET#<id>, SK begins_with "HISTORY#"`) |

## エラーモデル

API層で返すエラーは種別を区別できる形にする(実装詳細はcontracts参照):

| ケース | 対応するHTTPステータス(想定) | 該当要件 |
|---|---|---|
| 必須項目(title/assignee)欠落・空文字 | 400 | FR-004 |
| 不正な状態フィルタ値 | 400 | FR-007 |
| 存在しないticket_id指定 | 404 | FR-009 |
| 定義されていない状態遷移 | 409 (Conflict) | FR-012 |
| その他予期しないサーバーエラー | 500 | SC-005(内部エラーで不定終了しない) |
