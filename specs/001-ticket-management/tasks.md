---
description: "Task list template for feature implementation"
---

# Tasks: チケット管理基幹システム

**Input**: Design documents from `/specs/001-ticket-management/`

**Prerequisites**: [plan.md](./plan.md)(必須)、[spec.md](./spec.md)(必須・ユーザーストーリー)、
[research.md](./research.md)、[data-model.md](./data-model.md)、[contracts/api.md](./contracts/api.md)、
[quickstart.md](./quickstart.md)

**Tests**: 本フィーチャーはspec.mdでテストを明示要求していないが、plan.mdのTechnical Context /
research.md 7節で「pytest + moto によるLambdaロジックの単体・統合テスト」が設計方針として
明記されており、quickstart.mdの手順1も前提としているため、各ユーザーストーリーにテストタスクを
含める。特にUS2は差し戻された「同時実行時の楽観的ロック(ConditionExpression)」の回帰防止テストを含む。

**Organization**: タスクはユーザーストーリー(spec.mdのP1〜P3)ごとにグループ化し、各ストーリーを
独立して実装・検証できるようにする。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(異なるファイル、未完了タスクへの依存なし)
- **[Story]**: 対象ユーザーストーリー(US1〜US5、spec.mdの番号に対応)
- 各タスクの説明には正確なファイルパスを含める

## Path Conventions

plan.mdの Project Structure に従い、Terraform・Lambdaコードはすべて `core/` 配下:
- Terraform: `core/*.tf`
- Lambdaソース: `core/src/ticket_api/`
- テスト: `core/tests/ticket_api/unit/`, `core/tests/ticket_api/integration/`

---

## Phase 1: Setup(共有基盤の準備)

**Purpose**: プロジェクトの初期構造・開発依存関係の整備

- [X] T001 `core/src/ticket_api/`、`core/tests/ticket_api/unit/`、`core/tests/ticket_api/integration/`
      ディレクトリを作成する(各ディレクトリに空の `__init__.py` を配置し、pytestのテスト
      検出・パッケージインポートが機能するようにする)
- [X] T002 [P] `core/tests/requirements-dev.txt` を作成し、開発依存(`pytest`, `moto`, `boto3`)を
      記載する(Lambdaデプロイパッケージには含めない。research.md 7節参照)
- [X] T003 [P] `core/pyproject.toml` に `ruff` のlint/format設定(対象: `core/src/ticket_api`,
      `core/tests/ticket_api`)を追加する

---

## Phase 2: Foundational(全ストーリー共通のブロッキング前提作業)

**Purpose**: いずれのユーザーストーリーの実装にも先立って完了していなければならない共通基盤

**⚠️ CRITICAL**: このフェーズが完了するまで、どのユーザーストーリーの実装にも着手できない

- [X] T004 [P] `core/src/ticket_api/errors.py` に `ValidationError` / `NotFoundError` /
      `InvalidTransitionError` の3つのドメイン例外クラスを定義する(contracts/api.mdの
      `error.code`: `VALIDATION_ERROR` / `NOT_FOUND` / `INVALID_TRANSITION` に対応)
- [X] T005 [P] `core/src/ticket_api/models.py` に `Ticket` / `HistoryEntry` のデータクラスと、
      DynamoDBアイテム⇔dataclass変換関数(`to_item()` / `from_item()`)を定義する
      (data-model.md のエンティティ定義に対応)
- [X] T006 `core/src/ticket_api/repository.py` にDynamoDBクライアントの初期化処理(`boto3.resource`、
      環境変数 `TABLE_NAME` からテーブル参照)と共通ヘルパーの雛形を実装する(T005に依存)
- [X] T007 `core/src/ticket_api/handler.py` にLambdaエントリポイント(`lambda_handler`)の雛形を
      実装する: `event["resource"]` + `event["httpMethod"]` に基づくルーティングテーブル
      (未実装ルートは501)、および `errors.py` の例外を contracts/api.md の共通エラー
      レスポンス形式(`{"error": {"code", "message"}}`)に変換する共通処理(T004, T006に依存)
