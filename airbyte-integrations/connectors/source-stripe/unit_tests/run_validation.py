import os
import sys
import argparse
import json
import yaml
import jsonschema
from jsonschema import RefResolver, Draft7Validator
from pathlib import Path
import requests

# Setup search path so we can resolve conftest and other modules correctly
current_dir = Path(__file__).resolve().parent
connector_dir = current_dir.parent
sys.path.insert(0, str(connector_dir))
sys.path.insert(0, str(current_dir))

from conftest import get_source
from airbyte_cdk.test.catalog_builder import CatalogBuilder
from airbyte_cdk.models import SyncMode
from airbyte_cdk.test.entrypoint_wrapper import read

# Stream name to OpenAPI schema component name mapping
STREAM_MAPPING = {
    "customers": "customer",
    "charges": "charge",
    "invoices": "invoice",
    "payment_intents": "payment_intent",
    "products": "product",
    "prices": "price",
    "refunds": "refund"
}

def fix_openapi_schema(schema):
    """
    Recursively converts OpenAPI 3.0 schema features (like 'nullable: true')
    into standard JSON Schema Draft-7 format compatible with jsonschema library.
    """
    if not isinstance(schema, dict):
        return schema
    
    fixed = {}
    for k, v in schema.items():
        if k == "nullable" and v is True:
            pass
        elif isinstance(v, dict):
            fixed[k] = fix_openapi_schema(v)
        elif isinstance(v, list):
            fixed[k] = [fix_openapi_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            fixed[k] = v
            
    if schema.get("nullable") is True:
        if "type" in schema:
            t = schema["type"]
            if isinstance(t, list):
                if "null" not in t:
                    fixed["type"] = t + ["null"]
            else:
                fixed["type"] = [t, "null"]
        elif "anyOf" in schema:
            any_of = fixed.get("anyOf", [])
            if not any(isinstance(item, dict) and item.get("type") == "null" for item in any_of):
                fixed["anyOf"] = any_of + [{"type": "null"}]
        elif "oneOf" in schema:
            one_of = fixed.get("oneOf", [])
            if not any(isinstance(item, dict) and item.get("type") == "null" for item in one_of):
                fixed["oneOf"] = one_of + [{"type": "null"}]
            
    fixed.pop("nullable", None)
    fixed.pop("discriminator", None)
    fixed.pop("xml", None)
    fixed.pop("example", None)
    fixed.pop("externalDocs", None)
    
    return fixed

def validate_record(record_data, schema_name, spec):
    """
    Validates a record dictionary against the OpenAPI schema definition.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    if schema_name not in schemas:
        return [f"Schema '{schema_name}' not found in OpenAPI specification components."]
        
    schema = schemas[schema_name]
    resolver = RefResolver.from_schema(spec)
    validator = Draft7Validator(schema, resolver=resolver)
    
    errors = []
    for error in validator.iter_errors(record_data):
        path = ".".join([str(p) for p in error.path]) if error.path else "root"
        errors.append(f"Field '{path}': {error.message}")
    return errors

def main():
    parser = argparse.ArgumentParser(description="Validate Airbyte Stripe Connector against OpenAPI contract")
    parser.add_argument("--spec-path", required=True, help="Path to the Stripe OpenAPI spec file")
    parser.add_argument("--report-output", required=True, help="Path to save the markdown report")
    parser.add_argument("--port", type=int, default=9000, help="Port where Specmatic mock server is running")
    parser.add_argument("--host", default="127.0.0.1", help="Host where Specmatic mock server is running")
    args = parser.parse_args()

    # Load OpenAPI spec
    print(f"Loading OpenAPI specification from: {args.spec_path}")
    ext = Path(args.spec_path).suffix.lower()
    with open(args.spec_path, "r", encoding="utf-8") as f:
        if ext in (".json",):
            spec = json.load(f)
        else:
            spec = yaml.safe_load(f)

    # Fix the entire specification for Draft-7 JSON schema compatibility
    spec = fix_openapi_schema(spec)

    # Airbyte Stripe connector config values (simulated)
    client_secret = "sk_test_mock"
    account_id = "acct_mock"
    base_url = f"http://{args.host}:{args.port}/v1"

    config = {
        "client_secret": client_secret,
        "account_id": account_id,
        "url_base": f"{base_url}/"
    }

    results = {}
    violations = []

    for stream_name, schema_name in STREAM_MAPPING.items():
        print(f"\n========================================\nValidating Stream: {stream_name}\n========================================")
        
        request_ok = True
        response_ok = True
        stream_violations = []

        # Build configured catalog for this single stream
        catalog_builder = CatalogBuilder()
        catalog_builder.with_stream(name=stream_name, sync_mode=SyncMode.full_refresh)
        single_catalog = catalog_builder.build()

        try:
            print(f"Invoking Airbyte connector read for stream: '{stream_name}'...")
            source = get_source(config=config)
            actual_messages = read(source, config=config, catalog=single_catalog)
            print("HTTP request conforms to Specmatic contract (200 OK).")
            
            # Extract records from connector output
            records = [msg.record.data for msg in actual_messages.records]
            
            if not records:
                response_ok = False
                stream_violations.append("Response validation skipped: Connector returned no records.")
            else:
                print(f"Validating {len(records)} records from connector response against schema '{schema_name}'...")
                record_errors = []
                for record in records:
                    errors = validate_record(record, schema_name, spec)
                    if errors:
                        record_errors.extend(errors)
                        if len(record_errors) >= 10:
                            record_errors.append("...truncated additional record errors")
                            break
                if record_errors:
                    response_ok = False
                    for err in record_errors:
                        stream_violations.append(f"**Response Schema Mismatch**: {err}")
                        
        except Exception as e:
            request_ok = False
            response_ok = False
            
            # Check if this is an HTTP error with a response body (e.g. from Specmatic mock)
            err_text = ""
            if hasattr(e, "response") and e.response is not None:
                err_text = e.response.text
                
            if err_text:
                print(f"Connector request failed contract validation (400 Bad Request): {err_text}")
                stream_violations.append(f"**Request Error**: Specmatic mock server validation failed.\nDetail:\n```json\n{err_text}\n```")
            else:
                err_msg = str(e)
                print(f"Connector read failed: {err_msg}")
                stream_violations.append(f"**Connector Error**: {err_msg}")
                
        req_status = "✅" if request_ok else "❌"
        resp_status = "✅" if response_ok else "❌"
        status_text = "PASS" if (request_ok and response_ok) else "FAIL"
        
        results[stream_name] = {"request": req_status, "response": resp_status, "status": status_text}
        if stream_violations:
            violations.append((stream_name, stream_violations))

    # Generate Markdown Report
    print(f"\nWriting validation report to: {args.report_output}")
    os.makedirs(os.path.dirname(args.report_output), exist_ok=True)
    
    overall_status = "PASS"
    for r in results.values():
        if r["status"] == "FAIL":
            overall_status = "FAIL"
            break

    with open(args.report_output, "w", encoding="utf-8") as f:
        f.write("# Contract Validation Report\n\n")
        f.write(f"**Overall Build Status: {overall_status}**\n\n")
        
        f.write("## Streams Tested\n\n")
        f.write("| Stream | Request Validation | Response Schema Validation | Status |\n")
        f.write("| :--- | :---: | :---: | :---: |\n")
        for stream_name, r in results.items():
            f.write(f"| {stream_name} | {r['request']} | {r['response']} | **{r['status']}** |\n")
        f.write("\n")
        
        f.write("## Contract Violations\n\n")
        if not violations:
            f.write("✅ No contract violations or schema mismatches detected! All streams conform fully to the specification.\n")
        else:
            for stream_name, stream_v in violations:
                f.write(f"### Stream: `{stream_name}`\n")
                for v in stream_v:
                    f.write(f"- {v}\n")
                f.write("\n")
                
    print(f"Validation finished. Overall status: {overall_status}")
    sys.exit(0 if overall_status == "PASS" else 1)

if __name__ == "__main__":
    main()
