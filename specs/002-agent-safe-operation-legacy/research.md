# Research: チケット管理エージェントの安全運用基盤

**Feature**: [spec.md](./spec.md) | **Date**: 2026-09-14

## 1. Ticket API(Phase 1)の認可方式変更

- **Decision**: `core/api_gateway.tf` の全メソッド(`tickets_post` / `tickets_get` / `ticket_get` /
  `ticket_status_patch` / `ticket_history_get`)の `authorization` を `"NONE"` から `"AWS_IAM"` に
  変更する。あわせて `core/outputs.tf` に `ticket_api_execution_arn`(REST APIの`execution_arn`)を
  追加し、`agent/` 側からIAMポリシーのResource指定に使えるようにする
- **Rationale**: spec.md FR-001/FR-002(エージェントのIAMロールを許可範囲に絞り込み、範囲外の
  操作を拒否する)を技術的に実効あるものにするには、呼び出し先自体がIAMを見ている必要がある。
  `authorization = "NONE"` のままではAPI Gatewayが認証を一切要求しないため、エージェント側の
  IAMロールをどれだけ絞ってもネットワーク層での強制力を持たない。ユーザー承認済みの変更
- **Alternatives considered**:
  - 認可方式は`NONE`のまま、エージェントのアプリケーションコード側だけで呼び出しを制限する →
    却下(ユーザー判断)。コードの規律に依存し、バグや設計ミスがあれば範囲外の呼び出しを
    システムとして防げない
  - API Gatewayにカスタムオーソライザーを追加する → 却下(AWS_IAMで要件を満たせるため、
    追加のLambda・実装コストを持つカスタムオーソライザーは過剰)

## 2. LLM呼び出し方式(エージェントの判断ロジック)

- **Decision**: Amazon Bedrock経由でAmazon Nova Microを呼び出す。呼び出しは`boto3`の
  `bedrock-runtime`クライアント(Converse API、`converse()`)を使う。APIキーの発行・保管は
  不要になる(IAM権限のみで呼び出せるため)
- **Rationale**: 開発者がAnthropic APIキーを保有していないため、直接API呼び出し方式は
  そもそも採用できない。Bedrockであれば追加のAPIキー管理(Parameter Store/Secrets Manager
  への保存・ローテーション)が一切不要になり、IAMロールのみで完結する。Amazon Nova Microは
  Bedrock上の軽量・低コストなモデルであり、docs/proposal.md 5節の「軽量モデルを優先し
  コストを最小化する」方針にも合致する
- **リージョンの制約**: `ap-northeast-1`ではAmazon Nova Microを**そのリージョンのモデルIDで
  直接**呼び出すことはできず、クロスリージョン推論プロファイル(例:
  `apac.amazon.nova-micro-v1:0` のような`apac.`プレフィックス付きプロファイル)経由でのみ
  利用可能である。呼び出し側は`converse()`の`modelId`にモデルID自体ではなく、この
  推論プロファイルのID(またはARN)を指定する。実際にどのAPACリージョンにルーティング
  されるかはAWS側の制御下にあり、呼び出し元では制御・特定しない
- **Alternatives considered**:
  - Anthropic APIの直接HTTPS呼び出し → 却下(開発者がAPIキーを保有していないため実施不可)
  - Amazon Bedrock経由でのAnthropicモデル(Claude)呼び出し → 却下(Nova Microの方がコストが
    低く、docs/proposal.md 5節の「軽量モデル優先」方針により合致する。将来的にClaude系への
    切替が必要になった場合も、Converse APIは複数モデルベンダーで共通のインターフェースを
    提供するため、`modelId`(推論プロファイルID)の変更のみで対応できる)
  - 旧来のBedrock InvokeModel API(モデルごとに異なるリクエスト/レスポンス形式) → 却下。
    Converse APIの方がモデル非依存の共通インターフェースで実装がシンプルになる

> **学び(実機デプロイで判明した訂正)**: 呼び出しAPIはConverse(`converse()`)のままだが、
> これを許可するIAMアクションは`bedrock:Converse`ではなく**`bedrock:InvokeModel`**である
> (ConverseAPIはInvokeModelと同じ認可アクションで権限判定される、AWS仕様)。当初
> `agent/iam.tf`に`bedrock:Converse`を許可アクションとして実装したところ、実際に
> `decision` Lambdaを実行すると`AccessDeniedException`(`bedrock:InvokeModel`が
> 許可されていない旨)が発生し判明した。`agent/iam.tf`の`decision`ロールのポリシーは
> `bedrock:InvokeModel`に修正済み。data-model.mdの記載も参照。