- [X] T008 [P] Terraform: `core/dynamodb.tf` にチケットテーブル(オンデマンドモード、
      `PK`/`SK` 文字列属性)と GSI `StatusIndex`(`GSI1PK`/`GSI1SK`)を定義する
      (data-model.md の物理データモデルに対応)
- [X] T009 Terraform: `core/iam.tf` にLambda実行用IAMロール・ポリシーを定義する。
      許可するDynamoDBアクションは以下に限定して明示的に列挙する(`dynamodb:*` のような
      ワイルドカードは使用しない): `dynamodb:GetItem`, `dynamodb:PutItem`,
      `dynamodb:Query`, `dynamodb:Scan`, `dynamodb:TransactWriteItems`。
      リソースはT008のテーブルARN・GSI ARN(`.../index/StatusIndex`)に限定する。
      加えてCloudWatch Logsへの書き込み権限(`logs:CreateLogGroup`,
      `logs:CreateLogStream`, `logs:PutLogEvents`)を付与する。
      `dynamodb:DeleteItem` / `dynamodb:UpdateTable` 等、本フィーチャーで使用しない
      アクションは含めない(Phase 2「①権限制御」の伏線として、今回から必要最小限に
      絞っておく)。constitution原則IVのタグは `provider` の `default_tags` により
      自動付与されるため明示的な `tags` 指定は不要(T008に依存)
- [X] T010 Terraform: `core/lambda.tf` に `archive_file` で `core/src/ticket_api/` をZIP化し、
      Lambda関数(runtime `python3.13`, handler `handler.lambda_handler`, 環境変数
      `TABLE_NAME` にT008のテーブル名)を定義する(T007, T008, T009に依存)
- [X] T011 Terraform: `core/api_gateway.tf` にREST API本体と、共通の親リソース `/tickets` を
      定義する(各ストーリーのメソッドはこのリソース配下に追加していく)(T010に依存)
- [X] T012 Terraform: `core/api_gateway.tf` に `aws_api_gateway_deployment` と
      `aws_api_gateway_stage`(ステージ名は `v1` 等)を定義する。`aws_api_gateway_deployment`
      には `triggers = { redeployment = filemd5("${path.module}/api_gateway.tf") }` と
      `lifecycle { create_before_destroy = true }` を設定し、以降のストーリーで
      `api_gateway.tf` にメソッドを追記するたびに自動的に再デプロイされるようにする
      (これが無いとAPIが一切呼び出せないため、Foundationalフェーズで確実に用意する)
      (T011に依存)
- [X] T013 Terraform: `core/outputs.tf` にAPI GatewayエンドポイントURL(T012のステージの
      `invoke_url`)の出力を定義する(T012に依存)

**Checkpoint**: 基盤が完成。以降、各ユーザーストーリーの実装に着手できる

---

## Phase 3: User Story 1 - チケットを作成する(Priority: P1)🎯 MVP

**Goal**: タイトル・説明・担当者を指定してチケットを作成し、「発行」状態で登録できる

**Independent Test**: `POST /tickets` を呼び出し、一意なIDと `status: "OPEN"` を持つチケットが
生成されることを確認する(spec.md US1 Acceptance Scenarios)

### Tests for User Story 1

- [X] T014 [P] [US1] 単体テスト: 必須項目バリデーション `core/tests/ticket_api/unit/test_models.py`
      (title/assigneeが空文字・未指定の場合に `ValidationError` となることを検証、FR-004)
- [X] T015 [P] [US1] 統合テスト(moto): チケット作成のDynamoDB書き込み
      `core/tests/ticket_api/integration/test_repository_create.py`
      (`create_ticket()` が METADATA レコード + 初回HISTORYレコード
      (`from_status: null, to_status: "OPEN"`)を `TransactWriteItems` で同時書き込みすることを
      検証、FR-002/003/013)

