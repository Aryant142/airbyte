# Copyright (c) 2025 Airbyte, Inc., all rights reserved.

import argparse
import ast
import json
import os
import sys
from pathlib import Path

import jsonschema
import requests
import yaml
from jsonschema import Draft7Validator, RefResolver


# Setup search path so we can resolve conftest and other modules correctly
current_dir = Path(__file__).resolve().parent
connector_dir = current_dir.parent
sys.path.insert(0, str(connector_dir))
sys.path.insert(0, str(current_dir))

from conftest import get_source

from airbyte_cdk.models import SyncMode
from airbyte_cdk.test.catalog_builder import CatalogBuilder
from airbyte_cdk.test.entrypoint_wrapper import read


# Stream name to OpenAPI schema component name mapping
STREAM_MAPPING = {
    "customers": "customer",
    "charges": "charge",
    "invoices": "invoice",
    "payment_intents": "payment_intent",
    "products": "product",
    "prices": "price",
    "refunds": "refund",
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


def parse_stringified_fields(data):
    """
    Recursively attempts to parse string values that represent JSON arrays or
    objects (using ast.literal_eval) back into Python dictionaries or lists.
    This resolves type conflicts where the Airbyte CDK has serialized nested structures.
    """
    if isinstance(data, dict):
        parsed = {}
        for k, v in data.items():
            parsed[k] = parse_stringified_fields(v)
        return parsed
    elif isinstance(data, list):
        return [parse_stringified_fields(item) for item in data]
    elif isinstance(data, str):
        val = data.strip()
        if (val.startswith("{") and val.endswith("}")) or (val.startswith("[") and val.endswith("]")):
            try:
                parsed_val = ast.literal_eval(val)
                return parse_stringified_fields(parsed_val)
            except Exception:
                return data
    return data


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


def write_html_report(results, violations, overall_status, html_path):
    total = len(results)
    success_count = sum(1 for r in results.values() if r["status"] == "PASS")
    failed_count = total - success_count
    coverage_pct = int((success_count / total) * 100) if total > 0 else 0

    violations_dict = {stream: v for stream, v in violations}

    # Build HTML rows
    table_rows = ""
    for stream_name, r in results.items():
        status_class = "pass" if r["status"] == "PASS" else "fail"
        req_val = "Conforming" if r["request"] == "✅" else "Violated"
        resp_val = "Conforming" if r["response"] == "✅" else "Violated"
        req_icon = r["request"]
        resp_icon = r["response"]
        
        # Details action
        details_btn = ""
        details_row = ""
        if r["status"] != "PASS" and stream_name in violations_dict:
            details_btn = f'<button class="details-btn" onclick="toggleDetails(\'{stream_name}\')">View Details</button>'
            v_list = "".join([f"<li>{v}</li>" for v in violations_dict[stream_name]])
            details_row = f"""
            <tr id="details_{stream_name}" class="details-row" style="display: none;">
                <td colspan="5">
                    <div class="violations-box">
                        <h4>Violations for {stream_name}:</h4>
                        <ul>{v_list}</ul>
                    </div>
                </td>
            </tr>
            """
            
        table_rows += f"""
        <tr class="stream-row status-{status_class}">
            <td class="stream-name">{stream_name}</td>
            <td><span class="val-badge {r['request'] == '✅'}"><span class="icon">{req_icon}</span> {req_val}</span></td>
            <td><span class="val-badge {r['response'] == '✅'}"><span class="icon">{resp_icon}</span> {resp_val}</span></td>
            <td>{details_btn}</td>
            <td><span class="status-badge {status_class}">{r['status']}</span></td>
        </tr>
        {details_row}
        """

    # Build HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Specmatic & Airbyte Contract Test Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #8b5cf6;
            --primary-hover: #a78bfa;
            --success: #10b981;
            --success-bg: rgba(16, 185, 129, 0.1);
            --danger: #ef4444;
            --danger-bg: rgba(239, 68, 68, 0.1);
            --border-color: #334155;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            padding: 2rem 1.5rem;
            line-height: 1.5;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        /* Header Style */
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }}

        .logo-section {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .logo-icon {{
            background: linear-gradient(135deg, #6366f1, #a855f7);
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Outfit', sans-serif;
            font-weight: 800;
            font-size: 1.5rem;
            color: white;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
        }}

        h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.025em;
        }}

        .build-status {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            text-transform: uppercase;
            padding: 0.5rem 1rem;
            border-radius: 9999px;
        }}

        .build-status.PASS {{
            background-color: var(--success-bg);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .build-status.FAIL {{
            background-color: var(--danger-bg);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}

        /* Stats Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }}

        .stat-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
        }}

        .stat-card::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }}

        .stat-card.total::after {{ background-color: var(--primary); }}
        .stat-card.success::after {{ background-color: var(--success); }}
        .stat-card.failed::after {{ background-color: var(--danger); }}
        .stat-card.coverage::after {{ background: linear-gradient(to bottom, #6366f1, #a855f7); }}

        .stat-label {{
            font-size: 0.875rem;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 500;
            letter-spacing: 0.05em;
        }}

        .stat-value {{
            font-size: 2.25rem;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
            color: var(--text-main);
        }}

        /* Filters and Table */
        .content-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }}

        .filters-section {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            gap: 1rem;
            flex-wrap: wrap;
        }}

        .filter-buttons {{
            display: flex;
            gap: 0.5rem;
            background-color: var(--bg-color);
            padding: 0.25rem;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}

        .filter-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 0.5rem 1rem;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            border-radius: 6px;
            transition: all 0.2s;
        }}

        .filter-btn.active, .filter-btn:hover {{
            background-color: var(--card-bg);
            color: var(--text-main);
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }}

        .search-bar {{
            background-color: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.5rem 1rem;
            color: var(--text-main);
            font-size: 0.875rem;
            width: 250px;
            outline: none;
            transition: border-color 0.2s;
        }}

        .search-bar:focus {{
            border-color: var(--primary);
        }}

        /* Table Styling */
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}

        th {{
            color: var(--text-muted);
            font-weight: 500;
            font-size: 0.875rem;
            text-transform: uppercase;
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
            letter-spacing: 0.05em;
        }}

        td {{
            padding: 1.25rem 1rem;
            border-bottom: 1px solid var(--border-color);
            font-size: 0.95rem;
        }}

        .stream-name {{
            font-weight: 600;
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            font-size: 1.05rem;
        }}

        /* Badges */
        .val-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.85rem;
            font-weight: 500;
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
        }}

        .val-badge.True {{
            background-color: rgba(16, 185, 129, 0.05);
            color: var(--success);
        }}

        .val-badge.False {{
            background-color: rgba(239, 68, 68, 0.05);
            color: var(--danger);
        }}

        .status-badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .status-badge.pass {{
            background-color: var(--success-bg);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }}

        .status-badge.fail {{
            background-color: var(--danger-bg);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}

        /* Buttons & Collapsible details */
        .details-btn {{
            background-color: transparent;
            border: 1px solid var(--primary);
            color: var(--primary);
            padding: 0.4rem 0.8rem;
            font-size: 0.8rem;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .details-btn:hover {{
            background-color: var(--primary);
            color: white;
        }}

        .details-row td {{
            background-color: rgba(15, 23, 42, 0.4);
            padding: 1.5rem;
        }}

        .violations-box {{
            border-left: 3px solid var(--danger);
            padding-left: 1.5rem;
        }}

        .violations-box h4 {{
            margin-bottom: 0.75rem;
            color: var(--danger);
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
        }}

        .violations-box ul {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}

        .violations-box li {{
            color: #cbd5e1;
            font-size: 0.875rem;
            background-color: rgba(30, 41, 59, 0.8);
            padding: 0.75rem;
            border-radius: 8px;
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
            border: 1px solid var(--border-color);
        }}
    </style>
    <script>
        function filterResults(filter) {{
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            const activeBtn = document.querySelector('.filter-btn.' + filter);
            if (activeBtn) activeBtn.classList.add('active');

            const rows = document.querySelectorAll('.stream-row');
            rows.forEach(row => {{
                const streamName = row.querySelector('.stream-name').innerText;
                const detailsRow = document.getElementById('details_' + streamName);
                if (detailsRow) detailsRow.style.display = 'none';

                if (filter === 'all') {{
                    row.style.display = '';
                }} else if (filter === 'passed') {{
                    if (row.classList.contains('status-pass')) {{
                        row.style.display = '';
                    }} else {{
                        row.style.display = 'none';
                    }}
                }} else if (filter === 'failed') {{
                    if (row.classList.contains('status-fail')) {{
                        row.style.display = '';
                    }} else {{
                        row.style.display = 'none';
                    }}
                }}
            }});
        }}

        function toggleDetails(streamName) {{
            const detailsRow = document.getElementById('details_' + streamName);
            if (detailsRow) {{
                if (detailsRow.style.display === 'none') {{
                    detailsRow.style.display = '';
                }} else {{
                    detailsRow.style.display = 'none';
                }}
            }}
        }}

        function searchStreams() {{
            const query = document.getElementById('search').value.toLowerCase();
            const rows = document.querySelectorAll('.stream-row');
            rows.forEach(row => {{
                const name = row.querySelector('.stream-name').innerText.toLowerCase();
                const detailsRow = document.getElementById('details_' + name);
                if (detailsRow) detailsRow.style.display = 'none';

                if (name.includes(query)) {{
                    row.style.display = '';
                }} else {{
                    row.style.display = 'none';
                }}
            }});
        }}
    </script>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-section">
                <div class="logo-icon">S</div>
                <div>
                    <h1>Contract Test Report</h1>
                    <p style="color: var(--text-muted); font-size: 0.875rem; margin-top: 0.15rem;">Stripe OpenAPI validation summary</p>
                </div>
            </div>
            <div class="build-status {overall_status}">
                {overall_status}
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card total">
                <span class="stat-label">Total Streams</span>
                <span class="stat-value">{total}</span>
            </div>
            <div class="stat-card success">
                <span class="stat-label">Passed</span>
                <span class="stat-value">{success_count}</span>
            </div>
            <div class="stat-card failed">
                <span class="stat-label">Failed</span>
                <span class="stat-value">{failed_count}</span>
            </div>
            <div class="stat-card coverage">
                <span class="stat-label">Mock Coverage</span>
                <span class="stat-value">{coverage_pct}%</span>
            </div>
        </div>

        <div class="content-card">
            <div class="filters-section">
                <div class="filter-buttons">
                    <button class="filter-btn all active" onclick="filterResults('all')">All</button>
                    <button class="filter-btn passed" onclick="filterResults('passed')">Passed</button>
                    <button class="filter-btn failed" onclick="filterResults('failed')">Failed</button>
                </div>
                <input type="text" id="search" class="search-bar" placeholder="Search streams..." oninput="searchStreams()">
            </div>

            <table>
                <thead>
                    <tr>
                        <th style="width: 30%;">Stream</th>
                        <th style="width: 25%;">Request Validation</th>
                        <th style="width: 25%;">Response Validation</th>
                        <th style="width: 10%;">Details</th>
                        <th style="width: 10%;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Interactive HTML report generated at: {html_path}")


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

    config = {"client_secret": client_secret, "account_id": account_id, "url_base": f"{base_url}/"}

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

            # Extract and parse records from connector output to handle stringified sub-structures
            records = [parse_stringified_fields(msg.record.data) for msg in actual_messages.records]

            if not records:
                response_ok = False
                stream_violations.append("Response validation skipped: Connector returned no records.")
            else:
                print(f"Validating {len(records)} records from connector response against schema '{schema_name}'...")
                record_errors = []
                seen_errors = set()
                for record in records:
                    errors = validate_record(record, schema_name, spec)
                    for err in errors:
                        if err not in seen_errors:
                            seen_errors.add(err)
                            record_errors.append(err)
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
    
    # Generate companion HTML report
    html_report_path = str(Path(args.report_output).with_suffix(".html"))
    write_html_report(results, violations, overall_status, html_report_path)

    sys.exit(0 if overall_status == "PASS" else 1)


if __name__ == "__main__":
    main()