## 3. Lambda関数・IAMロールの責務分離

- **Decision**: 単一の万能Lambdaにはせず、責務ごとに4つのLambda関数・IAMロールに分割する

  | Lambda | トリガー | 許可するTicket API操作 | その他の主な権限 |
  |---|---|---|---|
  | `decision` | EventBridge(定期実行) | `GET /tickets`, `GET /tickets/{id}`, `PATCH /tickets/{id}/status`(コード上は`IN_PROGRESS`への遷移のみ発行) | `bedrock:InvokeModel`(Amazon Nova Microの推論プロファイル・基盤モデルARN、§2参照。Converse APIはこのアクションで認可される)、承認用ステートマシンの`states:StartExecution` |
  | `apply_decision` | Step Functions(承認後のTaskステート) | `PATCH /tickets/{id}/status`(`DONE`への遷移) | なし |
  | `apply_rejection` | Step Functions(却下時のTaskステート) | `PATCH /tickets/{id}/status`(`OPEN`への遷移=差し戻し) | なし |
  | `approval_callback` | API Gateway(承認リンク) | なし(Ticket APIを直接呼ばない) | `states:SendTaskSuccess` / `states:SendTaskFailure`(対象ステートマシンARNのみ) |
  | `budget_stop` | SNS(予算超過通知) | なし | `events:DisableRule`(対象EventBridgeルールのみ) |

- **Rationale**: IAMは「どのAPI・アクションを呼べるか」は細かく制御できるが、「PATCHの
  リクエストボディにどの値を入れるか」までは制御できない。そのため、重大操作(`DONE`への
  遷移)を発行できるコードパスを`apply_decision`という承認後にしか呼ばれないLambdaだけに
  限定することで、設計時点で「エージェントが自動的に完了操作を行う」余地そのものを排除する
  (FR-011)。同様に`approval_callback`にTicket APIへの権限を持たせないことで、承認リンクの
  処理自体がチケットを直接操作できないようにする
- **Alternatives considered**:
  - 単一Lambda・単一ロールで全処理を担う → 却下。重大操作の実行権限が常時稼働する
    `decision`関数にも付与されてしまい、コードのバグがそのままFR-011違反に直結するリスクが
    高い

## 4. 実行回数上限・タイムアウトの実装方式

- **Decision**: `decision` Lambdaのタイムアウトは60秒(Lambda関数設定)。1回の実行あたりの
  Ticket API呼び出し上限は20回とし、Lambda内のカウンタで判定する。上限に達した場合は
  それ以降の呼び出しをスキップし、その旨をCloudWatch Logsに記録して正常終了する。値は
  Terraform変数・Lambda環境変数として外出しし、コードへの埋め込みは避ける
- **Rationale**: 学習用リポジトリの想定データ量(spec.md Assumptions: 運用しながら調整可能な
  小さい値から始める)を踏まえた妥当な初期値。60秒はチケット数件に対しGET→LLM判断→PATCHを
  行っても十分な余裕がある一方、無限ループが発生した場合の被害を小さく抑えられる
- **Alternatives considered**:
  - Step Functions Mapステートで回数制御 → 却下。単純なカウンタで要件を満たせるため、
    ステートマシンの状態遷移(コスト・複雑さ)を不要に増やす必要がない

## 5. コスト超過時の自動停止方式

- **Decision**: AWS Budgets(月次コスト予算)を、`cost_filter`でタグ`Phase=agent`に絞り込んで
  設定する。実際コストがしきい値(例: 80%で警告、100%で停止)に達した際にSNSへ通知し、
  `budget_stop` Lambdaが`decision`Lambdaを起動しているEventBridgeルールを無効化
  (`events:DisableRule`)する。既に実行中のStep Functions実行やLambda呼び出しを強制終了する
  範囲までは含まない(spec.md Assumptions)。しきい値・停止対象は変数化し、運用しながら
  調整可能にする
- **Rationale**: docs/proposal.md 4.4節の想定構成(AWS Budgets + SNS + Lambda)と一致する。
  停止処理は「新規実行の受付を止める」という単純な操作であり、SNS通知を受けたLambdaが
  該当のEventBridgeルールを無効化するだけの構成の方が、AWS Budgets Actionsのネイティブ
  自動対応機能を使うより処理内容をコードで素直に表現でき、学習目的にも合う
- **Alternatives considered**:
  - AWS Budgets Actions(IAMポリシー自動適用等のネイティブ機能) → 却下。今回の「新規実行を
    止める」という単純な用途にはオーバースペック。将来の拡張候補として記録のみ残す

