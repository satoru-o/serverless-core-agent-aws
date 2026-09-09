# API Contract: チケット管理基幹システム

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)

ベースパス: `/tickets`(API Gateway REST API のステージ配下)

すべてのリクエスト・レスポンスボディは `application/json`。認証ヘッダは本フェーズでは要求しない
(spec.md Assumptions: Phase 2で段階的に安全設計を追加する前提)。

## 共通エラーレスポンス形式

```json
{
  "error": {
    "code": "VALIDATION_ERROR | NOT_FOUND | INVALID_TRANSITION | INTERNAL_ERROR",
    "message": "人間が読めるエラー説明"
  }
}
```

| `error.code` | HTTPステータス | 該当要件 |
|---|---|---|
| `VALIDATION_ERROR` | 400 | FR-004, FR-007 |
| `NOT_FOUND` | 404 | FR-009 |
| `INVALID_TRANSITION` | 409 | FR-012 |
| `INTERNAL_ERROR` | 500 | SC-005 |

---

## POST /tickets — チケット作成(US1)

**Request Body**:
```json
{
  "title": "string (required, non-empty)",
  "description": "string (optional, default: \"\")",
  "assignee": "string (required, non-empty)"
}
```

**Response 201 Created**:
```json
{
  "ticket_id": "uuid",
  "title": "string",
  "description": "string",
  "assignee": "string",
  "status": "OPEN",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

**Response 400**: `title` または `assignee` が欠落・空文字(FR-004)

---

## GET /tickets — チケット一覧取得(US3)

**Query Parameters**:
- `status` (optional): `OPEN` | `IN_PROGRESS` | `DONE` のいずれか。省略時は全件返却

**Response 200 OK**:
```json
{
  "tickets": [
    {
      "ticket_id": "uuid",
      "title": "string",
      "description": "string",
      "assignee": "string",
      "status": "OPEN | IN_PROGRESS | DONE",
      "created_at": "ISO8601",
      "updated_at": "ISO8601"
    }
  ]
}
```
チケットが1件もない場合は `"tickets": []` を返す(エラーにしない、Edge Cases参照)。

**Response 400**: `status` に `OPEN` / `IN_PROGRESS` / `DONE` 以外の値が指定された場合(FR-007)

---

## GET /tickets/{ticket_id} — チケット単体取得(US4)

**Path Parameters**: `ticket_id` (uuid)

**Response 200 OK**: POST /tickets のレスポンスと同一スキーマ(単一オブジェクト)

**Response 404**: 指定した `ticket_id` が存在しない(FR-009)

---

## PATCH /tickets/{ticket_id}/status — チケットの状態変更(US2)

**Path Parameters**: `ticket_id` (uuid)

**Request Body**:
```json
{
  "status": "OPEN | IN_PROGRESS | DONE"
}
```
指定する `status` は「変更後の状態」。許可される遷移は data-model.md のステートマシン表を参照
(`OPEN→IN_PROGRESS`, `IN_PROGRESS→DONE`, `IN_PROGRESS→OPEN` の3パターンのみ)。

**Response 200 OK**: 更新後のチケット(POST /tickets のレスポンスと同一スキーマ)

**Response 404**: 指定した `ticket_id` が存在しない(FR-009)

**Response 409**: 現在の状態から指定した状態への遷移が定義されていない(FR-012)。
このとき対象チケットの状態は一切変更されない。

同一チケットへの状態変更要求が競合し、`GetItem`時点の状態と実際の書き込み時点の状態が
異なっていた場合(`ConditionExpression`不一致、TOCTOU)も、同じ `409 INVALID_TRANSITION` を
返す。サーバー側での自動リトライは行わない(高度な排他制御は本フェーズの対象外、
spec.md Assumptions参照)。クライアントは最新の状態を `GET /tickets/{ticket_id}` で
確認した上で、必要であれば改めて状態変更を要求する

**Response 400**: `status` が `OPEN` / `IN_PROGRESS` / `DONE` 以外の値

---

## GET /tickets/{ticket_id}/history — 状態変更履歴取得(US5)

**Path Parameters**: `ticket_id` (uuid)

**Response 200 OK**:
```json
{
  "ticket_id": "uuid",
  "history": [
    {
      "from_status": "OPEN | IN_PROGRESS | DONE | null",
      "to_status": "OPEN | IN_PROGRESS | DONE",
      "changed_at": "ISO8601"
    }
  ]
}
```
`history` は `changed_at` の昇順(発生順)で返す。先頭の要素は作成時のレコード
(`from_status: null, to_status: "OPEN"`)。拒否された遷移の試みは含まれない(FR-015)。

**Response 404**: 指定した `ticket_id` が存在しない(FR-009)
