# Stripe Connector — OpenAPI Contract Validation & Specmatic Integration Tests

This directory contains the tools, OpenAPI specifications, and scripts to perform automated OpenAPI contract validation for the Airbyte Stripe source connector, and to run integration tests backed by a live Specmatic contract mock server.

> **Requires**: Node.js 18+, Python 3.11+, Docker, Specmatic v2.49.1+

---

## Architecture Overview

Specmatic is used in this repository for two primary testing workflows:

1. **Contract Validation Runner (`run_validation.py`)**: Runs full connector syncs, routing requests to the Specmatic mock server. Specmatic validates the connector's requests against the Stripe API contract and returns mocked records matching the OpenAPI response schema. The runner extracts these records and validates them against the schema components using Python's `jsonschema` library, outputting a markdown drift report.

2. **Migrated Integration Tests**: Integration tests migrated from `HttpMocker`/`requests-mock` to `SpecmaticIntegrationTestCase`. During the test class lifecycle, the Specmatic server starts automatically, dynamic contract-validated expectations are registered, the connector runs, and the server shuts down. Specmatic validates every incoming HTTP request against the Stripe OpenAPI specification.

---

## Before vs After: Integration Test Architecture

### ❌ Before — Old Workflow (HttpMocker / requests-mock)

```
 ┌────────────────────────────────────────┐
 │         Integration Test               │
 │         (e.g. test_events.py)          │
 │                                        │
 │   @HttpMocker()                        │
 │   def test_...(http_mocker):           │
 │       http_mocker.get(                 │
 │           _request().build(),          │
 │           _response().build()  ← ─ ─ ─│─ ─ Static JSON template (hardcoded)
 │       )                                │
 └───────────────┬────────────────────────┘
                 │ calls read()
                 ▼
 ┌────────────────────────────────────────┐
 │     Airbyte Stripe Connector           │
 │     (runs actual connector code)       │
 └───────────────┬────────────────────────┘
                 │ HTTP GET /v1/events?...
                 ▼
 ┌────────────────────────────────────────┐
 │     requests-mock (HttpMocker)         │
 │     intercepts at the Python layer     │
 │     returns hardcoded JSON body        │
 │                                        │
 │     ✗ No OpenAPI schema validation     │
 │     ✗ Static JSON, manual maintenance  │
 │     ✗ Contract drift goes undetected   │
 └───────────────┬────────────────────────┘
                 │ mocked response
                 ▼
 ┌────────────────────────────────────────┐
 │     Test Assertions                    │
 │     (record count, state, fields)      │
 └────────────────────────────────────────┘
```

**Characteristics:**
- Static JSON templates per endpoint
- No OpenAPI schema validation
- Manual maintenance as API evolves
- Contract drift goes undetected until production

---

### ✅ After — New Workflow (Specmatic Contract Mock)

```
 ┌──────────────────────────────────────────────────────────┐
 │   Stripe OpenAPI Specification (stripe-official.json)    │
 └───────────────────────────┬──────────────────────────────┘
                             │
                             ▼
 ┌──────────────────────────────────────────────────────────┐
 │   fix_spec.py  (runs automatically in setUpClass)        │
 │                                                          │
 │   • Injects missing endpoint paths                       │
 │   • Flattens deepObject params (created → created[gte])  │
 │   • Duplicates type → type[] and types[] for events      │
 │   • Adds payout / setup_intent query params              │
 │   • Prunes overly strict required[] constraints          │
 └───────────────────────────┬──────────────────────────────┘
                             │ Modified spec
                             ▼
 ┌──────────────────────────────────────────────────────────┐
 │   Specmatic Mock Server  (127.0.0.1:9000)                │
 │   • Started automatically in setUpClass                  │
 │   • Validates all requests against the OpenAPI spec      │
 │   • Returns contract-compliant mock responses            │
 │   • Terminated automatically in tearDownClass            │
 └────────────────┬───────────────────────────┬─────────────┘
                  │                           │
    POST /_specmatic/expectations       HTTP GET /v1/...
    (register dynamic stubs)           (real connector request)
                  │                           │
 ┌────────────────┴───────────────────────────┴─────────────┐
 │   SpecmaticIntegrationTestCase                           │
 │   (base class for all migrated tests)                    │
 │                                                          │
 │   1. set_specmatic_expectation(path, query, body)        │
 │   2. calls read() → connector runs                       │
 │   3. connector hits Specmatic → validated & stubbed      │
 │   4. assert output.records, state, fields                │
 └──────────────────────────────────────────────────────────┘
                             │
                             ▼
 ┌──────────────────────────────────────────────────────────┐
 │   Test Assertions                                        │
 │   (record count, pagination, stream state, field values) │
 │                                                          │
 │   ✓ OpenAPI contract validated on every request          │
 │   ✓ Dynamic stubs — no static JSON files                 │
 │   ✓ Schema changes automatically caught                  │
 │   ✓ Prevents contract drift                              │
 └──────────────────────────────────────────────────────────┘
```

**Characteristics:**
- Live OpenAPI contract validation on every request
- Dynamic stubs registered per-test — no static JSON templates
- Low maintenance: spec drives correctness, not hardcoded bodies
- Detects and prevents contract drift automatically

---

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

**10 of 16 integration test files migrated. All migrated tests pass.**

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
| `fix_spec.py` | Preprocesses the spec: flattens deepObject params, duplicates array params, injects missing paths, patches missing query params |
| `specmatic.yaml` | Specmatic configuration referencing the spec file |
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
   ```bash
   specmatic mock --port 9000
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
