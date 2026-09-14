# Contract: 承認フロー(Step Functions wait-for-task-token)

**Feature**: [../spec.md](../spec.md) | **Data Model**: [../data-model.md](../data-model.md)

承認/却下は、通知リンクの単純なアクセス(メールクライアントのプリフェッチ・セキュリティ
製品のリンクスキャン等を含む)だけでは実行されない2段階方式とする(FR-016、research.md §11)。

## ステートマシンの入力

`decision` Lambdaが重大操作(チケットの完了)が必要と判断した際、承認用ステートマシンを
`states:StartExecution` で起動する。

```json
{
  "ticket_id": "uuid",
  "requested_action": "TRANSITION_DONE",
  "requested_at": "ISO8601"
}
```

## SNS通知メッセージ(承認依頼)

`RequestApproval` ステートに入った時点で、SNSトピック `agent-approval-request` へ以下の
形式で発行する(サブスクライバ: 運用者のメールアドレス。Slack通知を追加する場合は同トピックに
Chatbot等のサブスクライバーを追加する)。

```json
{
  "subject": "チケット完了の承認依頼: {ticket_id}",
  "message": "チケット {ticket_id} を「完了」にする操作の承認を求めています。\n承認: {approve_url}\n却下: {reject_url}\n(このリンクを開いても即座には確定しません。内容を確認したうえで確認ページ上のボタンを押してください。リンクは24時間有効です。応答がない場合、操作は実行されず保留のままになります)"
}
```

`{approve_url}` は `GET {base}/approvals?token={task_token}&decision=approve`、
`{reject_url}` は `GET {base}/approvals?token={task_token}&decision=reject`。

## Step 1: 通知リンク(確認ページの表示のみ、副作用なし)

```
GET /approvals?token={task_token}&decision=approve|reject
```

- **認可**: `NONE`(署名不要の公開エンドポイント)。`task_token` はStep Functionsが発行する
  長いランダム文字列であり、これ自体が知識ベースの認可情報として機能する
- **処理**(`approval_callback` Lambda):
  1. `agent-approval-links` テーブルに対し、`PK=task_token` のアイテムを
     `attribute_not_exists(task_token)` 条件付きで `PutItem`(`decision`, `consumed_at=now`,
     `confirmed_at=null`, `ttl=now+25h`)。条件不一致(既に存在)の場合は何もせず
     既存アイテムをそのまま使う
  2. `states:SendTaskSuccess` / `states:SendTaskFailure` は**呼ばない**
  3. 既に `confirmed_at` が設定済み(=Step 2まで完了済み)であれば「既に処理済みです」
     ページを返す
  4. それ以外は「本当に{承認|却下}しますか?」という確認ページ(HTML)を返す。ページ内には
     Step 2のURL(`/approvals/confirm?token={task_token}&decision=...`)への
     リンク/ボタンを埋め込む。このURLは通知メール本文には含まれないため、メール
     クライアントやセキュリティ製品によるプリフェッチの対象にはならない
- **Response 200**: 確認ページ(HTML)、または「既に処理済みです」ページ
- **Response 400/404**: `token` が存在しない・形式不正な場合

## Step 2: 確認ページ内のリンク(実際に状態を変更する)

```
GET /approvals/confirm?token={task_token}&decision=approve|reject
```

- **認可**: `NONE`。ただしStep 1で発行された `agent-approval-links` のアイテムが存在し、
  かつ `confirmed_at` が未設定であることを前提条件とする
- **処理**(`approval_callback` Lambda):
  1. `agent-approval-links` から `task_token` のアイテムを取得。存在しない、または
     `decision` が渡された値と一致しない場合は `400`
  2. `confirmed_at` が既に設定済みなら「既に処理済みです」ページを返し、
     `states:SendTaskSuccess`/`Failure` は呼ばない(二重実行防止)
  3. 未設定なら `attribute_not_exists(confirmed_at)` 条件付きで `confirmed_at=now` に
     `UpdateItem`。成功した場合のみ、`decision=approve` なら
     `states:SendTaskSuccess(taskToken, output={"decision": "approve"})`、
     `decision=reject` なら `states:SendTaskFailure(taskToken, error="Rejected")` を呼ぶ
     (却下はエラーとして扱い、ステートマシンのCatchで`ApplyRejection`へ分岐させる)
- **Response 200**: 「承認/却下を受け付けました。処理を実行します。」という完了ページ
- **Response 400/404**: `token` が無効・Step 1未実施・期限切れの場合

## タイムアウト時の挙動

`RequestApproval` の `TimeoutSeconds`(86400秒 = 24時間)を超過すると、Step Functionsが
`States.Timeout` エラーを発行する。これを `Catch` で捕捉し `NotifyTimeout` ステートに遷移する。
`NotifyTimeout` はTicket APIを一切呼ばず(チケットの状態は変更しない)、
`TIMEOUT` の操作記録(data-model.md)をCloudWatch Logsに残すのみ。Step 1のみが行われ
Step 2(確認)が行われないまま24時間が経過した場合も、このタイムアウト経路に合流する
(`agent-approval-links` のアイテムはTTLにより自動的に削除される)。

## 実行結果の記録

`ApplyDecision` / `ApplyRejection` / `NotifyTimeout` の各Lambda(または直接のログ出力)は、
data-model.mdの「操作記録」フォーマットで結果をCloudWatch Logsに記録する
(`action` は `APPROVE` / `REJECT` / `TIMEOUT`、対応する `TRANSITION_DONE` /
`TRANSITION_OPEN` も併記する)。Step 1のアクセス(プリフェッチ含む)自体も
`REQUEST_APPROVAL`とは区別される形で軽量に記録してよいが、`result`は常に`success`
(=「消費済みにマークしただけ」)であり、チケットの状態変更を伴わないことをログ上も
明確にする。
