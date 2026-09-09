# Research: チケット管理基幹システム

**Feature**: [spec.md](./spec.md) | **Date**: 2026-09-09

すべての技術選定はユーザーが `/speckit-plan` の入力で明示済み(Lambda(Python) + API Gateway(REST)
+ DynamoDB シングルテーブル + Terraform + プロファイル `sca-aws`)。本ドキュメントは、その枠内で
残る実装判断を整理し、Technical Context の NEEDS CLARIFICATION を解消するためのもの。

## 1. Lambda ランタイム・構成方式

- **Decision**: Python 3.13 ランタイムの単一 Lambda 関数(`ticket-api`)で API Gateway の
  全ルートをプロキシ統合(`ANY /{proxy+}` 相当、実際は各リソース×メソッドを個別に
  Lambda プロキシ統合)して受け、関数内部で `(resource path, HTTPメソッド)` に応じて
  ルーティングする
- **Rationale**: チケットCRUD+状態遷移+履歴取得という限定的なAPI面(5〜6エンドポイント)に対して
  エンドポイントごとにLambdaを分けると、IAMロール・デプロイパッケージ・Terraformリソースが
  5〜6倍に増え、"スピードを優先する" というユーザー方針や、まずシンプルに動かすという
  spec.md の Assumptions と整合しない。単一関数+内部ルーティングなら Terraform リソース数も
  最小限で済み、コスト(Lambda無料枠は関数数でなく実行回数・時間で決まる)にも影響しない
- **Alternatives considered**:
  - エンドポイントごとに個別Lambda関数 → 却下(現時点でメリットがない複雑化。Phase 2で
    エージェント側IAMを絞る際もAPI Gateway/Lambdaの分割は必須ではない)
  - コンテナイメージLambda → 却下(ZIPデプロイで十分な小規模コードに対してオーバースペック)

## 2. API Gateway タイプ

- **Decision**: REST API(ユーザー指定通り)、Lambdaプロキシ統合
- **Rationale**: ユーザーが明示的に REST API を指定。HTTP APIより高機能(リクエストバリデーション等)
  だが、今回はLambda内バリデーションで完結させるため、API Gateway側の機能は最小限の利用に留める
- **Alternatives considered**: HTTP API(より安価・高速だが今回は対象外。ユーザー指定を優先)

## 3. DynamoDB テーブル設計方式

- **Decision**: シングルテーブル、オンデマンドキャパシティモード(PAY_PER_REQUEST)
  - `PK = TICKET#<ticket_id>`, `SK = METADATA` → チケット本体
  - `PK = TICKET#<ticket_id>`, `SK = HISTORY#<ISO8601タイムスタンプ>#<短いUUID接尾辞>` → 履歴レコード
  - GSI `StatusIndex`: `GSI1PK = STATUS#<status>`, `GSI1SK = <created_at>#<ticket_id>`
    (状態フィルタ付き一覧取得を効率的なQueryで実現)
- **Rationale**: docs/proposal.md 3.4節の設計方針をそのまま踏襲。オンデマンドモードは
  プロビジョニング不要でコスト意識ファースト原則(常時課金の回避、無料枠内運用)と合致する。
  履歴SKにタイムスタンプ+UUID接尾辞を付けるのは、同一ミリ秒内に複数回の遷移が発生しても
  SKの一意性・時系列ソート順を保証するため
- **Alternatives considered**:
  - チケットと履歴を別テーブルに分離 → 却下(トランザクション境界が複雑化し、シングル
    テーブル設計を採るというproposal.mdの方針からも外れる)
  - プロビジョニングモード → 却下(常時課金を避けたいコスト意識ファースト原則に反する)

## 4. 「フィルタなし一覧取得」の実現方式

