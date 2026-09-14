# agent/step_functions.tf
# 承認ステートマシン(Standard型、wait-for-task-token + 2段階確認方式)。
# research.md §6・§11 / data-model.md 状態モデル / contracts/approval-flow.md 参照。
#
# 注意(既知の制約): SNS通知に埋め込むタスクトークンはURLエンコードせずそのまま
# 埋め込んでいる。Step Functionsのタスクトークンに稀に生じうるURL非セーフな文字への
# 対応は、本リポジトリの学習目的のスコープ外とする(将来の改善余地として記録)。
#
# 注意(ファイル間の参照): このステートマシンはagent/api_gateway.tf(T051)で定義する
# 承認コールバックAPIのURLをSNSメッセージに埋め込む。T051はT048より後のタスクだが、
# Terraformはファイル単位ではなくモジュール全体の依存グラフで解決するため、
# `terraform apply`時点で両方のリソースが定義されていれば問題ない
# (T047のLambda参照のような単純な前方参照ではなく、通知内容と通知先APIの間に生じる
# 構造的な相互参照であり、api_gateway.tf側をさらに分割しない限り解消できないため
# 許容する)。

resource "aws_cloudwatch_log_group" "approval_state_machine" {
  name              = "/aws/states/agent-approval-flow"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "approval_state_machine_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "approval_state_machine" {
  name               = "agent-approval-state-machine"
  assume_role_policy = data.aws_iam_policy_document.approval_state_machine_assume_role.json
}

data "aws_iam_policy_document" "approval_state_machine" {
  statement {
    sid       = "PublishApprovalRequest"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.approval_request.arn]
  }

  statement {
    sid       = "InvokeApplyLambdas"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.apply_decision.arn, aws_lambda_function.apply_rejection.arn]
  }

  # AWSのStep Functions - CloudWatch Logs連携(logging_configuration)は、これらの
  # ログ配信系アクションについてResourceを"*"にすることを要求する(AWS仕様)。
  statement {
    sid    = "StateMachineLogging"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "approval_state_machine" {
  name   = "agent-approval-state-machine-policy"
  role   = aws_iam_role.approval_state_machine.id
  policy = data.aws_iam_policy_document.approval_state_machine.json
}

locals {
  approval_base_url = aws_api_gateway_stage.approvals.invoke_url

  approval_state_machine_definition = jsonencode({
    Comment = "チケット完了の人間承認フロー(wait-for-task-token + 2段階確認方式)"
    StartAt = "RequestApproval"
    States = {
      RequestApproval = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish.waitForTaskToken"
        Parameters = {
          TopicArn = aws_sns_topic.approval_request.arn
          Subject  = "チケット完了の承認依頼"
          "Message.$" = join("", [
            "States.Format('チケット {} を「完了」にする操作の承認を求めています。",
            "\n承認: ${local.approval_base_url}/approvals?token={}&decision=approve",
            "\n却下: ${local.approval_base_url}/approvals?token={}&decision=reject",
            "\n(リンクを開いても即座には確定しません。内容を確認したうえで確認ページ",
            "上のリンクを押してください。応答がない場合、操作は実行されず保留のままに",
            "なります)', $.ticket_id, $$.Task.Token, $$.Task.Token)",
          ])
        }
        TimeoutSeconds = var.approval_timeout_seconds
        ResultPath     = "$.approval"
        Catch = [
          {
            ErrorEquals = ["States.Timeout"]
            ResultPath  = "$.error"
            Next        = "NotifyTimeout"
          },
          {
            ErrorEquals = ["Rejected"]
            ResultPath  = "$.error"
            Next        = "ApplyRejection"
          },
        ]
        Next = "ApplyDecision"
      }
      ApplyDecision = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.apply_decision.arn
          "Payload.$"  = "$"
        }
        End = true
      }
      ApplyRejection = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.apply_rejection.arn
          "Payload.$"  = "$"
        }
        End = true
      }
      NotifyTimeout = {
        Type    = "Pass"
        Comment = "タイムアウト到達。Ticket APIは一切呼ばず、チケットの状態は変更しない(FR-014/FR-015)。実行履歴自体がlogging_configuration経由でCloudWatch Logsに残る"
        End     = true
      }
    }
  })
}

resource "aws_sfn_state_machine" "approval" {
  name       = "agent-approval-flow"
  role_arn   = aws_iam_role.approval_state_machine.arn
  type       = "STANDARD"
  definition = local.approval_state_machine_definition

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.approval_state_machine.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }
}
