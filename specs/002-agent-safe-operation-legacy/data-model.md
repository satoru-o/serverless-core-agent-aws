# Data Model: チケット管理エージェントの安全運用基盤

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

spec.mdのKey Entitiesは、基本的に既存のAWSサービスの実行状態・ログとして実体化する
(専用テーブルは持たない)。ただし承認/却下リンクのプリフェッチ対策(research.md §11)の
ために、消費状態を記録する小さなDynamoDBテーブルを1つ新設する。

## エンティティと実体化先

### エージェント実行 (Agent Run)

| 属性 | 型 | 説明 |
|---|---|---|
| `run_id` | string | `decision` Lambdaの呼び出しID(CloudWatch Logsのリクエストid) |
| `started_at` / `ended_at` | string (ISO 8601, UTC) | Lambda呼び出しの開始・終了時刻 |
| `processed_tickets` | list\<string\> | 処理対象としたチケットIDの一覧 |
| `outcome` | enum(`completed` \| `limit_reached` \| `error`) | 実行結果 |

**実体化先**: 専用テーブルは持たず、`decision` LambdaのCloudWatch Logs(1呼び出し=1ログ
ストリーム)として記録される。承認が必要になった場合は、対応するStep Functions実行
(実行ARN)が同一の「1回の判断」に紐づく。

### 操作記録 (Operation Log)

| 属性 | 型 | 必須 | 説明 |
|---|---|---|---|
| `timestamp` | string (ISO 8601, UTC) | ○ | ログ出力時刻 |
| `actor` | enum(`decision` \| `apply_decision` \| `apply_rejection` \| `approval_callback` \| `budget_stop`) | ○ | 記録した主体(research.md §3のLambda) |
| `ticket_id` | string (UUID) \| null | – | 対象チケットID(チケットに紐づかない操作はnull) |
| `action` | string | ○ | 例: `GET_TICKET`, `LIST_TICKETS`, `TRANSITION_IN_PROGRESS`, `TRANSITION_DONE`, `TRANSITION_OPEN`, `REQUEST_APPROVAL`, `APPROVE`, `REJECT`, `TIMEOUT`, `EXECUTION_LIMIT_REACHED`, `UNAUTHORIZED_ATTEMPT`, `BUDGET_STOP` |
| `result` | enum(`success` \| `rejected` \| `error`) | ○ | 操作の結果(FR-008, FR-009) |
| `detail` | string | – | 人間が読める補足情報 |

**実体化先**: CloudWatch Logs上の構造化JSON(1行1レコード)。運用者は
CloudWatch Logs Insightsで`timestamp`範囲を指定してクエリすることで、FR-010(任意の期間の
参照)を満たす。`UNAUTHORIZED_ATTEMPT`(許可範囲外の操作が拒否された記録)はAPI Gatewayが
返す`403`をクライアント側(Lambda)がキャッチして記録する。

**ルール**:
- 実際に行われた操作・拒否された操作の両方を記録する(FR-008, FR-009)
- 承認された・却下された・タイムアウトした重大操作の判断結果も記録する

### 承認依頼 (Approval Request)

| 属性 | 型 | 必須 | 説明 |
|---|---|---|---|
| `execution_arn` | string | ○ | 承認ステートマシンの実行ARN(一意識別子) |
| `ticket_id` | string (UUID) | ○ | 対象チケットID |
| `requested_action` | string(固定値 `TRANSITION_DONE`) | ○ | 依頼対象の操作 |
| `task_token` | string | ○ | `waitForTaskToken`が発行するトークン(承認/却下リンクに埋め込む) |
| `requested_at` | string (ISO 8601, UTC) | ○ | 依頼発行時刻 |
| `status` | enum(`PENDING` \| `CONFIRMING` \| `APPROVED` \| `REJECTED` \| `TIMED_OUT`) | ○ | 現在の状態 |