## 6. 承認フロー(Step Functions wait-for-task-token)の設計

- **Decision**: Standard型のステートマシンを1つ定義する

  ```
  [RequestApproval]                  … Task(.waitForTaskToken), TimeoutSeconds=86400(24時間)
    │  実行開始時にSNSへ「承認リンク」「却下リンク」(いずれもタスクトークンを含む)を発行
    │  ※リンクへのアクセスは即座にはSendTaskSuccess/Failureを呼ばない(§11の2段階確認方式)
    │
    ├─ 確認ページで人間が明示的に確認 ──▶ [ApplyDecision]   … PATCH .../status = DONE
    │  (承認コールバックが approve で応答)
    ├─ 確認ページで人間が明示的に確認 ──▶ [ApplyRejection] … PATCH .../status = OPEN(差し戻し)
    │  (承認コールバックが reject で応答)
    └─ TimeoutSeconds超過(States.Timeout)─▶ [NotifyTimeout]  … チケットへは一切書き込まず、
                                                                  タイムアウトした旨のみログ記録
  ```

- **Rationale**: spec.mdのUser Story 3・Edge Casesと1対1で対応する。却下時のみ「差し戻し」
  (Phase 1で定義済みの状態、spec.md Assumptions)へ遷移させ、タイムアウト時は「保留状態を
  維持する(操作を実行しない)」というFR-015の要求どおりチケットの状態を一切変更しない。
  Step Functionsのタスクタイムアウトはネイティブ機能であり、Lambda側で独自にポーリング・
  時間管理を実装するより単純で確実。SendTaskSuccess/Failureの実際の呼び出しは§11の
  2段階確認方式における「確認」操作の時点まで遅延される
- **Alternatives considered**:
  - SQS + 独自ポーリングによる承認待ち実装 → 却下。Step Functionsのwait-for-task-tokenは
    ユーザーが明示的に指定した方式であり、タイムアウト処理もネイティブに備える

## 7. Ticket APIクライアントの実装方式(SigV4署名)

- **Decision**: `botocore.auth.SigV4Auth` + `botocore.awsrequest.AWSRequest`(いずれもboto3の
  依存として標準搭載、追加レイヤー不要)でリクエストに署名し、標準ライブラリ
  `urllib.request`でHTTPS送信する薄いクライアント(`ticket_client.py`)を実装する
- **Rationale**: 001の方針(標準ライブラリ・boto3同梱ライブラリのみで完結させる)を踏襲し、
  `requests`等の外部ライブラリ追加によるLambdaデプロイパッケージの複雑化を避ける
- **Alternatives considered**:
  - `requests` + `requests-aws4auth` → 却下。外部依存が増え、パッケージングが複雑化する

## 8. 操作記録(監査ログ)の実装方式

- **Decision**: 各Lambda(`decision` / `apply_decision` / `apply_rejection` / `approval_callback` /
  `budget_stop`)が、実際に行った、または拒否した操作ごとに構造化JSONログ(1行1JSON。
  `timestamp` / `actor` / `ticket_id` / `action` / `result`(success・rejected・error) /
  `detail`)をCloudWatch Logsへ出力する。CloudTrailは別途有効化し、これらのAWSリソースに
  対する管理操作(Terraform適用等)の監査に役割分担させる。CloudTrailのデータイベント
  (Lambda呼び出し内容そのもの等)の追加設定は行わない
- **Rationale**: Ticket APIはAWSネイティブAPIではない自前のREST APIであるため、CloudTrailは
  「どのチケットに何をしたか」というアプリケーションレベルの操作内容までは記録できない。
  構造化ログをCloudWatch Logsに出力し、CloudWatch Logs Insightsで期間指定クエリを行うことで
  FR-008〜FR-010(操作記録・拒否記録・期間指定の参照)を満たす
- **Alternatives considered**:
  - 監査ログ専用のDynamoDBテーブルを新設 → 却下。CloudWatch Logs Insightsで期間指定の
    参照要件を満たせるため、新たに常時発生しうる書き込みコストを持つテーブルを増やす
    必要がない

## 9. EventBridgeトリガーの実行間隔

- **Decision**: `rate(5 minutes)` のスケジュールルールで`decision` Lambdaを起動する。値は
  Terraform変数化し調整可能にする
- **Rationale**: 学習用途でのチケット滞留時間として許容範囲であり、5分間隔でも月あたり
  約8,640回とLambda無料枠(月100万リクエスト)を大きく下回る
