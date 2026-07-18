# Stripe Connector — OpenAPI Contract Validation & Specmatic Integration Tests

This directory contains the tools, OpenAPI specifications, and scripts required to perform **automated OpenAPI contract validation** for the Airbyte Stripe source connector and to run **contract-driven integration tests** using a live **Specmatic** mock server.

> **Requirements**
>
> - Node.js 18+
> - Python 3.11+
> - Docker
> - Specmatic v2.49.1+

---

# Why?

The Stripe connector originally relied on **HttpMocker** and **requests-mock**, where every integration test used manually maintained JSON responses.

This approach introduced several limitations:

- Static mock responses become outdated as the Stripe API evolves.
- Contract drift between the connector and Stripe's API is difficult to detect.
- Mock responses require continuous manual maintenance.
- HTTP requests are not validated against the official OpenAPI contract.

This project introduces **[Specmatic](https://specmatic.io/)** to enable **contract-driven integration testing**, ensuring that both requests and responses conform to the Stripe OpenAPI specification.

---

# What Was Implemented?

## 1. OpenAPI Contract Validation

A dedicated validation runner executes the Stripe connector against a **Specmatic Mock Server**.

During execution, Specmatic validates:

- Outgoing connector requests
- Query parameters
- Response schemas
- Overall API contract compliance

```text
  Airbyte Connector
        │
        ▼
Specmatic Mock Server
        │
        ▼
Stripe OpenAPI Specification
        │
        ▼
Validation Report
```

After validation, the runner generates a **Contract Drift Report**, highlighting any deviations from the official Stripe OpenAPI specification.

---

## 2. Specmatic-backed Integration Tests

Integration tests have been migrated from static **HttpMocker**-based mocks to **Specmatic**.

### Before

Instead of relying on hardcoded JSON files:

```text
HttpMocker
      │
      ▼
accounts.json
```

### After

Tests now communicate with a live **Specmatic Mock Server** generated from the Stripe OpenAPI specification.

```text
Stripe OpenAPI Specification
          │
          ▼
     fix_spec.py
          │
          ▼
 Modified OpenAPI Specification
          │
          ▼
 Specmatic Mock Server
          │
          ▼
 Airbyte Stripe Connector
          │
          ▼
 Test Assertions
```

Every HTTP request sent by the connector is validated against the OpenAPI specification before Specmatic returns a contract-compliant response.

This significantly reduces mock maintenance while automatically detecting contract drift during integration testing.

## Migration Status

| Batch | Files | Status |
|---|---|---|
| **Batch 1** — Base Issuing, Risk & Fee streams | `test_application_fees.py` | ✅ Migrated |
| | `test_authorizations.py` | ✅ Migrated |
| | `test_cards.py` | ✅ Migrated |
| | `test_early_fraud_warnings.py` | ✅ Migrated |
| | `test_events.py` | ✅ Migrated |
| **Batch 2** — Standard Payment & Balance streams | `test_payment_methods.py` | ✅ Migrated |
| | `test_payout_balance_transactions.py` | ✅ Migrated |
| | `test_reviews.py` | ✅ Migrated |
| | `test_setup_attempts.py` | ✅ Migrated |
| | `test_transactions.py` | ✅ Migrated |
| **POC** | `test_accounts.py` | ✅ Migrated (original POC) |

** All migrated tests pass.**

---

## Key Migration Patterns

### 1. Standard stream expectation
```python
self.set_specmatic_expectation(
    path="/v1/application_fees",
    query={
        "created[gte]": str(int(start_date.timestamp())),
        "created[lte]": str(int(now.timestamp())),
        "limit": "100"
    },
    response_body={
        "object": "list",
        "url": "/v1/application_fees",
        "has_more": False,
        "data": [{"id": "fee_1", "object": "application_fee", "created": ...}]
    }
)
```

### 2. Event types — single wildcard vs multi-value
```python
# Single wildcard (e.g. payment_method.*):
query={"type": "payment_method.*", ...}

# Multiple types (e.g. reviews, transactions):
query={"types[]": ["review.closed", "review.opened"], ...}
```

### 3. Error / retry tests — bypass Specmatic with requests_mock
```python
with requests_mock.Mocker(real_http=True) as m:
    m.register_uri("GET", url, status_code=429)
    m.register_uri("GET", url, status_code=200, json={...})
    output = self._read(config)
```

### 4. Parent-child streams
```python
# Register parent first
self.set_specmatic_expectation(path="/v1/payouts", query={...}, response_body={...})

# Then child per parent ID
self.set_specmatic_expectation(
    path="/v1/balance_transactions",
    query={"payout": "a_payout_id", "limit": "100"},
    response_body={...}
)
```

---

## Setup & Files

| File | Description |
|---|---|
| `specs/stripe-official.json` | Preprocessed official Stripe OpenAPI spec used by the Specmatic mock server |
| `specs/stripe-drifted.json` | Modified spec with intentional drift — used to verify contract violation detection |
| `specs/stripe-accounts-contract.json` | Minimal contract spec covering only the `GET /v1/accounts` endpoint |
| `specs/stripe-accounts-contract_examples/` | Directory containing externalized mock test examples (`success.json`, `bad_limit.json`, `no_auth.json`) |
| `specs/stripe-accounts-contract_dictionary.yaml` | Domain-specific dictionary specifying real-world mock data templates (e.g. `acct_` IDs, custom domains) for generative tests |
| `fix_spec.py` | Preprocesses the spec: flattens deepObject params, duplicates array params, injects missing paths, patches missing query params, and filters paths based on whitelisted streams |
| `specmatic.yaml` | Specmatic configuration referencing the spec file for MOCK mode |
| `specmatic-accounts-test.yaml` | Specmatic configuration referencing the accounts spec file for TEST mode |
| `accounts_stub_server.py` | HTTP stub server that acts as a target for Specmatic TEST mode contract verification |
| `run_contract_test.ps1` | Orchestrates starting the accounts stub server, running Specmatic tests, and generating reports |
| `docker-compose.yml` | Container orchestrator config to run the stub server, mock server, and test runner in a clean, unified sandbox |
| `official_report.md` | Output of the contract validation runner against the official spec |
| `drift_report.md` | Output of the contract validation runner against the drifted spec |

| Test Infrastructure | Location |
|---|---|
| `SpecmaticIntegrationTestCase` | `unit_tests/specmatic/base_test.py` |
| Specmatic server manager | `unit_tests/specmatic/server.py` |
| Migration validation runner | `unit_tests/run_validation.py` |

---

## How to Run Integration Tests Locally

### Prerequisites

```bash
npm install -g specmatic@2.49.1
```

### Run a single migrated test file

**Windows (PowerShell) — from `unit_tests/` directory:**
```powershell
cd airbyte-integrations/connectors/source-stripe/unit_tests
.\.venv\Scripts\python.exe -m pytest -v integration/test_events.py
```

**macOS / Linux — from `unit_tests/` directory:**
```bash
cd airbyte-integrations/connectors/source-stripe/unit_tests
./.venv/bin/python -m pytest -v integration/test_events.py
```

### Run all migrated Batch 1 + Batch 2 tests

**Windows (PowerShell):**
```powershell
cd airbyte-integrations/connectors/source-stripe/unit_tests
.\.venv\Scripts\python.exe -m pytest -v `
  integration/test_accounts.py `
  integration/test_application_fees.py `
  integration/test_authorizations.py `
  integration/test_cards.py `
  integration/test_early_fraud_warnings.py `
  integration/test_events.py `
  integration/test_payment_methods.py `
  integration/test_payout_balance_transactions.py `
  integration/test_reviews.py `
  integration/test_setup_attempts.py `
  integration/test_transactions.py
```

**macOS / Linux:**
```bash
cd airbyte-integrations/connectors/source-stripe/unit_tests
./.venv/bin/python -m pytest -v \
  integration/test_accounts.py \
  integration/test_application_fees.py \
  integration/test_authorizations.py \
  integration/test_cards.py \
  integration/test_early_fraud_warnings.py \
  integration/test_events.py \
  integration/test_payment_methods.py \
  integration/test_payout_balance_transactions.py \
  integration/test_reviews.py \
  integration/test_setup_attempts.py \
  integration/test_transactions.py
```

---

## How to Run Contract Validation Locally

### 1. Preprocess the spec

```bash
python specmatic_test/fix_spec.py
```

### 2. Run against the Official Stripe Specification

1. Start the Specmatic mock server from the repo root:

   **Using Specmatic CLI (Direct):**
   ```bash
   specmatic mock --port 9000
   ```

   **Using Docker Compose:**
   ```bash
   docker compose -f specmatic_test/docker-compose.yml up specmatic-mock
   ```
2. Run the validation runner:
   - **macOS / Linux:**
     ```bash
     docker run --rm \
       --add-host=host.docker.internal:host-gateway \
       -v "$(pwd):/workspace" \
       python:3.11-slim \
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-official.json --report-output /workspace/specmatic_test/official_report.md --host host.docker.internal"
     ```
   - **Windows (PowerShell):**
     ```powershell
     docker run --rm `
       --add-host=host.docker.internal:host-gateway `
       -v "${PWD}:/workspace" `
       python:3.11-slim `
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-official.json --report-output /workspace/specmatic_test/official_report.md --host host.docker.internal"
     ```
3. Inspect the report at `specmatic_test/official_report.md`.

### 3. Run against the Drifted Stripe Specification

To test drift detection, update `specmatic.yaml` to reference `stripe-drifted.json`, then:

1. Start the drifted mock server:
   ```bash
   specmatic mock --port 9000
   ```
2. Run the validation runner targeting the drifted spec:
   - **macOS / Linux:**
     ```bash
     docker run --rm \
       --add-host=host.docker.internal:host-gateway \
       -v "$(pwd):/workspace" \
       python:3.11-slim \
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-drifted.json --report-output /workspace/specmatic_test/drift_report.md --host host.docker.internal"
     ```
   - **Windows (PowerShell):**
     ```powershell
     docker run --rm `
       --add-host=host.docker.internal:host-gateway `
       -v "${PWD}:/workspace" `
       python:3.11-slim `
       sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-drifted.json --report-output /workspace/specmatic_test/drift_report.md --host host.docker.internal"
     ```
3. Inspect the drift report at `specmatic_test/drift_report.md`.
4. Revert `specmatic.yaml` back to `stripe-official.json` when done.

### 4. Validate Specification and Examples Locally

To validate that inline or external examples and the API specification conform to OpenAPI schemas, run Specmatic's built-in validation command:

```bash
specmatic examples validate --lenient --spec-file specmatic_test/specs/stripe-official.json
```

> [!NOTE]
> The `--lenient` flag is required because the official Stripe specification contains duplicate query parameter entries which otherwise cause strict parser validation to fail.

---

## How to Run Accounts Contract Tests (TEST Mode) Locally

This runs Specmatic in **TEST mode** where Specmatic acts as a test client that auto-generates requests from the OpenAPI contract, fires them at a local target server (our Python stub server), and verifies the response schemas and examples.

### 1. Start the accounts stub server:
```bash
python specmatic_test/accounts_stub_server.py --port 3000
```

### 2. Run the Specmatic contract tests:
From the repository root:

**Using Specmatic CLI (Direct):**
```bash
specmatic test --host=127.0.0.1 --port=3000 --config=specmatic-accounts-test.yaml
```

**Using Docker (Windows/PowerShell):**
```powershell
.\run_contract_test.ps1
```

**Using Docker (macOS / Linux):**
```bash
docker run --rm \
  -v "$(pwd):/usr/src/app" \
  -v "$HOME/.specmatic:/root/.specmatic" \
  -w /usr/src/app \
  specmatic/specmatic:2.49.1 test \
  --host=host.docker.internal --port=3000 \
  --config specmatic-accounts-test.yaml \
  --timeout=30
```

**Using Docker Compose (Cross-Platform):**
```bash
# Automatically starts the accounts stub server, waits for its health check,
# runs the Specmatic contract tests, and exits.
docker compose -f specmatic_test/docker-compose.yml up specmatic-test --exit-code-from specmatic-test
```

### 3. View the generated reports:
*   HTML report: `build/reports/specmatic/accounts/test/html/index.html`
*   JSON summary: `build/reports/specmatic/accounts/ctrf-report.json`
