---

description: "Task list template for feature implementation"
---

# Tasks: チケット管理エージェントの安全運用基盤

**Input**: Design documents from `/specs/002-agent-safe-operation/`

**Prerequisites**: [plan.md](./plan.md)(必須)、[spec.md](./spec.md)(必須・ユーザーストーリー)、
[research.md](./research.md)、[data-model.md](./data-model.md)、
[contracts/](./contracts/)、[quickstart.md](./quickstart.md)

**Tests**: spec.mdはテストを明示要求していないが、plan.mdのTechnical Context(`pytest` + `moto`)、
および001の前例(単体・統合テストを各ストーリーに含める運用)を踏襲し、各ユーザーストーリーに
テストタスクを含める。特にUS1はIAM境界(許可/拒否範囲)の検証、US3は2段階確認方式の
副作用境界(FR-016)の検証を重点的に行う。

**Organization**: タスクはユーザーストーリー(spec.mdのP1〜P3)ごとにグループ化し、各ストーリーを
独立して実装・検証できるようにする。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(異なるファイル、未完了タスクへの依存なし)
- **[Story]**: 対象ユーザーストーリー(US1〜US3、spec.mdの番号に対応)
- 各タスクの説明には正確なファイルパスを含める

## Path Conventions

plan.mdの Project Structure に従う:
- Phase 2(エージェント)のTerraform・Lambdaコードはすべて `agent/` 配下
- Terraform: `agent/*.tf`
- Lambdaソース: `agent/src/ticket_agent/`
- テスト: `agent/tests/ticket_agent/unit/`, `agent/tests/ticket_agent/integration/`
- `core/` への変更は認可方式(`api_gateway.tf`)と出力追加(`outputs.tf`)のみに限定する

## design docsに対する実装レベルの補足(このtasks.mdで新たに具体化した点)

- **`approval_links.py`**: plan.mdのファイル一覧には明示されていないが、`agent-approval-links`
  テーブルへの条件付き読み書き(`mark_consumed` / `mark_confirmed` / `get`)を
  `approval_callback_handler.py` から分離し、単体テスト可能にするための小さなヘルパー
  モジュールとして追加する(001の `repository.py` 分離パターンを踏襲)
- **`NotifyTimeout`**: data-model.mdの操作記録`actor`列挙に専用のLambdaは含まれていないため、
  専用Lambdaは作らず、Step Functionsの`Pass`ステートとして実装する。ステートマシンに
  `logging_configuration`(`level = "ALL"`)を設定し、タイムアウト到達を含む実行履歴を
  専用CloudWatchロググループに記録することでFR-015相当の追跡可能性を担保する
- **`agent/cloudwatch.tf`**: 各LambdaのロググループをTerraformで明示管理し、
  `retention_in_days`(既定30日、spec.md Assumptions)を設定する。デフォルト(無期限保持)の
  ままだと不要なログ保持コストが発生し続けるため

---

## Phase 1: Setup(共有基盤の準備)

**Purpose**: プロジェクトの初期構造・開発依存関係の整備

- [ ] T001 `agent/src/ticket_agent/`、`agent/tests/ticket_agent/unit/`、
      `agent/tests/ticket_agent/integration/` ディレクトリを作成する(各ディレクトリに空の
      `__init__.py` を配置し、pytestのテスト検出・パッケージインポートが機能するようにする)
- [ ] T002 [P] `agent/tests/requirements-dev.txt` を作成し、開発依存(`pytest`, `moto`, `boto3`)を
      記載する(Lambdaデプロイパッケージには含めない)
- [ ] T003 [P] `agent/pyproject.toml` を作成し、`ruff` のlint/format設定
      (`src = ["src/ticket_agent", "tests/ticket_agent"]`)と `pytest` 設定
      (`pythonpath = ["src"]`, `testpaths = ["tests/ticket_agent"]`)を定義する
      (`core/pyproject.toml` を踏襲)

---

## Phase 2: Foundational(全ストーリー共通のブロッキング前提作業)

**Purpose**: いずれのユーザーストーリーの実装にも先立って完了していなければならない共通基盤

