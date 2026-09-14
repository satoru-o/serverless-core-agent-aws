"""エージェント共通のドメイン例外。"""


class TicketApiError(Exception):
    """Ticket API呼び出しで発生した予期しないエラー。"""


class UnauthorizedTicketApiCallError(TicketApiError):
    """Ticket APIが403(許可範囲外の呼び出し)を返した場合に送出される。"""

    def __init__(self, method: str, path: str):
        self.method = method
        self.path = path
        super().__init__(f"unauthorized ticket api call: {method} {path}")


class ExecutionLimitReachedError(Exception):
    """1回の実行あたりのTicket API呼び出し回数上限に達した場合に送出される。"""


class InvalidApprovalLinkError(Exception):
    """承認/却下リンクのトークンが無効・期限切れ・既に処理済みの場合に送出される。"""
