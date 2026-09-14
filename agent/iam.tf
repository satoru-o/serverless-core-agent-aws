# agent/iam.tf
# 各Lambdaの実行ロール・ポリシーを定義する。IAMは「呼び出せるAPI・メソッド」までは
# 制御できるが「リクエストボディの値」までは制御できないため、重大操作(チケット完了)を
# 発行できるコードパスを承認後にしか呼ばれないLambdaだけに限定することで、最小権限原則
# (FR-001)とFR-011(重大操作の自動実行禁止)を実現する(research.md §3)。

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- T019: decision ロール ---
# 許可: Ticket APIのGET/PATCH(状態参照・IN_PROGRESSへの遷移はコード側で保証)、
# Bedrock Converse呼び出し。dynamodb:* / states:* はUS1時点では含めない。
# states:StartExecutionはUS3(T052)で追加する。

resource "aws_iam_role" "decision" {
  name               = "agent-decision-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "decision" {
  statement {
    sid     = "TicketApiReadAndStartProgress"
    effect  = "Allow"
    actions = ["execute-api:Invoke"]
    resources = [
      "${data.terraform_remote_state.core.outputs.ticket_api_execution_arn}/v1/GET/tickets",
      "${data.terraform_remote_state.core.outputs.ticket_api_execution_arn}/v1/GET/tickets/*",
      "${data.terraform_remote_state.core.outputs.ticket_api_execution_arn}/v1/PATCH/tickets/*/status",
    ]
  }

  statement {
    sid     = "BedrockConverse"
    effect  = "Allow"
    actions = ["bedrock:Converse"]
    resources = [
      "arn:aws:bedrock:ap-northeast-1:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_inference_profile_id}",
      "arn:aws:bedrock:*::foundation-model/${var.bedrock_foundation_model_id}",
    ]
  }

  # --- T052: 承認ステートマシンの起動権限 ---
  # decisionが発行できるのは「承認を求めるリクエスト」の起動のみであり、
  # 承認結果への応答(states:SendTaskSuccess/Failure、approval_callback専用)は含めない。
  statement {
    sid       = "StartApprovalExecution"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.approval.arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "decision" {
  name   = "agent-decision-lambda-policy"
  role   = aws_iam_role.decision.id
  policy = data.aws_iam_policy_document.decision.json
}

# --- T022: budget_stop ロール ---
# 許可: 対象EventBridgeルール(agent/eventbridge.tf T021)の無効化のみ。ルールARNを
# 参照するため、EventBridgeルール定義より後に定義する(/speckit-analyze F2対応)。

resource "aws_iam_role" "budget_stop" {
  name               = "agent-budget-stop-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "budget_stop" {
  statement {
    sid       = "DisableDecisionSchedule"
    effect    = "Allow"
    actions   = ["events:DisableRule"]
    resources = [aws_cloudwatch_event_rule.decision_schedule.arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "budget_stop" {
  name   = "agent-budget-stop-lambda-policy"
  role   = aws_iam_role.budget_stop.id
  policy = data.aws_iam_policy_document.budget_stop.json
}

# --- T046: apply_decision / apply_rejection ロール ---
# いずれもステートマシンのARNに依存しないため、承認ステートマシン定義(T048)より前に
# 用意できる(/speckit-analyze F3対応)。重大操作(DONE遷移)を発行できるのは
# apply_decisionだけであり、decisionロールにはこの権限を一切持たせない(FR-011)。

resource "aws_iam_role" "apply_decision" {
  name               = "agent-apply-decision-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "apply_decision" {
  statement {
    sid       = "TransitionToDone"
    effect    = "Allow"
    actions   = ["execute-api:Invoke"]
    resources = ["${data.terraform_remote_state.core.outputs.ticket_api_execution_arn}/v1/PATCH/tickets/*/status"]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "apply_decision" {
  name   = "agent-apply-decision-lambda-policy"
  role   = aws_iam_role.apply_decision.id
  policy = data.aws_iam_policy_document.apply_decision.json
}

resource "aws_iam_role" "apply_rejection" {
  name               = "agent-apply-rejection-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "apply_rejection" {
  statement {
    sid       = "TransitionToOpen"
    effect    = "Allow"
    actions   = ["execute-api:Invoke"]
    resources = ["${data.terraform_remote_state.core.outputs.ticket_api_execution_arn}/v1/PATCH/tickets/*/status"]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "apply_rejection" {
  name   = "agent-apply-rejection-lambda-policy"
  role   = aws_iam_role.apply_rejection.id
  policy = data.aws_iam_policy_document.apply_rejection.json
}

# --- T049: approval_callback ロール ---
# ステートマシンARN(T048)を参照するため、ステートマシン定義より後に定義する
# (/speckit-analyze F3対応)。Ticket APIへのアクセス権限は一切持たせない
# (承認リンクの処理自体はチケットを直接操作できない、research.md §3)。

resource "aws_iam_role" "approval_callback" {
  name               = "agent-approval-callback-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "approval_callback" {
  statement {
    sid       = "RespondToApprovalTask"
    effect    = "Allow"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = [aws_sfn_state_machine.approval.arn]
  }

  statement {
    sid       = "ApprovalLinksTable"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.approval_links.arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "approval_callback" {
  name   = "agent-approval-callback-lambda-policy"
  role   = aws_iam_role.approval_callback.id
  policy = data.aws_iam_policy_document.approval_callback.json
}