**実体化先**: Step Functionsの実行そのもの(`RequestApproval`ステートで一時停止している間の
実行コンテキスト)。`status`はステートマシンの実行履歴・遷移先ステートに加え、下記の
「承認リンク消費状態」の有無で判定できる。`CONFIRMING`は、通知リンクへの初回アクセスは
あったが、確認ページ上での明示的な確認操作はまだ行われていない状態を指す
(research.md §11の2段階確認方式)。

### 承認リンク消費状態 (Approval Link Consumption)

承認/却下の通知リンクへのプリフェッチ・事前スキャンによって重大操作が誤って実行されない
ようにするための状態(research.md §11、FR-016)。

| 属性 | 型 | 必須 | 説明 |
|---|---|---|---|
| `task_token` | string | ○(PK) | 対象の承認依頼のタスクトークン |
| `decision` | enum(`approve` \| `reject`) | ○ | 通知リンクに埋め込まれていた決定内容 |
| `consumed_at` | string (ISO 8601, UTC) | ○ | 通知リンクへの初回アクセス時刻(確認ページを表示した時刻) |
| `confirmed_at` | string (ISO 8601, UTC) \| null | – | 確認ページ上で明示的に確認した時刻。未確認の間は`null` |
| `ttl` | number (epoch seconds) | ○ | DynamoDB TTL。`consumed_at`+25時間程度で自動削除(承認ステートマシンの24時間タイムアウトより長く取る) |

**実体化先**: 新規DynamoDBテーブル `agent-approval-links`(オンデマンドキャパシティモード、
`PK = task_token`)。`PutItem`は`attribute_not_exists(task_token)`条件で行い、同一トークンへの
複数回アクセス(プリフェッチの繰り返し等)があっても`consumed_at`は最初の1回のみ記録される。
`confirmed_at`の更新も`attribute_not_exists(confirmed_at)`条件で行い、確認の二重実行を防ぐ。

**ルール**:
- `consumed_at`が記録されるだけでは、Ticket APIへのいかなる書き込みも発生しない(FR-016)
- `confirmed_at`が記録された時点で初めて、対応するStep Functionsタスクへ
  `SendTaskSuccess` / `SendTaskFailure`を送信する

## 状態モデル(承認ステートマシン)

```
[RequestApproval] (Task, waitForTaskToken, TimeoutSeconds=86400)
  → SNSで承認リンク・却下リンクを通知(リンク自体はまだ何も実行しない)
  │
  │  GET /approvals?token=...&decision=approve|reject (プリフェッチされうる)
  ▼
[承認リンク消費状態: consumed_at 記録] ── ここではSendTaskSuccess/Failureを呼ばない
  │  確認ページを表示し、人間の明示的なクリックを待つ
  │
  │  GET /approvals/confirm?token=... (確認ページ内のリンクを能動的にクリックした場合のみ到達)
  ▼
[承認リンク消費状態: confirmed_at 記録] ── ここで初めてSendTaskSuccess/Failureを呼ぶ
  │
  ├─ decision=approve ──▶ [ApplyDecision]   … PATCH .../status = DONE          ─▶ [Success]
  └─ decision=reject  ──▶ [ApplyRejection] … PATCH .../status = OPEN(差し戻し) ─▶ [Success]

  TimeoutSeconds超過(States.Timeout、confirmed_atが記録されないまま24時間経過)
    ─▶ NotifyTimeout(ログ記録のみ、チケットは無変更) ─▶ [Success]
```

**遷移の意味**:

| 分岐 | 対応するTicket API操作 | チケットの状態変化 | 該当要件 |
|---|---|---|---|
| 承認 (approve) | `PATCH /tickets/{id}/status` `{"status": "DONE"}` | `IN_PROGRESS → DONE` | FR-012 |
| 却下 (reject) | `PATCH /tickets/{id}/status` `{"status": "OPEN"}` | `IN_PROGRESS → OPEN`(差し戻し) | FR-013 |
| タイムアウト | なし(Ticket APIを呼ばない) | 変化なし(保留状態を維持) | FR-014, FR-015 |
| 通知リンクへの初回アクセス(プリフェッチ含む) | なし(Ticket APIもStep Functionsも呼ばない) | 変化なし | FR-016 |