- **Decision**: `SK = METADATA` の項目のみを対象にした `Scan` + `FilterExpression` で実装する
- **Rationale**: 学習用リポジトリであり想定件数は小規模(数百〜数千件オーダー)。この規模では
  Scanのコスト・レイテンシは無視できる範囲に収まる。専用GSI(定数PKで全件Queryを可能にする)を
  追加する案もあるが、書き込み時に余分なGSI書き込みコストが常に発生するため、現時点では
  過剰最適化と判断する
- **Alternatives considered**: 定数PKを持つ全件用GSI(`GSI2PK = "TICKET"`) → 却下(現時点では
  スケールメリットがコストに見合わない。将来件数が増えた場合の拡張として記録のみ残す)

## 5. チケットID・タイムスタンプの形式

- **Decision**: チケットIDは `uuid.uuid4()` (標準ライブラリ)による36文字のUUID文字列。
  タイムスタンプはUTCのISO 8601文字列(`datetime.now(timezone.utc).isoformat()`)
- **Rationale**: 標準ライブラリのみで追加依存が不要(Lambdaデプロイパッケージを最小に保てる)。
  ISO 8601は辞書式ソートと時系列順が一致するため、DynamoDBのSKとしてそのまま利用できる
- **Alternatives considered**: ULID(生成順にソート可能なID) → 却下(追加の外部ライブラリが
  必要になり、標準ライブラリのみで完結させたいという方針に反する。ソート用途はSK側の
  タイムスタンプで別途担保できるため、IDそのものをソート可能にする必要性は薄い)

## 6. 状態遷移バリデーションの実装場所

- **Decision**: Lambda内の純粋関数(`state_machine.py` 相当)として、許可された遷移の
  集合(`{(OPEN, IN_PROGRESS), (IN_PROGRESS, DONE), (IN_PROGRESS, OPEN)}`)に対する
  メンバーシップチェックで実装する。Step Functionsは使用しない
- **Rationale**: ユーザー指示により明示的にStep Functionsを見送り、spec.md Assumptionsとも
  整合。将来Step Functionsで承認フロー等を追加する場合も、この純粋関数はそのままロジックとして
  再利用可能
- **Alternatives considered**: Step Functionsステートマシンでの遷移制御 → 今回は見送り
  (docs/proposal.md 3.3節では将来的な想定サービスとして記載されているが、本フィーチャーでは
  ユーザーが明示的にスコープ外とした)

## 7. テスト方針

- **Decision**: `pytest` + `moto`(DynamoDBのモック)によるLambdaロジックの単体テスト。
  実AWSリソースへは接続しない
- **Rationale**: コスト意識ファースト原則・高速なフィードバックループの両立。実デプロイ済み
  環境に依存しないため、CIやローカルでも安定して実行できる
- **Alternatives considered**: 実DynamoDB(テスト用テーブル)を都度作成 → 却下(常時ではないが
  不要な課金・待ち時間が発生し、学習用リポジトリの開発ループには重すぎる)

## 8. tfstateバックエンド・プロバイダ設定

- **Decision**: 既存の `core/providers.tf` の設定(S3バケット `sca-aws-tfstate`、
  key `core/terraform.tfstate`、profile `sca-aws`、region `ap-northeast-1`、
  `default_tags` で Project/ManagedBy/Phase を自動付与)をそのまま利用する。新規リソースは
  すべて `core/` ディレクトリ配下の新しい `.tf` ファイル(`dynamodb.tf` / `lambda.tf` /
  `api_gateway.tf` / `iam.tf` など)として追加し、既存の `main.tf`(リハビリ用S3バケット)は
  変更しない
- **Rationale**: ユーザー入力の制約と完全に一致。`provider "aws"` の `default_tags` が
  既に Project/ManagedBy/Phase="core" を設定済みのため、新規リソースは明示的な `tags` 指定
  なしでもタグ付けルール(constitution原則IV)を満たす
- **Alternatives considered**: なし(既存設定をそのまま踏襲するのが唯一の妥当な選択)

## 未解決事項

なし。Technical Context の NEEDS CLARIFICATION はすべて上記で解消済み。
