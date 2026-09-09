"""チケット管理APIのドメインエラー。

contracts/api.md の共通エラーレスポンス形式(error.code)に1対1で対応する。
"""

from __future__ import annotations


class DomainError(Exception):
    """ドメインエラーの基底クラス。"""

    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    """必須項目の欠落・空文字など、入力値が不正な場合。"""

    code = "VALIDATION_ERROR"
    status_code = 400


class NotFoundError(DomainError):
    """指定されたticket_idが存在しない場合。"""

    code = "NOT_FOUND"
    status_code = 404


class InvalidTransitionError(DomainError):
    """定義されていない状態遷移、または書き込み時点の競合(ConditionExpression不一致)。"""

    code = "INVALID_TRANSITION"
    status_code = 409
