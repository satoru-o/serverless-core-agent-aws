import pytest
from ticket_api.errors import ValidationError
from ticket_api.models import validate_ticket_input


def test_validate_ticket_input_accepts_valid_values():
    validate_ticket_input(title="バグ修正", description="詳細", assignee="satoru-o")


def test_validate_ticket_input_allows_empty_description():
    validate_ticket_input(title="バグ修正", description="", assignee="satoru-o")


@pytest.mark.parametrize("title", ["", "   ", None])
def test_validate_ticket_input_rejects_empty_title(title):
    with pytest.raises(ValidationError):
        validate_ticket_input(title=title, description="", assignee="satoru-o")


@pytest.mark.parametrize("assignee", ["", "   ", None])
def test_validate_ticket_input_rejects_empty_assignee(assignee):
    with pytest.raises(ValidationError):
        validate_ticket_input(title="バグ修正", description="", assignee=assignee)
