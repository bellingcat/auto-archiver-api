from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
from app.shared.business_logic import get_store_archive_until

class Test_get_store_archive_until:
    GROUP_ID = "test-group"

    def test_group_not_found(self, db_session):
        with pytest.raises(AssertionError) as exc:
            get_store_archive_until(db_session, self.GROUP_ID)
        assert str(exc.value) == f"Group {self.GROUP_ID} not found."

    @patch("app.shared.db.worker_crud.get_group")
    def test_no_max_lifespan(self, mock_get_group, db_session):
        group = MagicMock()
        group.permissions = {"max_archive_lifespan_months": -1}
        mock_get_group.return_value = group

        result = get_store_archive_until(db_session, self.GROUP_ID)
        assert result is None
        mock_get_group.assert_called_once_with(db_session, self.GROUP_ID)

    @patch("app.shared.db.worker_crud.get_group")
    def test_with_max_lifespan(self, mock_get_group, db_session):
        group = MagicMock()
        group.permissions = {"max_archive_lifespan_months": 6}
        mock_get_group.return_value = group

        result = get_store_archive_until(db_session, self.GROUP_ID)
        expected = datetime.now() + timedelta(days=180)  # 6 months
        
        assert isinstance(result, datetime)
        # Allow 1 second difference due to execution time
        assert abs(result - expected) < timedelta(seconds=1)
        mock_get_group.assert_called_once_with(db_session, self.GROUP_ID)