# Stripe Specmatic Contract Validation & Integration Testing

This document details the file creations and modifications introduced to support **contract-driven integration testing** and **OpenAPI contract validation** for the Airbyte Stripe source connector.

---

## 1. Created Files

These files were created to set up the Specmatic testing framework, provide spec schemas, run contract compliance validation, and document the architecture.

### Specmatic Specifications & Preprocessing
*   **[specmatic.yaml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/specmatic.yaml)**
    *   **Why**: Required by Specmatic to configure mock servers and map path resources to OpenAPI specifications.
    *   **How**: Configured Specmatic to point to local Stripe specs.
*   **[stripe-official.json](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/specmatic_test/specs/stripe-official.json)**
    *   **Why**: Serves as the OpenAPI contract source of truth. It defines the schemas against which client requests and mock server responses are verified.
*   **[stripe-drifted.json](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/specmatic_test/specs/stripe-drifted.json)**
    *   **Why**: Created as an intentionally modified version of the specification. It is used to verify that the validation runner successfully catches schema changes (contract drift).
*   **[fix_spec.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/specmatic_test/fix_spec.py)**
    *   **Why**: Stripe's raw OpenAPI specification is extremely large, nested, and contains structures that cause parsing issues in Specmatic.
    *   **How**: Automatically flattens nested query parameters (e.g., `created[gte]`), injects missing schemas for target streams, prunes overly strict `required` fields to prevent mock failures, and maps clean, unique `operationId`s.

### Test Infrastructure & Runner
*   **[__init__.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/specmatic/__init__.py)**
    *   **Why**: Standard Python package initializer to structure the `specmatic` test files.
*   **[server.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/specmatic/server.py)**
    *   **Why**: To manage starting, stopping, and checking the status of the background Specmatic mock server subprocess.
    *   **How**: Implemented process controls and cross-platform termination logic (e.g., executing `taskkill` on Windows to cleanly terminate Java subprocesses).
*   **[base_test.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/specmatic/base_test.py)**
    *   **Why**: To provide a standardized base test class (`SpecmaticIntegrationTestCase`) that handles server lifecycles, expectation mappings, and cache isolation.
    *   **How**: Clears `requests_cache` and deletes the SQLite cache database (`test_cache.sqlite`) during setup and teardown to prevent connection locks between test executions.
*   **[run_validation.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py)**
    *   **Why**: Acts as the script execution harness that calls the connector, runs read operations against the Specmatic Mock Server, translates OpenAPI models to Draft-7 JSON schemas, and validates responses.

### CI Workflows & Documentation
*   **[stripe_contract_validation.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/stripe_contract_validation.yml)**
    *   **Why**: GitHub Actions workflow to run the contract validation runner automatically on pull requests/pushes touching Stripe connector code.
*   **[README.md](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/specmatic_test/README.md)**
    *   **Why**: Developer onboarding guide detailing local setup, prerequisite commands, architecture details, and verification flows.
*   **[official_report.md](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/specmatic_test/official_report.md)** & **[drift_report.md](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/specmatic_test/drift_report.md)**
    *   **Why**: Stores the resulting output of validation checks to quickly review compatibility passes or detected failures.

---

## 2. Modified Files

These files were modified to route integration tests through Specmatic and clean up CI/CD workflows for fork repositories.

### GitHub Workflows

*   **Workflow Schedule Deletions (16 files)**
    *   *Affected files*: [agent-sdk-docs-generate.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/agent-sdk-docs-generate.yml), [auto-merge-cron.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/auto-merge-cron.yml), [auto-upgrade-certified-connectors-cdk.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/auto-upgrade-certified-connectors-cdk.yml), [cdk-destination-connector-compatibility-test.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/cdk-destination-connector-compatibility-test.yml), [cdk-source-connector-compatibility-test.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/cdk-source-connector-compatibility-test.yml), [codeql.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/codeql.yml), [connectors-up-to-date.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/connectors-up-to-date.yml), [daily-sonar-release-notes.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/daily-sonar-release-notes.yml), [docker-image-pruning.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/docker-image-pruning.yml), [pyairbyte-docs-generate.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/pyairbyte-docs-generate.yml), [regenerate-agent-engine-api-spec.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/regenerate-agent-engine-api-spec.yml), [resolve-stale-metadata.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/resolve-stale-metadata.yml), [stale-community-issues.yaml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/stale-community-issues.yaml), [stale-discussions-autoclose.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/stale-discussions-autoclose.yml), [stale-routed-issues.yaml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/stale-routed-issues.yaml), [sync-ai-connector-docs.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/sync-ai-connector-docs.yml)
    *   **Why**: Removing `schedule:` (cron triggers) stops GitHub Actions from running daily tasks automatically on developer forks, where they would fail due to lacking repository secrets.
    *   **How**: Removed the `schedule` blocks under the `on:` trigger list.
*   **[format_check.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/format_check.yml)**
    *   **Why**: Prevent Slack notifications from throwing workflow errors during fork executions.
    *   **How**: Restricted the Slack steps via a condition: `github.repository == 'airbytehq/airbyte'`.
*   **[run-connector-tests-command.yml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/.github/workflows/run-connector-tests-command.yml)**
    *   **Why**: To ensure security permissions are properly inherited.
    *   **How**: Added write permissions (`checks: write`, `pull-requests: write`, `contents: read`) to the main test jobs.

### Stripe Source Connector Files

*   **[manifest.yaml](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/manifest.yaml)**
    *   **Why**: Minor schema and parameters adjustment to align configurations for mock runs.
*   **Stripe Integration Test Suites (11 files)**
    *   *Affected files*: [test_accounts.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_accounts.py), [test_application_fees.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_application_fees.py), [test_authorizations.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_authorizations.py), [test_cards.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_cards.py), [test_early_fraud_warnings.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_early_fraud_warnings.py), [test_events.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_events.py), [test_payment_methods.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_payment_methods.py), [test_payout_balance_transactions.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_payout_balance_transactions.py), [test_reviews.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_reviews.py), [test_setup_attempts.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_setup_attempts.py), [test_transactions.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_transactions.py)
    *   **Why**: Migrate files to use contract-driven expectations instead of arbitrary mock response templates. This guarantees mock specs are always checked against the real OpenAPI schema.
    *   **How**:
        1. Changed inheritance from standard `unittest.TestCase` to `SpecmaticIntegrationTestCase`.
        2. Set the base URL (`url_base`) dynamically in `setUpClass` to target the local mock server.
        3. Removed `@HttpMocker` annotations and internal mock builder classes.
        4. Replaced the manual stub mocking logic with `self.set_specmatic_expectation()`.
