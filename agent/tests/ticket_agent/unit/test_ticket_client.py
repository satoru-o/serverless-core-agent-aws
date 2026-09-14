import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from botocore.credentials import Credentials

from ticket_agent.errors import TicketApiError, UnauthorizedTicketApiCallError
from ticket_agent.ticket_client import TicketClient


def _fake_credentials() -> Credentials:
    return Credentials("AKIAFAKEEXAMPLE", "fakesecretkey", token=None)


def _mock_response(body: dict) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(body).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


@patch("ticket_agent.ticket_client.urllib.request.urlopen")
@patch("ticket_agent.ticket_client.boto3.Session")
def test_get_ticket_signs_request_and_returns_json(mock_session, mock_urlopen):
    mock_session.return_value.get_credentials.return_value = _fake_credentials()
    mock_urlopen.return_value = _mock_response({"ticket_id": "abc", "status": "OPEN"})

    client = TicketClient(base_url="https://example.com/v1")
    result = client.get_ticket("abc")

    assert result == {"ticket_id": "abc", "status": "OPEN"}
    sent_request = mock_urlopen.call_args[0][0]
    assert sent_request.get_method() == "GET"
    assert sent_request.full_url == "https://example.com/v1/tickets/abc"
    # SigV4Authが付与するヘッダが実際にリクエストに載っていることを確認する
    assert sent_request.get_header("Authorization") is not None
    assert sent_request.get_header("Authorization").startswith("AWS4-HMAC-SHA256")
    assert sent_request.get_header("X-amz-date") is not None


@patch("ticket_agent.ticket_client.urllib.request.urlopen")
@patch("ticket_agent.ticket_client.boto3.Session")
def test_list_tickets_with_status_filter(mock_session, mock_urlopen):
    mock_session.return_value.get_credentials.return_value = _fake_credentials()
    mock_urlopen.return_value = _mock_response({"tickets": [{"ticket_id": "a"}]})

    client = TicketClient(base_url="https://example.com/v1")
    result = client.list_tickets(status="OPEN")

    assert result == [{"ticket_id": "a"}]
    sent_request = mock_urlopen.call_args[0][0]
    assert sent_request.full_url == "https://example.com/v1/tickets?status=OPEN"


@patch("ticket_agent.ticket_client.urllib.request.urlopen")
@patch("ticket_agent.ticket_client.boto3.Session")
def test_update_status_sends_signed_patch_with_json_body(mock_session, mock_urlopen):
    mock_session.return_value.get_credentials.return_value = _fake_credentials()
    mock_urlopen.return_value = _mock_response({"ticket_id": "abc", "status": "IN_PROGRESS"})

    client = TicketClient(base_url="https://example.com/v1")
    result = client.update_status("abc", "IN_PROGRESS")

    assert result["status"] == "IN_PROGRESS"
    sent_request = mock_urlopen.call_args[0][0]
    assert sent_request.get_method() == "PATCH"
    assert json.loads(sent_request.data) == {"status": "IN_PROGRESS"}


@patch("ticket_agent.ticket_client.urllib.request.urlopen")
@patch("ticket_agent.ticket_client.boto3.Session")
def test_403_response_raises_unauthorized_error(mock_session, mock_urlopen):
    mock_session.return_value.get_credentials.return_value = _fake_credentials()
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://example.com/v1/tickets", code=403, msg="Forbidden", hdrs=None, fp=None
    )

    client = TicketClient(base_url="https://example.com/v1")
    with pytest.raises(UnauthorizedTicketApiCallError) as excinfo:
        client.list_tickets()

    assert excinfo.value.method == "GET"
    assert excinfo.value.path == "/tickets"


@patch("ticket_agent.ticket_client.urllib.request.urlopen")
@patch("ticket_agent.ticket_client.boto3.Session")
def test_non_403_error_raises_ticket_api_error(mock_session, mock_urlopen):
    mock_session.return_value.get_credentials.return_value = _fake_credentials()
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://example.com/v1/tickets/abc",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=io.BytesIO(b"boom"),
    )

    client = TicketClient(base_url="https://example.com/v1")
    with pytest.raises(TicketApiError):
        client.get_ticket("abc")