**⚠️ CRITICAL**: このフェーズが完了するまで、どのユーザーストーリーの実装にも着手できない

- [ ] T004 [P] Terraform: `core/api_gateway.tf` の全メソッド(`tickets_post` / `tickets_get` /
      `ticket_get` / `ticket_status_patch` / `ticket_history_get`)の `authorization` を
      `"NONE"` から `"AWS_IAM"` に変更する(contracts/ticket-api-access-control.md、
      ユーザー承認済みの変更)
- [ ] T005 [P] Terraform: `core/outputs.tf` に `ticket_api_execution_arn`
      (`aws_api_gateway_rest_api.this.execution_arn`)の出力を追加する
- [ ] T006 Terraform: `agent/providers.tf` に `backend "s3"`(`key = "agent/terraform.tfstate"`、
      バケット・プロファイル・リージョンは`core/`と同一)、`provider "aws"`
      (`default_tags` に `Phase = "agent"` を含む)、`data "terraform_remote_state" "core"`
      (T004, T005で追加した出力を参照するため)を定義する(T004, T005を`core/`に
      `terraform apply`済みであることに依存)
- [ ] T007 [P] Terraform: `agent/variables.tf` に共通変数を定義する
      (`execution_limit`(既定20)、`decision_timeout_seconds`(既定60)、
      `eventbridge_schedule`(既定`"rate(5 minutes)"`)、`budget_limit_usd`、
      `notification_email`、`approval_timeout_seconds`(既定86400)、
      `log_retention_days`(既定30))。すべてTerraform変数として外出しし、
      コードへの固定値埋め込みを避ける(spec.md Assumptions)
- [ ] T008 [P] `agent/src/ticket_agent/errors.py` に `UnauthorizedTicketApiCallError` /
      `TicketApiError` / `ExecutionLimitReachedError` / `InvalidApprovalLinkError` の
      ドメイン例外クラスを定義する
- [ ] T009 `agent/src/ticket_agent/ticket_client.py` にSigV4署名付きTicket APIクライアントを
      実装する: `get_ticket(ticket_id)` / `list_tickets(status=None)` /
      `update_status(ticket_id, status)`。`botocore.auth.SigV4Auth` +
      `botocore.awsrequest.AWSRequest` で署名し `urllib.request` で送信する
      (research.md §7)。レスポンスが `403` の場合は `UnauthorizedTicketApiCallError` に
      変換する(contracts/ticket-api-access-control.md)(T008に依存)
- [ ] T010 [P] `agent/src/ticket_agent/audit_log.py` に
      `log_operation(actor, ticket_id, action, result, detail=None)` を実装する。
      data-model.md「操作記録」のフィールド(`timestamp` / `actor` / `ticket_id` / `action` /
      `result` / `detail`)を持つ構造化JSONを標準出力に書き込む(CloudWatch Logsに
      自動収集される)
- [ ] T011 [P] 単体テスト: SigV4署名・403変換
      `agent/tests/ticket_agent/unit/test_ticket_client.py`(T009に依存)
- [ ] T012 [P] 単体テスト: 操作記録のJSONスキーマ
      `agent/tests/ticket_agent/unit/test_audit_log.py`(T010に依存)

**Checkpoint**: 基盤が完成。以降、各ユーザーストーリーの実装に着手できる

---

## Phase 3: User Story 1 - 最小権限とコスト上限を備えた状態でエージェントを稼働させる(Priority: P1)🎯 MVP

**Goal**: 権限制御(許可された特定のチケットAPI呼び出しのみ)と暴走防止(実行回数上限・
タイムアウト・コスト超過時自動停止)が、エージェントの初回リリース時点から同時に有効になる

**Independent Test**: 許可範囲外操作が拒否されること、実行回数上限・タイムアウト・
コストしきい値のそれぞれを超過させた場合にエージェントの新規実行が自動的に停止することを
確認する(spec.md US1 Acceptance Scenarios)

### Tests for User Story 1

