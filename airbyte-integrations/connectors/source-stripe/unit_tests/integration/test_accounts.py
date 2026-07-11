#
# Copyright (c) 2025 Airbyte, Inc., all rights reserved.
#

from datetime import datetime, timezone
from unittest import TestCase
from pathlib import Path

import freezegun
from unit_tests.conftest import get_source

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
class AccountsTest(TestCase):
    specmatic_process = None
    mock_host = "127.0.0.1"

    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys
        import time
        import requests
        import shutil
        import os

        # Resolve the repository root directory
        repo_root = Path(__file__).resolve().parents[5]
        fix_spec_script = repo_root / "specmatic_test" / "fix_spec.py"

        # Determine if we are running inside Docker
        is_docker = os.path.exists("/.dockerenv")
        cls.mock_host = "host.docker.internal" if is_docker else "127.0.0.1"

        # Dynamically configure url_base for the connector
        _CONFIG["url_base"] = f"http://{cls.mock_host}:9000/v1/"

        # Preprocess OpenAPI specs using the utility script if on host
        specmatic_bin = shutil.which("specmatic")
        if specmatic_bin:
            print("Running fix_spec.py to ensure specifications are modified...")
            subprocess.run([sys.executable, str(fix_spec_script)], check=True, cwd=str(repo_root))

            # Start the Specmatic mock server
            print("Starting Specmatic mock server...")
            cls.specmatic_process = subprocess.Popen(
                ["specmatic", "mock", "--port=9000"],
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )

            # Poll the mock server until it is ready
            retries = 20
            connected = False
            while retries > 0:
                try:
                    requests.get(f"http://{cls.mock_host}:9000")
                    connected = True
                    break
                except requests.exceptions.ConnectionError:
                    time.sleep(0.5)
                    retries -= 1

            if not connected:
                if cls.specmatic_process:
                    cls.specmatic_process.terminate()
                raise RuntimeError("Specmatic mock server failed to start on port 9000")
            print("Specmatic mock server started successfully on port 9000.")
        else:
            print("Specmatic executable not found. Assuming Specmatic mock server is already running on the host.")

    @classmethod
    def tearDownClass(cls):
        if cls.specmatic_process:
            print("Terminating Specmatic mock server...")
            cls.specmatic_process.terminate()
            cls.specmatic_process.wait()
            print("Specmatic mock server terminated.")

    def tearDown(self) -> None:
        import requests_cache
        import gc
        try:
            if hasattr(self, "source") and self.source:
                for stream in self.source.streams(config=_CONFIG):
                    if hasattr(stream, "retriever") and hasattr(stream.retriever, "requester"):
                        session = getattr(stream.retriever.requester, "_session", None)
                        if session:
                            session.close()
        except Exception as e:
            print(f"Error closing stream session: {e}")
        try:
            # Uninstall and clear requests_cache to release SQLite file handles on Windows
            requests_cache.uninstall_cache()
            requests_cache.clear()
        except Exception:
            pass
        gc.collect()

    def _set_specmatic_expectation(self, query: dict, response_body: dict) -> None:
        import requests
        url = f"http://{self.mock_host}:9000/_specmatic/expectations"
        payload = {
            "http-request": {
                "method": "GET",
                "path": "/v1/accounts",
                "query": query
            },
            "http-response": {
                "status": 200,
                "body": response_body
            }
        }
        resp = requests.post(url, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to set Specmatic expectation: {resp.status_code} - {resp.text}")

    def test_full_refresh(self) -> None:
        # Register Specmatic mock expectation for full refresh
        self._set_specmatic_expectation(
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
        self._set_specmatic_expectation(
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
        self._set_specmatic_expectation(
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