- **Alternatives considered**:
  - チケット作成イベントの検知(EventBridge Pipes等) → 却下。Ticket API自体がイベント
    発行の仕組みを持たないため今回はスコープ外とし、将来拡張の余地として記録する

## 10. tfstate・プロバイダ設定

- **Decision**: `core/`と同じS3バケット(`sca-aws-tfstate`)・プロファイル(`sca-aws`)・
  リージョン(`ap-northeast-1`)を使うが、`key`は`agent/terraform.tfstate`として分離する。
  `default_tags`にProject="serverless-core-agent-aws" / ManagedBy="terraform" /
  Phase="agent"を設定する。Ticket APIのREST API ID・`execution_arn`は
  `terraform_remote_state`データソースで`core/`のtfstateを参照して取得する
- **Rationale**: Phase単位でtfstateを分離し変更影響範囲を明確にしつつ、既存のバックエンド・
  タグ運用(constitution原則IV)を踏襲する
- **Alternatives considered**:
  - `core/`と同一tfstateに同居 → 却下。Phase 1/2の分離という企画・ディレクトリ構成の方針に
    反する

## 11. 承認/却下リンクのプリフェッチ対策(2段階確認方式)

- **Decision**: 承認コールバックAPIを2段階に分ける。
  1. `GET /approvals?token={task_token}&decision={approve|reject}`(通知に記載する
     リンク本体): 副作用として、指定された`task_token`に対する消費レコード(下記
     `agent-approval-links`テーブル)を「初回アクセス時刻」「依頼された決定内容」とともに
     記録する(`attribute_not_exists`条件で1回目のみ書き込む)だけで、
     `states:SendTaskSuccess` / `states:SendTaskFailure` は一切呼ばない。レスポンスは
     「本当に{承認|却下}しますか?」を表示するHTML確認ページで、その中に**このページを
     開かない限りURLを知り得ない**2段階目のリンクを埋め込む
  2. `GET /approvals/confirm?token={task_token}`(確認ページ内のリンクを人間が明示的に
     クリックした場合にのみ到達する): ここで初めて`states:SendTaskSuccess` /
     `states:SendTaskFailure`を呼び、実際にチケットの状態を変更する。同一トークンに
     対して2回目以降のアクセスは「既に処理済みです」を返すだけで何も実行しない
  - 消費レコードの実体化先として、小さなDynamoDBテーブル `agent-approval-links`
    (オンデマンドキャパシティモード、`PK = task_token`、属性
    `decision` / `consumed_at` / `confirmed_at` / `ttl`)を新設する。`ttl`属性で
    DynamoDB TTLを設定し、承認ステートマシンのタイムアウト(24時間)より少し長い
    期間(例: 25時間)で自動削除する
- **Rationale**: メールクライアントのリンクプリフェッチや、セキュリティ製品によるURL
  事前スキャン(Safe Links等)は、通知本文に書かれたURLに対してHTTP GETを自動発行する
  ことがある。1段階方式(リンクを開いた瞬間に承認/却下を実行する)では、この自動アクセス
  だけで人間の意図しない重大操作(チケット完了・差し戻し)が実行されてしまい、FR-013
  (人間が承認した場合にのみ実行)・FR-016(単純なアクセスだけでは実行しない)に違反する。
  2段階方式にすることで、通知メール本文に直接書かれたURL(=プリフェッチされうるURL)への
  アクセスには一切の状態変更を伴わせず、実際の状態変更は「確認ページを開いて中身を見て
  能動的にクリックする」という、自動化されたプリフェッチ機構が通常たどらない経路でのみ
  発生するようにする
- **Alternatives considered**:
  - 1段階方式のまま、リンクをワンタイムかつ短時間(数分)で無効化する → 却下。
    プリフェッチは通常メール受信直後に発生するため、有効期限を短くしても防げない
  - リンクをPOSTフォーム化する(HTMLメールにフォームを埋め込む) → 却下。多くの
    メールクライアントはメール本文中の`<form>`やJavaScriptを実行できないため、
    実運用上機能しない
  - Step Functionsの`task_token`自体をDynamoDBに保存せず完全ステートレス(署名付き
    確認トークンをその場で生成)にする → 却下。ユーザーが明示的に要求した
    「トークンの状態を消費済みにマークする」という方針(再アクセス時の挙動を
    サーバー側で判定できる)を素直に満たすには、状態を持つ小さなテーブルの方が
    実装・検証ともに単純

## 未解決事項

なし。Technical Context の NEEDS CLARIFICATION はすべて上記で解消済み。