- [ ] T013 [P] [US1] 単体テスト: 実行回数上限の判定
      `agent/tests/ticket_agent/unit/test_decision_handler.py`
      (上限(`EXECUTION_LIMIT`)到達時にそれ以上`ticket_client`を呼ばず
      `EXECUTION_LIMIT_REACHED` を記録して正常終了することを検証、FR-003)
- [ ] T014 [P] [US1] 統合テスト: `decision` ロールのIAM境界
      `agent/tests/ticket_agent/integration/test_iam_boundaries_decision.py`
      (`decision` ロールのIAMポリシードキュメントが `GET /tickets` / `GET /tickets/{id}` /
      `PATCH /tickets/{id}/status` の3メソッドのみを許可し、`POST /tickets` や
      `dynamodb:*` / `states:SendTaskSuccess` 等を一切含まないことを検証、FR-001/002)
- [ ] T015 [P] [US1] 単体テスト: `budget_stop_handler`
      `agent/tests/ticket_agent/unit/test_budget_stop_handler.py`
      (しきい値100%のSNSメッセージでのみ`events.disable_rule()`を呼び、80%通知では
      何もしないことを検証、FR-005/006)

### Implementation for User Story 1

- [ ] T016 [US1] `agent/src/ticket_agent/decision.py` に、`bedrock-runtime`クライアントの
      `converse()`(Amazon Nova Micro、クロスリージョン推論プロファイル指定、research.md §2)を
      呼び出し、チケットごとに `NO_OP` / `START_PROGRESS` のいずれかを判断するロジックを
      実装する(この時点では `COMPLETE` 判断は行わない。US3で拡張)
- [ ] T017 [US1] `agent/src/ticket_agent/decision_handler.py` にEventBridgeトリガーの
      Lambdaエントリポイントを実装する: `ticket_client.list_tickets()` で対象チケットを
      取得 → 呼び出し回数カウンタ(環境変数 `EXECUTION_LIMIT`)を見ながら `decision.py` を
      呼び出し → `START_PROGRESS` は `ticket_client.update_status(..., "IN_PROGRESS")` を
      実行 → 各操作を `audit_log.log_operation()` で記録 → 上限到達時は
      `EXECUTION_LIMIT_REACHED` を記録して正常終了する(T009, T010, T016に依存、
      T013をパスさせる)
- [ ] T018 [US1] `agent/src/ticket_agent/budget_stop_handler.py` にSNS(AWS Budgets通知)
      トリガーのLambdaを実装する: しきい値100%のメッセージのみ処理し `events.disable_rule()`
      で `decision` Lambdaのスケジュールルールを無効化、`audit_log.log_operation(actor=
      "budget_stop", action="BUDGET_STOP", ...)` を記録する(research.md §5、T010に依存、
      T015をパスさせる)
- [ ] T019 [US1] Terraform: `agent/iam.tf` に `decision` 実行ロールを定義する。許可:
      `execute-api:Invoke`(`${data.terraform_remote_state.core.outputs.
      ticket_api_execution_arn}/v1/GET/tickets`, `.../v1/GET/tickets/*`,
      `.../v1/PATCH/tickets/*/status`)、`bedrock:Converse`(推論プロファイルARN +
      基盤モデルARN(リージョンワイルドカード)の2 Resource、data-model.md「decisionロールの
      Bedrock関連IAMポリシー」)、CloudWatch Logs書き込み。`dynamodb:*` / `states:*` は
      含めない(T006, T007に依存、T014をパスさせる)
- [ ] T020 [US1] Terraform: `agent/iam.tf` に `budget_stop` 実行ロールを定義する。許可:
      `events:DisableRule`(対象EventBridgeルールARNのみ)、CloudWatch Logs書き込み
      (T006に依存)
- [ ] T021 [US1] Terraform: `agent/lambda.tf` に `decision` Lambda(runtime `python3.13`、
      handler `ticket_agent.decision_handler.lambda_handler`、
      `timeout = var.decision_timeout_seconds`、環境変数 `EXECUTION_LIMIT =
      var.execution_limit`, `TICKET_API_BASE_URL`, `BEDROCK_MODEL_ID`(推論プロファイルID))と
      `budget_stop` Lambda(handler `ticket_agent.budget_stop_handler.lambda_handler`)を
      定義する。`archive_file` で `agent/src` をZIP化する(T017, T018, T019, T020に依存)
