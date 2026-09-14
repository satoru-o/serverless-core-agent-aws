# agent/lambda.tf
# agent/src を丸ごとZIP化し、複数のLambda関数(decision / budget_stop / ...)で共有する。
# ハンドラはそれぞれの関数ごとに切り替える(core/lambda.tfの単一関数構成と異なり、
# 002-agent-safe-operationでは責務ごとにLambda・IAMロールを分離するため複数関数になる。
# research.md §3)。

data "archive_file" "ticket_agent" {
  type        = "zip"
  source_dir  = "${path.module}/src"
  output_path = "${path.module}/.build/ticket_agent.zip"
  excludes    = ["**/__pycache__", "**/__pycache__/**"]
}

# --- T020: decision Lambda ---

resource "aws_lambda_function" "decision" {
  function_name = "agent-decision"
  role          = aws_iam_role.decision.arn
  handler       = "ticket_agent.decision_handler.lambda_handler"
  runtime       = "python3.13"
  timeout       = var.decision_timeout_seconds
  memory_size   = 128

  filename         = data.archive_file.ticket_agent.output_path
  source_code_hash = data.archive_file.ticket_agent.output_base64sha256

  environment {
    variables = {
      EXECUTION_LIMIT            = tostring(var.execution_limit)
      TICKET_API_BASE_URL        = data.terraform_remote_state.core.outputs.ticket_api_endpoint
      BEDROCK_MODEL_ID           = var.bedrock_inference_profile_id
      APPROVAL_STATE_MACHINE_ARN = aws_sfn_state_machine.approval.arn
    }
  }
}

# --- T023: budget_stop Lambda ---
# budget_stopロール(agent/iam.tf T022)・EventBridgeルール(agent/eventbridge.tf T021)に依存。

resource "aws_lambda_function" "budget_stop" {
  function_name = "agent-budget-stop"
  role          = aws_iam_role.budget_stop.arn
  handler       = "ticket_agent.budget_stop_handler.lambda_handler"
  runtime       = "python3.13"
  timeout       = 30
  memory_size   = 128

  filename         = data.archive_file.ticket_agent.output_path
  source_code_hash = data.archive_file.ticket_agent.output_base64sha256

  environment {
    variables = {
      DECISION_SCHEDULE_RULE_NAME = aws_cloudwatch_event_rule.decision_schedule.name
    }
  }
}

# --- T047: apply_decision / apply_rejection Lambda ---
# 承認ステートマシン(agent/step_functions.tf T048)がこれらのLambda ARNを参照するため、
# ステートマシン定義より前に定義する(/speckit-analyze F3対応)。

resource "aws_lambda_function" "apply_decision" {
  function_name = "agent-apply-decision"
  role          = aws_iam_role.apply_decision.arn
  handler       = "ticket_agent.apply_decision_handler.lambda_handler"
  runtime       = "python3.13"
  timeout       = 30
  memory_size   = 128

  filename         = data.archive_file.ticket_agent.output_path
  source_code_hash = data.archive_file.ticket_agent.output_base64sha256

  environment {
    variables = {
      TICKET_API_BASE_URL = data.terraform_remote_state.core.outputs.ticket_api_endpoint
    }
  }
}

resource "aws_lambda_function" "apply_rejection" {
  function_name = "agent-apply-rejection"
  role          = aws_iam_role.apply_rejection.arn
  handler       = "ticket_agent.apply_rejection_handler.lambda_handler"
  runtime       = "python3.13"
  timeout       = 30
  memory_size   = 128

  filename         = data.archive_file.ticket_agent.output_path
  source_code_hash = data.archive_file.ticket_agent.output_base64sha256

  environment {
    variables = {
      TICKET_API_BASE_URL = data.terraform_remote_state.core.outputs.ticket_api_endpoint
    }
  }
}

# --- T050: approval_callback Lambda ---
# approval_callbackロール(T049)に依存。承認コールバック用API Gateway(T051)が
# このLambdaの invoke_arn を参照する。

resource "aws_lambda_function" "approval_callback" {
  function_name = "agent-approval-callback"
  role          = aws_iam_role.approval_callback.arn
  handler       = "ticket_agent.approval_callback_handler.lambda_handler"
  runtime       = "python3.13"
  timeout       = 10
  memory_size   = 128

  filename         = data.archive_file.ticket_agent.output_path
  source_code_hash = data.archive_file.ticket_agent.output_base64sha256

  environment {
    variables = {
      APPROVAL_LINKS_TABLE_NAME = aws_dynamodb_table.approval_links.name
      APPROVAL_TIMEOUT_SECONDS  = tostring(var.approval_timeout_seconds)
    }
  }
}