### Implementation for User Story 1

- [X] T016 [US1] `core/src/ticket_api/models.py` に `validate_ticket_input(title, description,
      assignee)` バリデーション関数を実装する(T014をパスさせる)(T005に依存)
- [X] T017 [US1] `core/src/ticket_api/repository.py` に `create_ticket()` を実装する
      (UUID採番、`created_at`/`updated_at` をISO8601で設定、`status` は常に `OPEN` 固定、
      METADATA + 初回HISTORYレコードを `TransactWriteItems` で書き込み)(T006, T016に依存、
      T015をパスさせる)
- [X] T018 [US1] `core/src/ticket_api/handler.py` に `POST /tickets` ハンドラを実装する
      (リクエストボディを `validate_ticket_input` で検証 → `create_ticket` 呼び出し →
      `201` レスポンス、`ValidationError` は `400` に変換)(T007, T017に依存)
- [X] T019 [US1] Terraform: `core/api_gateway.tf` に `/tickets` への `POST` メソッド・
      Lambdaプロキシ統合を追記し、`aws_lambda_permission` を1件作成する
      (`source_arn` はAPI全体をカバーするワイルドカード、例:
      `"${aws_api_gateway_rest_api.this.execution_arn}/*/*/*"`、を指定する。
      この権限はAPI Gateway全体からのLambda呼び出しを許可するため、後続のUS2〜US5で
      メソッドを追加する際に `aws_lambda_permission` を再作成する必要はない)
      (T011, T012, T018に依存)

**Checkpoint**: `POST /tickets` によるチケット作成がAPI経由で動作確認できる
(quickstart.md 手順3.1)

---

## Phase 4: User Story 2 - チケットの状態を遷移させる(Priority: P1)

**Goal**: 発行→対応中→完了、対応中→発行(差し戻し)の遷移のみを許可し、それ以外の遷移は
状態を変更せずエラーとして拒否する

**Independent Test**: 作成済みチケットに対して許可された3遷移を実行し状態が正しく変わること、
および未定義の遷移(例: 完了→発行)がエラーとなり状態が変化しないことを確認する
(spec.md US2 Acceptance Scenarios)

### Tests for User Story 2

- [X] T020 [P] [US2] 単体テスト: 状態遷移ルール
      `core/tests/ticket_api/unit/test_state_machine.py`
      (許可された3遷移(`OPEN→IN_PROGRESS`, `IN_PROGRESS→DONE`, `IN_PROGRESS→OPEN`)が
      成功し、それ以外(`DONE→OPEN` 等)が拒否されることを検証、FR-011/012)
- [X] T021 [P] [US2] 統合テスト(moto): 競合時の `ConditionExpression` 失敗
      `core/tests/ticket_api/integration/test_repository_transition.py`
      (正常遷移が書き込まれること、および書き込み時点の実際の `status` が `GetItem` 時点と
      異なる場合に `ConditionalCheckFailedException` が発生し `InvalidTransitionError` に
      変換されることを検証。TOCTOU対策の回帰防止テスト、spec.md Assumptions /
      data-model.md US2行 参照)

### Implementation for User Story 2

- [X] T022 [US2] `core/src/ticket_api/state_machine.py` に許可された遷移集合
      `{(OPEN, IN_PROGRESS), (IN_PROGRESS, DONE), (IN_PROGRESS, OPEN)}` と判定関数
      `is_valid_transition(from_status, to_status)` を実装する(T020をパスさせる)
- [X] T023 [US2] `core/src/ticket_api/repository.py` に `update_status()` を実装する
      (`GetItem` で現状態取得 → `TransactWriteItems` でMETADATAの `status`/`updated_at` 更新 +
      新規HISTORYレコード追加、`ConditionExpression` で書き込み時点の `status` が `GetItem`
      時点の値と一致することを確認。条件不一致は `InvalidTransitionError` として扱う)
      (T006, T022に依存、T021をパスさせる)