- [ ] T022 [US1] Terraform: `agent/eventbridge.tf` に `var.eventbridge_schedule`
      (既定`rate(5 minutes)`)のスケジュールルールと `decision` Lambdaをターゲットに設定し、
      `aws_lambda_permission` を付与する(research.md §9、T021, T007に依存)
- [ ] T023 [US1] Terraform: `agent/sns.tf` に `agent-budget-alert` トピック、運用者メール
      サブスクリプション(`var.notification_email`)、`budget_stop` Lambdaへの
      サブスクリプション・Lambda呼び出し許可を定義する(T021, T007に依存)
- [ ] T024 [US1] Terraform: `agent/budgets.tf` に `aws_budgets_budget`(`cost_filter`で
      タグ`Phase=agent`に限定、80%/100%の`ACTUAL`通知を`agent-budget-alert`へ送信)を
      定義する(contracts/budget-circuit-breaker.md、T023, T007に依存)
- [ ] T025 [US1] Terraform: `agent/outputs.tf` に `decision` Lambda名・EventBridgeルール名の
      出力を定義する(手動復旧・動作確認用、T021, T022に依存)

**Checkpoint**: `agent/`を初回`terraform apply`した時点で、権限制御・実行回数上限・
タイムアウト・コスト超過時自動停止のすべてが同時に有効(FR-007、quickstart.md 手順3)。
この時点でMVPとして単独にデプロイ・検証可能

---

## Phase 4: User Story 2 - エージェントの操作履歴を後から追跡する(Priority: P2)

**Goal**: エージェントが実際に行った・拒否された操作を、任意の期間を指定して後から確認できる

**Independent Test**: エージェントに一定期間チケットを処理させた後、CloudWatch Logs Insightsで
期間指定クエリを実行し、その期間内の操作(拒否された試み含む)が漏れなく確認できることを
検証する(spec.md US2 Acceptance Scenarios)

### Tests for User Story 2

- [ ] T026 [P] [US2] 単体テスト: 許可範囲外呼び出しの記録
      `agent/tests/ticket_agent/unit/test_decision_handler_audit.py`
      (`ticket_client` が `UnauthorizedTicketApiCallError` を送出した場合に
      `decision_handler` が処理を継続しつつ `audit_log.log_operation(result="rejected",
      action="UNAUTHORIZED_ATTEMPT")` を呼ぶことを検証、FR-009)
- [ ] T027 [P] [US2] 単体テスト: CloudWatch Logs Insightsクエリ文字列
      `agent/tests/ticket_agent/unit/test_log_insights_query.py`
      (T030で定義するクエリ文字列が `timestamp, actor, ticket_id, action, result` を
      フィールドとして含み、時系列ソートを行う形式であることを検証、FR-010)

### Implementation for User Story 2

- [ ] T028 [US2] `agent/src/ticket_agent/decision_handler.py`(T017)に、
      `UnauthorizedTicketApiCallError` 発生時の例外ハンドリング(記録して処理継続)を
      追加する(T026をパスさせる)
- [ ] T029 [P] [US2] Terraform: `agent/cloudwatch.tf` に `decision` / `budget_stop` Lambdaの
      ロググループ(`aws_cloudwatch_log_group`、`retention_in_days =
      var.log_retention_days`)を明示的に定義する(既定の無期限保持を避ける、T021に依存)
- [ ] T030 [US2] Terraform: `agent/cloudwatch.tf` に `aws_cloudwatch_query_definition`
      (名前 `agent-operation-history`、フィールド `timestamp, actor, ticket_id, action,
      result, detail` を時系列で表示するInsightsクエリ)を定義し、FR-010(任意期間参照の
      手段の提供)を満たす(T029に依存、T027をパスさせる)

**Checkpoint**: US1が稼働中に行った操作(拒否含む)が、quickstart.md 手順4
(`aws logs start-query`)で期間指定により漏れなく確認できる

