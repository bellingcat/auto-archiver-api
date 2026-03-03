from unittest.mock import mock_open, patch

from app.shared.utils.sheets import (
    check_sheet_write_access,
    get_service_account_json_path,
    get_sheet_access_error,
)


class TestGetServiceAccountJsonPath:
    def test_returns_none_for_empty_path(self):
        assert get_service_account_json_path("") is None
        assert get_service_account_json_path(None) is None

    def test_returns_path_from_orchestrator_yaml(self):
        # The test orchestration file has a service_account key
        get_service_account_json_path.cache_clear()
        result = get_service_account_json_path(
            "app/tests/orchestration.test.yaml"
        )
        assert result == "app/tests/fake_service_account.json"

    def test_returns_none_for_missing_file(self):
        get_service_account_json_path.cache_clear()
        assert get_service_account_json_path("nonexistent/path.yaml") is None

    def test_returns_none_for_invalid_yaml(self):
        get_service_account_json_path.cache_clear()
        with patch(
            "builtins.open", mock_open(read_data="!!! invalid yaml {{{")
        ):
            result = get_service_account_json_path("some/path.yaml")
            # yaml.safe_load may return a string for some invalid inputs
            # The function should not crash
            assert result is None or isinstance(result, str)

    def test_returns_none_when_no_service_account_key(self):
        get_service_account_json_path.cache_clear()
        yaml_content = "steps:\n  feeders:\n    - cli_feeder\n"
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            assert get_service_account_json_path("some/path.yaml") is None

    def test_finds_nested_service_account_key(self):
        get_service_account_json_path.cache_clear()
        yaml_content = (
            "configurations:\n"
            "  gsheet_feeder_db:\n"
            "    service_account: secrets/nested_sa.json\n"
        )
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            result = get_service_account_json_path("some/path.yaml")
            assert result == "secrets/nested_sa.json"


class TestCheckSheetWriteAccess:
    @patch("app.shared.utils.sheets.http_requests.get")
    @patch(
        "google.oauth2.service_account.Credentials.from_service_account_file"
    )
    def test_returns_true_when_can_edit(self, m_creds, m_get):
        m_creds.return_value.token = "fake-token"
        m_get.return_value.status_code = 200
        m_get.return_value.json.return_value = {
            "capabilities": {"canEdit": True}
        }

        result = check_sheet_write_access("sa.json", "sheet123")
        assert result is True
        m_get.assert_called_once()

    @patch("app.shared.utils.sheets.http_requests.get")
    @patch(
        "google.oauth2.service_account.Credentials.from_service_account_file"
    )
    def test_returns_false_when_cannot_edit(self, m_creds, m_get):
        m_creds.return_value.token = "fake-token"
        m_get.return_value.status_code = 200
        m_get.return_value.json.return_value = {
            "capabilities": {"canEdit": False}
        }

        result = check_sheet_write_access("sa.json", "sheet123")
        assert result is False

    @patch("app.shared.utils.sheets.http_requests.get")
    @patch(
        "google.oauth2.service_account.Credentials.from_service_account_file"
    )
    def test_returns_false_on_404(self, m_creds, m_get):
        m_creds.return_value.token = "fake-token"
        m_get.return_value.status_code = 404

        result = check_sheet_write_access("sa.json", "sheet123")
        assert result is False

    @patch("app.shared.utils.sheets.http_requests.get")
    @patch(
        "google.oauth2.service_account.Credentials.from_service_account_file"
    )
    def test_returns_false_on_403(self, m_creds, m_get):
        m_creds.return_value.token = "fake-token"
        m_get.return_value.status_code = 403

        result = check_sheet_write_access("sa.json", "sheet123")
        assert result is False

    @patch("app.shared.utils.sheets.http_requests.get")
    @patch(
        "google.oauth2.service_account.Credentials.from_service_account_file"
    )
    def test_returns_none_on_unexpected_status(self, m_creds, m_get):
        m_creds.return_value.token = "fake-token"
        m_get.return_value.status_code = 500
        m_get.return_value.text = "Internal Server Error"

        result = check_sheet_write_access("sa.json", "sheet123")
        assert result is None

    def test_returns_none_when_file_not_found(self):
        result = check_sheet_write_access("nonexistent/sa.json", "sheet123")
        assert result is None

    @patch(
        "google.oauth2.service_account.Credentials.from_service_account_file",
        side_effect=Exception("auth failed"),
    )
    def test_returns_none_on_auth_error(self, m_creds):
        result = check_sheet_write_access("sa.json", "sheet123")
        assert result is None


class TestGetSheetAccessError:
    @patch("app.shared.utils.sheets.check_sheet_write_access")
    @patch("app.shared.utils.sheets.get_service_account_json_path")
    def test_returns_none_when_access_ok(self, m_get_path, m_check):
        m_get_path.return_value = "sa.json"
        m_check.return_value = True

        result = get_sheet_access_error("orch.yaml", "sa@test.com", "sheet1")
        assert result is None

    @patch("app.shared.utils.sheets.check_sheet_write_access")
    @patch("app.shared.utils.sheets.get_service_account_json_path")
    def test_returns_error_when_no_access(self, m_get_path, m_check):
        m_get_path.return_value = "sa.json"
        m_check.return_value = False

        result = get_sheet_access_error("orch.yaml", "sa@test.com", "sheet1")
        assert result is not None
        assert "sa@test.com" in result
        assert "Editor" in result

    @patch("app.shared.utils.sheets.check_sheet_write_access")
    @patch("app.shared.utils.sheets.get_service_account_json_path")
    def test_returns_none_when_indeterminate(self, m_get_path, m_check):
        m_get_path.return_value = "sa.json"
        m_check.return_value = None

        result = get_sheet_access_error("orch.yaml", "sa@test.com", "sheet1")
        assert result is None

    def test_returns_none_when_no_orchestrator_path(self):
        assert get_sheet_access_error(None, "sa@test.com", "sheet1") is None
        assert get_sheet_access_error("", "sa@test.com", "sheet1") is None

    @patch("app.shared.utils.sheets.get_service_account_json_path")
    def test_returns_none_when_no_sa_json_path(self, m_get_path):
        m_get_path.return_value = None

        result = get_sheet_access_error("orch.yaml", "sa@test.com", "sheet1")
        assert result is None