- [X] T024 [US2] `core/src/ticket_api/handler.py` に `PATCH /tickets/{ticket_id}/status`
      ハンドラを実装する(`state_machine.is_valid_transition` による事前チェック →
      `update_status` 呼び出し → `200`、`NotFoundError`は`404`、`InvalidTransitionError`は
      `409`、不正な `status` 値は `400` に変換)(T007, T022, T023に依存)
- [X] T025 [US2] Terraform: `core/api_gateway.tf` に `/tickets/{ticket_id}/status` への
      `PATCH` メソッド・Lambdaプロキシ統合を追記する(T019で作成済みの
      `aws_lambda_permission` がAPI全体をカバーしているため、追加のLambda権限作成は不要)
      (T011, T012, T024に依存)

**Checkpoint**: US1 + US2 で、チケット作成〜正しい状態遷移〜未定義遷移の拒否がAPI経由で
確認できる(quickstart.md 手順3.4/3.5)。ここまでで実用最小限のチケット管理サイクルが成立する

---

## Phase 5: User Story 3 - チケット一覧を取得する(Priority: P2)

**Goal**: 登録済みチケットの一覧を取得し、状態で絞り込むことができる

**Independent Test**: 異なる状態のチケットを複数作成した後、フィルタなし/ありで一覧取得APIを
呼び出し、期待通りの件数・内容が返ることを確認する(spec.md US3 Acceptance Scenarios)

### Tests for User Story 3

- [X] T026 [P] [US3] 統合テスト(moto): 一覧取得(フィルタなし/状態フィルタ/不正フィルタ/0件)
      `core/tests/ticket_api/integration/test_repository_list.py`(FR-005/006/007)

### Implementation for User Story 3

- [X] T027 [US3] `core/src/ticket_api/repository.py` に `list_tickets(status=None)` を実装する
      (フィルタなし: `Scan` + `FilterExpression begins_with(SK, "METADATA")`、フィルタあり:
      `StatusIndex` への `Query`)(T006に依存、T026をパスさせる)
- [X] T028 [US3] `core/src/ticket_api/handler.py` に `GET /tickets` ハンドラを実装する
      (クエリパラメータ `status` を検証(`OPEN`/`IN_PROGRESS`/`DONE`以外は`400`) →
      `list_tickets` 呼び出し → `200`)(T007, T027に依存)
- [X] T029 [US3] Terraform: `core/api_gateway.tf` に `/tickets` への `GET` メソッド・
      Lambdaプロキシ統合を追記する(T019で作成済みの `aws_lambda_permission` を再利用する
      ため追加のLambda権限作成は不要)(T011, T012, T028に依存)

**Checkpoint**: 一覧取得(フィルタ有無)がAPI経由で確認できる(quickstart.md 手順3.3)

---

## Phase 6: User Story 4 - チケット単体を取得する(Priority: P2)

**Goal**: IDを指定して特定のチケットの詳細を取得できる

**Independent Test**: 作成済みチケットのIDを指定して単体取得APIを呼び出し、作成時の内容と
現在の状態が正しく返ることを確認する(spec.md US4 Acceptance Scenarios)

### Tests for User Story 4

- [X] T030 [P] [US4] 統合テスト(moto): 単体取得(存在するID/存在しないID)
      `core/tests/ticket_api/integration/test_repository_get.py`(FR-008/009)

### Implementation for User Story 4

- [X] T031 [US4] `core/src/ticket_api/repository.py` に `get_ticket(ticket_id)` を実装する
      (`GetItem`、存在しない場合は `NotFoundError`)(T006に依存、T030をパスさせる)
- [X] T032 [US4] `core/src/ticket_api/handler.py` に `GET /tickets/{ticket_id}` ハンドラを
      実装する(T007, T031に依存)
