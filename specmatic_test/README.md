# Stripe Connector OpenAPI Contract Validation

This directory contains the tools, OpenAPI specifications, and scripts to perform automated OpenAPI contract validation for the Airbyte Stripe source connector.

> **Requires**: Node.js 18+, Python 3.11+, Docker, Specmatic v2.49.1+

## Architecture Overview

Specmatic is used in this repository for two primary testing workflows:

1. **Contract Validation Runner (`run_validation.py`)**: Runs full connector syncs, routing requests to the Specmatic mock server. Specmatic validates the connector's requests against the Stripe API contract and returns mocked records matching the OpenAPI response schema. The runner extracts these records and validates them against the schema components using Python's `jsonschema` library, outputting a markdown drift report.
2. **Converted Integration Tests (`test_accounts.py`)**: Runs standard pytest integration tests. During the test class lifecycle, it automatically spins up the Specmatic mock server on the host, registers dynamic contract-validated expectations, executes the connector reads, and asserts record counts. Specmatic validates all incoming HTTP requests against the Stripe OpenAPI specification.

### Before (Old Airbyte Integration Test)

```
                    Static JSON Mock
                           |
                           v
             +---------------------------+
             | accounts.json             |
             | (hardcoded response)      |
             +---------------------------+
                          |
                          v
             +---------------------------+
             | HttpMocker                |
             | (requests-mock)           |
             +---------------------------+
                          ^
                          |
              HTTP Request|
                          |
             +---------------------------+
             | Airbyte Stripe Connector  |
             | (runs actual code)        |
             +---------------------------+
                          |
                          v
             +---------------------------+
             | Test Assertions           |
             | Record count, fields      |
             +---------------------------+
```

**Characteristics**:
* Static JSON
* No OpenAPI validation
* Manual maintenance
* Contract drift possible

### New Workflow (Specmatic POC)

```
                    Stripe OpenAPI Specification
                              |
                              |
                    +-------------------+
                    |   fix_spec.py     |
                    | (preprocess spec) |
                    +-------------------+
                              |
                              v
                 Modified Stripe OpenAPI Spec
                              |
                              |
                +----------------------------+
                | Specmatic Mock Server      |
                | (starts in setUpClass)     |
                +----------------------------+
                   ^                     |
                   |                     |
        POST /_specmatic/expectations    |
        (dynamic expectations)           |
                   |                     |
                   |             Validates Request
                   |             against OpenAPI
                   |                     |
+---------------------------+            |
| test_accounts.py          |------------+
| Registers Expectations    |
+---------------------------+
              |
              |
              v
+---------------------------+
| Airbyte Stripe Connector  |
| (runs actual code)        |
+---------------------------+
              |
              |
      HTTP Request
              |
              v
+----------------------------+
| Specmatic Mock Server      |
| - validates request        |
| - returns mock response    |
| - validates response       |
+----------------------------+
              |
              v
+---------------------------+
| Connector parses records  |
+---------------------------+
              |
              v
+---------------------------+
| Test Assertions           |
| Record count              |
| Pagination                |
| Stream output             |
+---------------------------+
```

**Characteristics**:
* Dynamic contract-based mocking
* Real-time OpenAPI contract validation of requests
* Low maintenance (stubs conform to schema changes automatically)
* Prevents contract drift

## Setup & Files