---

## Phase 5: User Story 3 - 重大な操作は人間の承認を必須にする(Priority: P3)

**Goal**: チケットの完了などの重大操作は、Step Functionsのwait-for-task-tokenパターンによる
人間承認を経てのみ実行され、通知リンクの単純アクセス(プリフェッチ含む)だけでは実行されない

**Independent Test**: 完了が必要な状況を作り、(a) 通知リンクへの初回アクセスだけでは
何も実行されないこと、(b) 確認ページ上の明示的な操作を経て初めて実行されること、
(c) 却下・タイムアウト時にチケットが安全な状態に保たれることを確認する
(spec.md US3 Acceptance Scenarios)

### Tests for User Story 3

- [ ] T031 [P] [US3] 単体テスト: `apply_decision_handler`
      `agent/tests/ticket_agent/unit/test_apply_decision_handler.py`
      (`ticket_client.update_status(ticket_id, "DONE")` を呼び出すことを検証、FR-013)
- [ ] T032 [P] [US3] 単体テスト: `apply_rejection_handler`
      `agent/tests/ticket_agent/unit/test_apply_rejection_handler.py`
      (`ticket_client.update_status(ticket_id, "OPEN")` を呼び出すことを検証、FR-014)
- [ ] T033 [P] [US3] 統合テスト(moto DynamoDB): `approval_links` の条件付き書き込み
      `agent/tests/ticket_agent/integration/test_approval_links.py`
      (`mark_consumed()` が `attribute_not_exists(task_token)` 条件により初回のみ
      書き込まれること、`mark_confirmed()` が `attribute_not_exists(confirmed_at)` 条件により
      一度しか成功しないことを検証、research.md §11)
- [ ] T034 [P] [US3] 単体テスト: `approval_callback_handler` Step 1
      `agent/tests/ticket_agent/unit/test_approval_callback_step1.py`
      (`GET /approvals` 呼び出しで `approval_links.mark_consumed()` のみが呼ばれ、
      `states:SendTaskSuccess` / `SendTaskFailure` が一切呼ばれないことを検証、FR-016)
- [ ] T035 [P] [US3] 単体テスト: `approval_callback_handler` Step 2
      `agent/tests/ticket_agent/unit/test_approval_callback_step2.py`
      (`GET /approvals/confirm` 呼び出しで、未確認時のみ `SendTaskSuccess` /
      `SendTaskFailure` が呼ばれ、既に確認済みの場合は呼ばれず「既に処理済みです」を
      返すことを検証、FR-013/FR-016)
- [ ] T036 [P] [US3] 統合テスト: `apply_decision` / `apply_rejection` / `approval_callback`
      ロールのIAM境界 `agent/tests/ticket_agent/integration/test_iam_boundaries_approval.py`
      (`apply_decision`・`apply_rejection`ロールが`states:*`を持たないこと、
      `approval_callback`ロールが`execute-api:Invoke`を一切持たないことを検証)

### Implementation for User Story 3

- [ ] T037 [P] [US3] `agent/src/ticket_agent/decision.py`(T016)を拡張し、チケットが
      完了条件を満たすとBedrockが判断した場合に `COMPLETE` を返すロジックを追加する
- [ ] T038 [P] [US3] `agent/src/ticket_agent/apply_decision_handler.py` を実装する:
      Step Functionsから呼ばれ、`ticket_client.update_status(ticket_id, "DONE")` を実行し
      `audit_log` に `APPROVE` / `TRANSITION_DONE` を記録する(T009, T010に依存、
      T031をパスさせる)
- [ ] T039 [P] [US3] `agent/src/ticket_agent/apply_rejection_handler.py` を実装する:
      `ticket_client.update_status(ticket_id, "OPEN")` を実行し `audit_log` に `REJECT` /
      `TRANSITION_OPEN` を記録する(T009, T010に依存、T032をパスさせる)