001の状態遷移(`OPEN → IN_PROGRESS → DONE`、`IN_PROGRESS → OPEN`)はPhase 1の既存定義を
そのまま利用し、本フィーチャーで新しい状態やAPIを追加することはない(スコープ外要件:
Phase 1の業務ロジック変更なし)。

## コストしきい値 (Budget Threshold)

| 属性 | 型 | 説明 |
|---|---|---|
| `limit_amount` | number | 月次予算額(USD、Terraform変数で調整可能) |
| `threshold_percent` | number | 通知・停止のトリガーとなる実際コストの割合(例: 80 / 100) |
| `cost_filter` | `TagKeyValue = "user:Phase$agent"` | Phase 2(agent)のリソースコストのみを対象にする |

**実体化先**: `aws_budgets_budget`(Terraformリソース)。しきい値到達時、SNS通知経由で
`budget_stop` Lambdaが起動する(research.md §5)。

## IAMロールと許可操作の対応表(FR-001/FR-002の実装マッピング)

| ロール(Lambda) | 許可される操作 | 拒否される操作の例 |
|---|---|---|
| `decision` | `GET /tickets`, `GET /tickets/{id}`, `PATCH /tickets/{id}/status`(コード上`IN_PROGRESS`のみ発行)、`bedrock:InvokeModel`(下記参照) | `POST /tickets`(作成)、Ticket API以外のAWSリソースへのアクセス |
| `apply_decision` | `PATCH /tickets/{id}/status`(`DONE`) | 上記以外のTicket API操作、`states:*` |
| `apply_rejection` | `PATCH /tickets/{id}/status`(`OPEN`) | 上記以外のTicket API操作、`states:*` |
| `approval_callback` | `states:SendTaskSuccess`, `states:SendTaskFailure`(対象ステートマシンのみ)、`dynamodb:GetItem`/`PutItem`/`UpdateItem`(`agent-approval-links`テーブルのみ) | Ticket APIへの一切のアクセス |
| `budget_stop` | `events:DisableRule`(対象ルールのみ) | Ticket API・Step Functionsへの一切のアクセス |

IAMは「呼び出せるAPI・メソッド」までは制御できるが「PATCHのリクエストボディの値」までは
区別できないため、`decision`のIAMポリシー上は`PATCH /tickets/{id}/status`自体を許可せざるを
得ない。その代わり、`decision`のコードが`DONE`への遷移を発行するロジックを一切持たない
(そのロジックは`apply_decision`にしか実装しない)ことで、実質的にFR-011(重大操作の
自動実行禁止)を担保する(research.md §3)。

### `decision`ロールのBedrock関連IAMポリシー

`ap-northeast-1`ではAmazon Nova Microをクロスリージョン推論プロファイル経由でしか
呼び出せない(research.md §2)。Bedrockはこの場合、呼び出し元のIAMポリシーに
**推論プロファイルARN**と、そのプロファイルがルーティングしうる**基盤モデルARN**の
両方への許可を要求する。`decision`ロールには次の2つのResourceを持つ
`bedrock:InvokeModel`許可を付与する(Converse APIの呼び出しも、IAM上は
`bedrock:Converse`ではなく`bedrock:InvokeModel`アクションで認可される。実機デプロイ時に
`AccessDeniedException`で判明、research.md §2参照)。

```
"Resource": [
  "arn:aws:bedrock:ap-northeast-1:<ACCOUNT_ID>:inference-profile/apac.amazon.nova-micro-v1:0",
  "arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0"
]
```

推論プロファイルARNはアカウント・リージョン(呼び出し元のリージョン)を含むのに対し、
基盤モデルARNはアカウントを含まず、実際にルーティングされうる複数リージョンをカバーする
ためリージョン部分をワイルドカードにする(AWS推奨パターン)。どちらか一方が欠けると
`AccessDeniedException`になる。
