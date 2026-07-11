#
# Copyright (c) 2025 Airbyte, Inc., all rights reserved.
#

from datetime import datetime, timezone
from pathlib import Path

import freezegun
from unit_tests.conftest import get_source
from unit_tests.specmatic import SpecmaticIntegrationTestCase

from airbyte_cdk.models import ConfiguredAirbyteCatalog, SyncMode
from airbyte_cdk.test.catalog_builder import CatalogBuilder
from airbyte_cdk.test.entrypoint_wrapper import read
from airbyte_cdk.test.state_builder import StateBuilder


_STREAM_NAME = "accounts"
_ACCOUNT_ID = "acct_1G9HZLIEn49ers"
_CLIENT_SECRET = "ConfigBuilder default client secret"
_NOW = datetime.now(timezone.utc)
_CONFIG = {
    "client_secret": _CLIENT_SECRET,
    "account_id": _ACCOUNT_ID,
    "url_base": "http://127.0.0.1:9000/v1/"
}
_NO_STATE = StateBuilder().build()


def _create_catalog(sync_mode: SyncMode = SyncMode.full_refresh) -> ConfiguredAirbyteCatalog:
    return CatalogBuilder().with_stream(name="accounts", sync_mode=sync_mode).build()


@freezegun.freeze_time(_NOW.isoformat())
class AccountsTest(SpecmaticIntegrationTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Dynamically point connector config to the Specmatic mock server URL
        _CONFIG["url_base"] = cls.config["url_base"]

    def test_full_refresh(self) -> None:
        # Register Specmatic mock expectation for full refresh
        self.set_specmatic_expectation(
            path="/v1/accounts",
            query={"limit": "100"},
            response_body={
                "object": "list",
                "url": "/v1/accounts",
                "has_more": False,
                "data": [
                    {
                        "id": _ACCOUNT_ID,
                        "object": "account"
                    }
                ]
            }
        )

        self.source = get_source(config=_CONFIG, state=_NO_STATE)
        actual_messages = read(self.source, config=_CONFIG, catalog=_create_catalog())

        assert len(actual_messages.records) == 1

    def test_pagination(self) -> None:
        # Register Specmatic mock expectation for page 1
        self.set_specmatic_expectation(
            path="/v1/accounts",
            query={"limit": "100"},
            response_body={
                "object": "list",
                "url": "/v1/accounts",
                "has_more": True,
                "data": [
                    {
                        "id": "last_record_id_from_first_page",
                        "object": "account"
                    }
                ]
            }
        )

        # Register Specmatic mock expectation for page 2
        self.set_specmatic_expectation(
            path="/v1/accounts",
            query={"limit": "100", "starting_after": "last_record_id_from_first_page"},
            response_body={
                "object": "list",
                "url": "/v1/accounts",
                "has_more": False,
                "data": [
                    {
                        "id": _ACCOUNT_ID,
                        "object": "account"
                    }
                ]
            }
        )

        self.source = get_source(config=_CONFIG, state=_NO_STATE)
        actual_messages = read(self.source, config=_CONFIG, catalog=_create_catalog())

        assert len(actual_messages.records) == 2