- [ ] T040 [P] [US3] `agent/src/ticket_agent/approval_links.py` を実装する:
      `mark_consumed(task_token, decision)`(`attribute_not_exists(task_token)`条件付き
      `PutItem`、既存時はFalseを返す)、`mark_confirmed(task_token)`
      (`attribute_not_exists(confirmed_at)`条件付き`UpdateItem`、失敗時はFalseを返す)、
      `get(task_token)` を実装する(data-model.md「承認リンク消費状態」、
      T033をパスさせる)
- [ ] T041 [US3] `agent/src/ticket_agent/approval_callback_handler.py` に Step 1
      (`GET /approvals`)を実装する: `approval_links.mark_consumed()` を呼び、
      戻り値やレコードの `confirmed_at` の状態に応じて確認ページ・完了済みページ(HTML)を
      返す。`states:SendTaskSuccess` / `SendTaskFailure` は呼ばない
      (contracts/approval-flow.md Step 1、T040に依存、T034をパスさせる)
- [ ] T042 [US3] 同ファイルに Step 2(`GET /approvals/confirm`)を実装する:
      `approval_links.mark_confirmed()` が成功した場合のみ `decision=approve` なら
      `states:SendTaskSuccess`、`decision=reject` なら `states:SendTaskFailure(error=
      "Rejected")` を呼ぶ。失敗(既に確認済み)の場合は「既に処理済みです」ページを返す
      (contracts/approval-flow.md Step 2、T041に依存、T035をパスさせる)
- [ ] T043 [US3] Terraform: `agent/dynamodb.tf` に `agent-approval-links` テーブル
      (オンデマンドモード、`PK = task_token`(文字列)、`ttl` 属性でDynamoDB TTLを有効化)を
      定義する(data-model.md「承認リンク消費状態」)
- [ ] T044 [P] [US3] Terraform: `agent/sns.tf` に `agent-approval-request` トピックと
      運用者メール(またはSlack連携用)サブスクリプションを追加する
- [ ] T045 [US3] Terraform: `agent/step_functions.tf` にStandard型の承認ステートマシンを
      定義する: `RequestApproval`(`arn:aws:states:::sns:publish.waitForTaskToken`統合、
      `agent-approval-request`トピックへ `$$.Task.Token` を埋め込んだ承認/却下URLを
      `States.Format`で構築して発行、`TimeoutSeconds = var.approval_timeout_seconds`)→
      `Catch`(`States.Timeout`)で`NotifyTimeout`(`Pass`ステート、チケットへは書き込まない)へ、
      成功時出力`decision=approve`で`ApplyDecision`(Lambda `apply_decision`呼び出し)へ、
      `Catch`(`ErrorEquals: ["Rejected"]`)で`ApplyRejection`(Lambda `apply_rejection`
      呼び出し)へ分岐する(research.md §6、data-model.md 状態モデル、T038, T039, T044に依存)。
      ステートマシン用IAMロール(`sns:Publish`・対象Lambda2つへの`lambda:InvokeFunction`)と、
      `logging_configuration`(`level = "ALL"`、専用CloudWatchロググループ、
      タイムアウト到達を含む実行履歴の追跡用)もあわせて定義する
- [ ] T046 [US3] Terraform: `agent/api_gateway.tf` に承認コールバック用REST API
      (`GET /approvals`, `GET /approvals/confirm`、いずれも`authorization = "NONE"`、
      Lambdaプロキシ統合、デプロイ・ステージ)を定義する(contracts/approval-flow.md、
      T041, T042に依存)
- [ ] T047 [US3] Terraform: `agent/iam.tf` に `apply_decision` ロール(`execute-api:Invoke`は
      `.../v1/PATCH/tickets/*/status`のみ、`states:*`は含まない)、`apply_rejection` ロール
      (同様)、`approval_callback` ロール(`states:SendTaskSuccess`/`SendTaskFailure`を
      対象ステートマシンARNのみ、`dynamodb:GetItem`/`PutItem`/`UpdateItem`を
      `agent-approval-links`テーブルのみ、`execute-api:Invoke`は一切持たない)を定義する
      (T043, T045に依存、T036をパスさせる)