- `specs/stripe-official.json`: Pruned official Stripe OpenAPI specification containing the endpoints under test (`/v1/customers`, `/v1/charges`, `/v1/invoices`, `/v1/payment_intents`, `/v1/products`, `/v1/prices`, `/v1/refunds`, and `/v1/accounts` added for POC).
- `specs/stripe-drifted.json`: A modified Stripe specification containing drifted properties and types to simulate API drift and verify validation failures.
- `fix_spec.py`: Python utility that automatically flattens deepObject parameters (such as `created[gte]`) and duplicates array parameters (such as `expand[]`) to work around Specmatic exact-match limits on array and object query parameters.
- `run_validation.py` (located in the connector's `unit_tests` directory): The test runner that instantiates the actual connector sources, executes incremental reads via `airbyte_cdk.test.entrypoint_wrapper.read`, processes response records, and writes validation reports.
- `airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_accounts.py`: Converted integration test that runs against a local Specmatic mock server and verifies requests dynamically using the expectations API.
- `.github/workflows/stripe_contract_validation.yml`: GitHub Actions CI workflow to run validation automatically on PRs.

## How to Run Validation Locally

### 1. Requirements

Ensure you have the following installed:

- Node.js v18+
- Python 3.11+
- Docker
- Specmatic v2.49.1+: `npm install -g specmatic@2.49.1`

### 2. Flatten deepObject Query Parameters

First, run the spec modifier script to prepare the specifications for Specmatic mock matching:

```bash
python specmatic_test/fix_spec.py
```

### 3. Run Validation against the Official Stripe Specification

`specmatic.yaml` already references `stripe-official.json` via the `dependencies` block, so no explicit spec path is needed.

1. Start the Specmatic mock server from the repo root:
   ```bash
   specmatic mock --port 9000
   ```
2. Run the validation runner using Docker:
   - **macOS / Linux (Bash/Zsh)**:
     ```bash
     docker run --rm \
       --add-host=host.docker.internal:host-gateway \
       -v "$(pwd):/workspace" \
       python:3.11-slim \
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-official.json --report-output /workspace/specmatic_test/official_report.md --host host.docker.internal"
     ```
   - **Windows (PowerShell)**:
     ```powershell
     docker run --rm `
       --add-host=host.docker.internal:host-gateway `
       -v "${PWD}:/workspace" `
       python:3.11-slim `
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-official.json --report-output /workspace/specmatic_test/official_report.md --host host.docker.internal"
     ```
3. Inspect the report at `specmatic_test/official_report.md`.

### 4. Run Validation against the Drifted Stripe Specification

To test drift detection, temporarily update `specmatic.yaml` — change the spec entry from `stripe-official.json` to `stripe-drifted.json` in the `dependencies` block — then:

1. Start the drifted mock server:
   ```bash
   specmatic mock --port 9000
   ```
2. Run the validation runner targeting the drifted spec:
   - **macOS / Linux (Bash/Zsh)**:
     ```bash
     docker run --rm \
       --add-host=host.docker.internal:host-gateway \
       -v "$(pwd):/workspace" \
       python:3.11-slim \
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-drifted.json --report-output /workspace/specmatic_test/drift_report.md --host host.docker.internal"
     ```
   - **Windows (PowerShell)**:
     ```powershell
     docker run --rm `
       --add-host=host.docker.internal:host-gateway `
       -v "${PWD}:/workspace" `
       python:3.11-slim `
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-drifted.json --report-output /workspace/specmatic_test/drift_report.md --host host.docker.internal"
     ```
3. Inspect the drift report at `specmatic_test/drift_report.md`.
4. Revert `specmatic.yaml` back to `stripe-official.json` when done.

## Converted Integration Tests (POC)

The integration test [test_accounts.py](file:///c:/Users/aryan/OneDrive/Documents/airbyte-master/airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_accounts.py) has been converted to use a local Specmatic mock server instead of static JSON mocks.

### How to Run Converted Tests

If you have `specmatic` installed on your host system path, the test suite will automatically handle pre-processing (flattening), starting the Specmatic mock server on port 9000, setting dynamic contract-validated expectations, running the connector, and shutting down the server.

To execute the test:

1. **Option A: From the repository root**
   - **Windows (PowerShell)**:
     ```powershell
     .\airbyte-integrations\connectors\source-stripe\unit_tests\.venv\Scripts\python.exe -m pytest -v airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_accounts.py
     ```
   - **macOS / Linux (Bash/Zsh)**:
     ```bash
     ./airbyte-integrations/connectors/source-stripe/unit_tests/.venv/bin/python -m pytest -v airbyte-integrations/connectors/source-stripe/unit_tests/integration/test_accounts.py
     ```

2. **Option B: From the `unit_tests` directory**
   - **Windows (PowerShell)**:
     ```powershell
     cd airbyte-integrations/connectors/source-stripe/unit_tests
     .\.venv\Scripts\python.exe -m pytest -v integration/test_accounts.py
     ```
   - **macOS / Linux (Bash/Zsh)**:
     ```bash
     cd airbyte-integrations/connectors/source-stripe/unit_tests
     ./.venv/bin/python -m pytest -v integration/test_accounts.py
     ```