- [X] T033 [US4] Terraform: `core/api_gateway.tf` に `/tickets/{ticket_id}` への `GET` メソッド・
      Lambdaプロキシ統合を追記する(T019で作成済みの `aws_lambda_permission` を再利用する
      ため追加のLambda権限作成は不要)(T011, T012, T032に依存)

**Checkpoint**: 単体取得がAPI経由で確認できる(quickstart.md 手順3.2/3.7)

---

## Phase 7: User Story 5 - 状態変更履歴を追跡する(Priority: P3)

**Goal**: チケットに対する全ての状態変更を発生順に履歴として取得できる

**Independent Test**: 複数回状態変更されたチケットの履歴を取得し、変更前後の状態・日時が
発生順に正しく記録されていること、拒否された遷移が含まれないことを確認する
(spec.md US5 Acceptance Scenarios)

### Tests for User Story 5

- [X] T034 [P] [US5] 統合テスト(moto): 履歴取得(発生順ソート・`from_status`の正確性・
      拒否された遷移が含まれないこと)`core/tests/ticket_api/integration/test_repository_history.py`
      (FR-013/014/015)

### Implementation for User Story 5

- [X] T035 [US5] `core/src/ticket_api/repository.py` に `get_history(ticket_id)` を実装する
      (`Query`: `PK=TICKET#<id>`, `SK begins_with "HISTORY#"`、`changed_at` 昇順ソート。
      チケット自体が存在しない場合は `get_ticket` 経由で `NotFoundError`)
      (T006, T031に依存、T034をパスさせる)
- [X] T036 [US5] `core/src/ticket_api/handler.py` に `GET /tickets/{ticket_id}/history`
      ハンドラを実装する(T007, T035に依存)
- [X] T037 [US5] Terraform: `core/api_gateway.tf` に `/tickets/{ticket_id}/history` への
      `GET` メソッド・Lambdaプロキシ統合を追記する(T019で作成済みの `aws_lambda_permission`
      を再利用するため追加のLambda権限作成は不要)(T011, T012, T036に依存)

**Checkpoint**: 全ユーザーストーリーがAPI経由で独立して確認できる(quickstart.md 手順3.6)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 全ストーリーに関わる仕上げ作業

- [X] T038 [P] `core/` で `pytest -v` を実行し、全ユーザーストーリーの単体・統合テストが
      成功することを確認する
- [X] T039 quickstart.md の手順3(curlによるE2E検証)をデプロイ済みAPI Gatewayエンドポイントに
      対して実行し、SC-001〜SC-005をすべて確認する

      > **学び(本番デプロイで判明した不備)**: 実行中、状態変更(`PATCH /tickets/{id}/status`)で
      > `AccessDeniedException` が発生した。原因は `core/iam.tf` のLambda実行ロールに
      > `dynamodb:UpdateItem` が不足していたこと。`update_status` は `TransactWriteItems` 内で
      > `Update` 操作を行うが、`moto` によるユニット/統合テスト(T038)はIAM権限を評価しない
      > ため、テストは全て成功していたにもかかわらず本番デプロイまでこの不備に気づけなかった。
      > `core/iam.tf` に `dynamodb:UpdateItem` を追加し `terraform apply` で再適用、実APIで
      > 再検証して解消済み(T009の最小権限列挙時に `TransactWriteItems` 内部で使う個々の
      > アクション(Update/Put/Delete等)も洗い出す必要がある、という教訓)。
- [X] T040 [P] `core/` で `terraform fmt -check` / `terraform validate` を実行し、
      constitution原則II(IaC統一)・原則IV(タグ付け必須化)からの逸脱がないことを確認する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **Foundational (Phase 2)**: Setup完了に依存。全ユーザーストーリーをブロックする
