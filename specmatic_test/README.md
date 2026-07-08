# Stripe Connector OpenAPI Contract Validation

This directory contains the tools, OpenAPI specifications, and scripts to perform automated OpenAPI contract validation for the Airbyte Stripe source connector.

> **Requires**: Node.js 18+, Python 3.11+, Docker, Specmatic v2.49.1+

## Architecture Overview

Instead of just checking if the connector runs successfully, we run the actual Airbyte Stripe connector, routing its HTTP request traffic to a **Specmatic Mock Server** loaded with the Stripe OpenAPI specification. Specmatic validates that the requests sent by the connector conform to the Stripe API contract, and then returns mocked records matching the OpenAPI response schema. These returned records are then validated against the schema components using python's `jsonschema` library.

```
+---------------------------+       HTTP Requests       +-----------------------+
|  Airbyte Stripe Connector | ------------------------> | Specmatic Mock Server |
|  (runs actual code)       | <------------------------ | (validates request &  |
+---------------------------+      Mocked Responses     |  mock schema content) |
              |                                         +-----------------------+
              | (extracts records)                                  ^
              v                                                     |
+---------------------------+                                       |
|  JSON Schema Validator    | --------------------------------------+
|  (evaluates record format)| (references Stripe OpenAPI spec schemas)
+---------------------------+
```

## Setup & Files

- `specs/stripe-official.json`: Pruned official Stripe OpenAPI specification containing the endpoints under test (`/v1/customers`, `/v1/charges`, `/v1/invoices`, `/v1/payment_intents`, `/v1/products`, `/v1/prices`, `/v1/refunds`).
- `specs/stripe-drifted.json`: A modified Stripe specification containing drifted properties and types to simulate API drift and verify validation failures.
- `fix_spec.py`: Python utility that automatically flattens deepObject parameters (such as `created[gte]`) and duplicates array parameters (such as `expand[]`) to work around Specmatic exact-match limits on array and object query parameters.
- `run_validation.py` (located in the connector's `unit_tests` directory): The test runner that instantiates the actual connector sources, executes incremental reads via `airbyte_cdk.test.entrypoint_wrapper.read`, processes response records, and writes validation reports.
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
   ```bash
   docker run --rm \
     --add-host=host.docker.internal:host-gateway \
     -v "${PWD}:/workspace" \
     python:3.11-slim \
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
   ```bash
   docker run --rm \
     --add-host=host.docker.internal:host-gateway \
     -v "${PWD}:/workspace" \
     python:3.11-slim \
     sh -c "pip install pytest freezegun pytest-mock requests-mock mock airbyte-cdk==6.61.6 requests pyyaml jsonschema && python /workspace/airbyte-integrations/connectors/source-stripe/unit_tests/run_validation.py --spec-path /workspace/specmatic_test/specs/stripe-drifted.json --report-output /workspace/specmatic_test/drift_report.md --host host.docker.internal"
   ```
3. Inspect the drift report at `specmatic_test/drift_report.md`.
4. Revert `specmatic.yaml` back to `stripe-official.json` when done.
