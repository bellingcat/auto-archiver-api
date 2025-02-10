from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pytest

from app.shared.config import ALLOW_ANY_EMAIL


def test_secure_compare():
    from web.security import secure_compare

    assert secure_compare("test", "test")
    assert not secure_compare("test", "test2")


@pytest.mark.asyncio
async def test_get_token_or_user_auth_with_api():
    from web.security import get_token_or_user_auth
    mock_api = HTTPAuthorizationCredentials(scheme="lorem", credentials="this_is_the_test_api_token")
    assert await get_token_or_user_auth(mock_api) == ALLOW_ANY_EMAIL


@pytest.mark.asyncio
async def test_get_token_or_user_auth_with_user():
    from web.security import get_token_or_user_auth
    bad_user = HTTPAuthorizationCredentials(scheme="ipsum", credentials="invalid")
    e: pytest.ExceptionInfo = None
    with pytest.raises(HTTPException) as e:
        await get_token_or_user_auth(bad_user)
    assert e.value.status_code == 401
    assert e.value.detail == "invalid access_token"


@patch("web.security.authenticate_user", return_value=(True, "summer@example.com"))
@pytest.mark.asyncio
async def test_get_user_auth(m1):
    from web.security import get_user_auth
    good_user = HTTPAuthorizationCredentials(scheme="ipsum", credentials="valid-and-good")
    assert await get_user_auth(good_user) == "summer@example.com"


@patch("web.security.secure_compare", return_value=False)
@pytest.mark.asyncio
async def test_token_api_key_auth_exception(m1):
    from web.security import token_api_key_auth

    e: pytest.ExceptionInfo = None
    with pytest.raises(HTTPException) as e:
        await token_api_key_auth(HTTPAuthorizationCredentials(scheme="ipsum", credentials="does-not-matter"), auto_error=True)
    assert e.value.status_code == 401
    assert e.value.detail == "Wrong auth credentials"


@pytest.mark.asyncio
async def test_authenticate_user():
    from web.security import authenticate_user

    assert authenticate_user("test") == (False, "invalid access_token")
    assert authenticate_user(123) == (False, "invalid access_token")

    with patch("web.security.requests.get") as mock_get:
        # bad response from oauth2
        mock_get.return_value.status_code = 403
        assert authenticate_user("this-will-call-requests") == (False, "invalid token")
        assert mock_get.call_count == 1

        # 200 but invalid json
        mock_get.return_value.status_code = 200
        assert authenticate_user("this-will-call-requests") == (False, "token does not belong to valid APP_ID")
        assert mock_get.call_count == 2

        # 200 but invalid azp and aud
        mock_get.return_value.json.return_value = {"email": "summer@example.com", "azp": "not_an_app"}
        assert authenticate_user("this-will-call-requests") == (False, "token does not belong to valid APP_ID")

        mock_get.return_value.json.return_value = {"email": "summer@example.com", "aud": "not_an_app"}
        assert authenticate_user("this-will-call-requests") == (False, "token does not belong to valid APP_ID")

        mock_get.return_value.json.return_value = {"email": "summer@example.com", "azp": "not_an_app", "aud": "not_an_app"}
        assert authenticate_user("this-will-call-requests") == (False, "token does not belong to valid APP_ID")

        # blocked email
        mock_get.return_value.json.return_value = {"email": "blocked@example.com", "azp": "test_app_id_1", "aud": "not_an_app"}
        assert authenticate_user("this-will-call-requests") == (False, "email 'blocked@example.com' not allowed")

        # not verified
        mock_get.return_value.json.return_value = {"email": "summer@example.com", "azp": "not_an_app", "aud": "test_app_id_1"}
        assert authenticate_user("this-will-call-requests") == (False, "email 'summer@example.com' not verified")

        # token expired
        mock_get.return_value.json.return_value = {"email": "summer@example.com", "azp": "test_app_id_2", "email_verified": "true"}
        assert authenticate_user("this-will-call-requests") == (False, "Token expired")

        # 200 and valid azp and aup and verified
        mock_get.return_value.json.return_value = {"email": "summer@example.com", "azp": "test_app_id_2", "email_verified": "true", "expires_in": 100}
        assert authenticate_user("this-will-call-requests") == (True, "summer@example.com")
        assert mock_get.call_count == 9


@pytest.mark.asyncio
async def test_authenticate_user_exception():
    from web.security import authenticate_user

    with patch("web.security.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.side_effect = Exception("mocked error")
        assert authenticate_user("this-will-call-requests") == (False, "exception occurred")