- [ ] T048 [US3] Terraform: `agent/iam.tf` の `decision` ロール(T019)に
      `states:StartExecution`(承認ステートマシンARNのみ)を追加し、`agent/lambda.tf` の
      `decision` Lambda(T021)に環境変数 `APPROVAL_STATE_MACHINE_ARN` を追加する
      (T045に依存)
- [ ] T049 [US3] `agent/src/ticket_agent/decision_handler.py`(T017)を拡張し、
      `COMPLETE` 判断のチケットについては `ticket_client.update_status` を直接呼ばず、
      `states.start_execution()`(環境変数 `APPROVAL_STATE_MACHINE_ARN` を使用)で
      承認ステートマシンを起動する処理を追加する(FR-011/012、T037, T048に依存)
- [ ] T050 [US3] Terraform: `agent/lambda.tf` に `apply_decision` / `apply_rejection` /
      `approval_callback` の3Lambdaを追加する(T038, T039, T041/T042, T047に依存)
- [ ] T051 [US3] Terraform: `agent/outputs.tf` に承認コールバックAPIのベースURLの出力を
      追加する(T045のSNSメッセージテンプレートが参照する、T046に依存)
- [ ] T052 [US3] Terraform: `agent/cloudwatch.tf` に `apply_decision` / `apply_rejection` /
      `approval_callback` Lambdaのロググループ(`retention_in_days = var.log_retention_days`)を
      追加する(T029と同様の方針、T050に依存)

**Checkpoint**: 重大操作(完了)がStep Functionsのwait-for-task-token + 2段階確認を経てのみ
実行され、通知リンクへの単純アクセスだけでは何も実行されないこと、却下・タイムアウト時に
チケットが安全な状態に保たれることが確認できる(quickstart.md 手順5)

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 全ストーリーに関わる仕上げ作業

- [ ] T053 [P] `agent/` で `pytest -v` を実行し、全ユーザーストーリーの単体・統合テストが
      成功することを確認する
- [ ] T054 `specs/001-ticket-management/quickstart.md` のcurl手順を、`core/`の`AWS_IAM`化
      (T004)後も動作するよう更新する(contracts/ticket-api-access-control.md「既存
      ドキュメントへの影響」。例: `awscurl`利用への切り替え、または
      `aws apigateway test-invoke-method` を使った代替手順の追記)
- [ ] T055 [P] `core/`・`agent/`双方で `terraform fmt -check` / `terraform validate` を
      実行し、constitution原則II(IaC統一)・原則IV(タグ付け必須化)からの逸脱がないことを
      確認する
- [ ] T056 quickstart.md の手順1〜6をデプロイ済み環境に対して実行し、SC-001〜SC-006を
      すべて確認する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **Foundational (Phase 2)**: Setup完了に依存。全ユーザーストーリーをブロックする。
  特にT004(`core/`のAWS_IAM化)は`core/`側の`terraform apply`が完了して初めてT006以降が
  意味を持つ
- **User Stories (Phase 3-5)**: すべてFoundational完了に依存
  - US1(P1)は他ストーリーへの依存なし。単独でMVPとしてデプロイ可能
  - US2(P2)はUS1で作成した`decision_handler.py`/`budget_stop_handler.py`が生成するログを
    前提とする(監査対象がなければ検証できないため)
  - US3(P3)はUS1の`decision`ロール・Lambda(T019, T021)を拡張する形で承認起動処理を
    追加するため、US1完了後の着手を推奨
- **Polish (Phase 6)**: 実装したいユーザーストーリーすべての完了に依存

### User Story Dependencies

- **US1(P1)**: Foundational完了後、他ストーリーへの依存なし
- **US2(P2)**: US1の`decision_handler.py`(T017)・`budget_stop_handler.py`(T018)・
  Lambda(T021)の存在を前提とする(ログの発生源が必要なため)
- **US3(P3)**: US1の`decision.py`(T016)・`decision_handler.py`(T017)・`decision`ロール
  (T019)・Lambda(T021)を拡張する。US2への直接依存はないが、US3実装後もUS2の
  ロググループ・クエリ定義(T029, T030)は`apply_decision`等の新規Lambdaにも同様の方針
  (T052)で適用する