- **User Stories (Phase 3-7)**: すべてFoundational完了に依存
  - US1(P1)・US2(P1)を先に完了させることを推奨(基本サイクルの土台)
  - US3(P2)・US4(P2)はUS1完了後であれば独立して着手可能(参照系のみでUS2に依存しない)
  - US5(P3)はUS4の `get_ticket` を再利用するため、US4完了後の着手を推奨
- **Polish (Phase 8)**: 実装したいユーザーストーリーすべての完了に依存

### User Story Dependencies

- **US1(P1)**: Foundational完了後、他ストーリーへの依存なし。ただし `aws_lambda_permission`
  (T019)はAPI全体をカバーするため、US2〜US5のTerraformタスクはT019の完了を前提とする
- **US2(P1)**: Foundational完了後、他ストーリーへの依存なし(遷移対象のチケットはUS1で作成する
  想定だが、テストはmotoでチケットを直接投入すれば独立して検証可能)
- **US3(P2)**: Foundational完了後、他ストーリーへの依存なし
- **US4(P2)**: Foundational完了後、他ストーリーへの依存なし
- **US5(P3)**: Foundational完了後に着手可能。実装上 `get_ticket`(US4, T031)を再利用するため、
  US4のT031完了後に着手することを推奨

### Within Each User Story

- テストを先に書き、実装前に失敗することを確認する
- モデル/ステートマシン → リポジトリ層 → ハンドラ → Terraform(APIメソッド)の順で実装する
- 各ストーリー完了後、次の優先度のストーリーに進む

### Parallel Opportunities

- Setup: T002, T003は並列実行可能
- Foundational: T004, T005, T008は並列実行可能(異なるファイル、相互依存なし)
- Foundational完了後、チーム体制があればUS1〜US5は並列着手可能。ただしTerraformタスク
  (T019/T025/T029/T033/T037)は `aws_lambda_permission` をT019で一度だけ作成する都合上、
  T019完了後に着手するのが安全
- 各ストーリーのテストタスク(T014/T015, T020/T021, T026, T030, T034)はそれぞれ並列実行可能

---

## Parallel Example: User Story 1

```bash
# User Story 1のテストを並列で実行:
Task: "単体テスト: 必須項目バリデーション core/tests/ticket_api/unit/test_models.py"
Task: "統合テスト(moto): チケット作成 core/tests/ticket_api/integration/test_repository_create.py"
```

---

## Implementation Strategy

### MVP First(User Story 1 + User Story 2)

1. Phase 1: Setup を完了する
2. Phase 2: Foundational を完了する(CRITICAL — 全ストーリーをブロックする。API Gatewayの
   デプロイ/ステージ(T012)も含めて完了させないと、後続のどのストーリーもAPI経由で
   検証できない)
3. Phase 3: User Story 1(チケット作成)を完了する
4. Phase 4: User Story 2(状態遷移)を完了する
5. **STOP and VALIDATE**: quickstart.md 手順3.1〜3.5相当をAPI経由で確認する
   (作成→対応中→差し戻し→対応中→完了→未定義遷移の拒否)
6. この時点で「チケットの発行から完了までのライフサイクル管理」という基幹システムの中核
   価値が成立する。US3〜US5は参照・監査系の追加価値として順次積み上げる

### Incremental Delivery

1. Setup + Foundational → 基盤完成(APIが実際に呼び出し可能な状態まで含む)
2. US1 → 独立検証 → チケット作成が可能に
3. US2 → 独立検証 → 状態遷移サイクルが完成(実用最小限のMVP)
4. US3 → 独立検証 → 一覧俯瞰が可能に
5. US4 → 独立検証 → 個別参照が可能に
6. US5 → 独立検証 → 履歴追跡(監査証跡)が可能に、Phase 1の完了条件(docs/proposal.md 3.5節)を満たす

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
- IAMポリシー(T009)・Lambda権限(T019)はいずれも必要最小限のアクション・スコープに
  絞ってある。Phase 2で権限制御を段階的に強化する際、ここを起点に見直す