### Within Each User Story

- テストを先に書き、実装前に失敗することを確認する
- アプリケーションロジック(Python)→ IAMロール → Lambda → トリガー/連携リソース の順で
  実装する
- 各ストーリー完了後、次の優先度のストーリーに進む

### Parallel Opportunities

- Setup: T002, T003は並列実行可能
- Foundational: T004, T005は並列実行可能。T007, T008は並列実行可能。T011, T012は並列実行可能
- US1: テストT013, T014, T015は並列実行可能
- US2: テストT026, T027は並列実行可能。実装のT029はT028と異なるファイルのため並列実行可能
- US3: テストT031〜T036は並列実行可能。実装のT037, T038, T039, T040は異なるファイルのため
  並列実行可能。Terraformの`agent/iam.tf`(T047, T048)・`agent/lambda.tf`(T021, T050)・
  `agent/cloudwatch.tf`(T029, T030, T052)はそれぞれ同一ファイルへの追記のため、
  当該ファイル内のタスクは並列実行不可(順次実行する)

---

## Parallel Example: User Story 1

```bash
# User Story 1のテストを並列で実行:
Task: "単体テスト: 実行回数上限の判定 agent/tests/ticket_agent/unit/test_decision_handler.py"
Task: "統合テスト: decisionロールのIAM境界 agent/tests/ticket_agent/integration/test_iam_boundaries_decision.py"
Task: "単体テスト: budget_stop_handler agent/tests/ticket_agent/unit/test_budget_stop_handler.py"
```

---

## Implementation Strategy

### MVP First(User Story 1 のみ)

1. Phase 1: Setup を完了する
2. Phase 2: Foundational を完了する(CRITICAL — `core/`のAWS_IAM化を含む。これが無いと
   エージェント側のIAM権限制御が技術的に無意味になる)
3. Phase 3: User Story 1(権限制御+暴走防止)を完了する
4. **STOP and VALIDATE**: quickstart.md 手順3(3.1〜3.4)を実行し、許可範囲外操作の拒否・
   実行回数上限・タイムアウト・コスト超過時自動停止のすべてが初回リリース時点から有効で
   あることを確認する
5. この時点で「無防備な状態を経ずに安全に稼働する」というPhase 2の中核方針
   (docs/proposal.md 4.3節)が成立する。US2〜US3は監査・承認という追加の安全対策として
   順次積み上げる

### Incremental Delivery

1. Setup + Foundational → 基盤完成(`core/`のAWS_IAM化・IAM/監査/Ticket APIクライアントの
   共通部品まで含む)
2. US1 → 独立検証 → 権限制御・暴走防止を備えた状態でエージェントが稼働(MVP!)
3. US2 → 独立検証 → 操作履歴を期間指定で追跡可能に
4. US3 → 独立検証 → 重大操作が2段階確認付きの人間承認を経てのみ実行されるように

---

## Notes

- [P] タスク = 異なるファイル、依存関係なし
- [Story] ラベルはトレーサビリティのため、対応するユーザーストーリーに紐づける
- 各ユーザーストーリーは独立して完了・検証可能であることを意図している
- 実装前にテストが失敗することを確認する
- タスクごと、または論理的なまとまりごとにコミットする(日本語で簡潔に、
  CLAUDE.mdのコミットメッセージ規約に従う)
- 各チェックポイントでストーリー単位の独立動作確認を行ってから次に進む
- 避けるべきこと: 曖昧なタスク、同一ファイルへの並列衝突、ストーリー間の独立性を壊す
  クロスストーリー依存
- `decision`ロール(T019)・Lambda(T021)はUS1完了時点では`GET`/`PATCH(IN_PROGRESS)`と
  Bedrock呼び出ししか行わない。US3(T048, T049)で`states:StartExecution`権限と
  完了判断ロジックを追加するまで、完了が必要なチケットは処理されずに残る
  (安全側に倒れる設計であり、US1単独デプロイ時の制約として許容する)
