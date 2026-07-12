# Copyright (c) 2025 Airbyte, Inc., all rights reserved.

import json
import os


def inject_list_endpoint(spec, path: str, schema_name: str, path_params: list = None, query_params: list = None) -> bool:
    """Injects a list-based GET endpoint into the specification paths if not already present."""
    if path not in spec.get("paths", {}):
        if query_params is None:
            query_params = ["limit", "starting_after"]

        parameters = []
        
        # Path parameters injection
        if path_params:
            for param_name in path_params:
                parameters.append({
                    "description": f"The identifier of the parent {param_name}.",
                    "in": "path",
                    "name": param_name,
                    "required": True,
                    "schema": {
                        "type": "string"
                    }
                })

        # Query parameters injection
        if "limit" in query_params:
            parameters.append({
                "description": "A limit on the number of objects to be returned.",
                "in": "query",
                "name": "limit",
                "required": False,
                "schema": {
                    "type": "integer"
                }
            })
        if "starting_after" in query_params:
            parameters.append({
                "description": "A cursor for use in pagination.",
                "in": "query",
                "name": "starting_after",
                "required": False,
                "schema": {
                    "type": "string"
                }
            })
        if "created" in query_params:
            parameters.append({
                "description": "Only return objects that were created during the given date interval.",
                "in": "query",
                "name": "created",
                "required": False,
                "style": "deepObject",
                "explode": True,
                "schema": {
                    "anyOf": [
                        {
                            "type": "integer"
                        },
                        {
                            "properties": {
                                "gt": {"type": "integer"},
                                "gte": {"type": "integer"},
                                "lt": {"type": "integer"},
                                "lte": {"type": "integer"}
                            },
                            "type": "object"
                        }
                    ]
                }
            })
        if "type" in query_params:
            parameters.append({
                "description": "Filter events by type.",
                "in": "query",
                "name": "type",
                "required": False,
                "schema": {
                    "type": "string"
                }
            })
        if "payout" in query_params:
            parameters.append({
                "description": "Only return balance transactions that were created for the given payout.",
                "in": "query",
                "name": "payout",
                "required": False,
                "schema": {
                    "type": "string"
                }
            })
        if "setup_intent" in query_params:
            parameters.append({
                "description": "Only return setup attempts created by the SetupIntent specified by this ID.",
                "in": "query",
                "name": "setup_intent",
                "required": False,
                "schema": {
                    "type": "string"
                }
            })

        # Sanitize operationId by removing dots and slashes
        op_id_base = schema_name.replace(".", "").replace("/", "").capitalize()
        sanitized_op_id = f"Get{op_id_base}s"

        spec["paths"][path] = {
            "get": {
                "description": f"Returns a list of {schema_name}s",
                "operationId": sanitized_op_id,
                "parameters": parameters,
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "data": {
                                            "items": {
                                                "$ref": f"#/components/schemas/{schema_name}"
                                            },
                                            "type": "array"
                                        },
                                        "has_more": {
                                            "type": "boolean"
                                        },
                                        "object": {
                                            "enum": [
                                                "list"
                                            ],
                                            "type": "string"
                                        },
                                        "url": {
                                            "type": "string"
                                        }
                                    },
                                    "required": [
                                        "data",
                                        "has_more",
                                        "object",
                                        "url"
                                    ],
                                    "type": "object"
                                }
                            }
                        },
                        "description": "Successful response."
                    }
                }
            }
        }
        print(f"Injected list endpoint {path} referencing components/schemas/{schema_name}.")
        return True
    return False


def patch_existing_endpoint_params(spec, path: str, query_params: list) -> bool:
    """Add any missing query parameters to an already-existing path in the spec."""
    if path not in spec.get("paths", {}):
        return False
    op = spec["paths"][path].get("get", {})
    existing_param_names = {p.get("name") for p in op.get("parameters", [])}
    added = False
    new_params = []
    if "payout" in query_params and "payout" not in existing_param_names:
        new_params.append({
            "description": "Only return balance transactions that were created for the given payout.",
            "in": "query",
            "name": "payout",
            "required": False,
            "schema": {"type": "string"}
        })
        added = True
    if "setup_intent" in query_params and "setup_intent" not in existing_param_names:
        new_params.append({
            "description": "Only return setup attempts created by the SetupIntent specified by this ID.",
            "in": "query",
            "name": "setup_intent",
            "required": False,
            "schema": {"type": "string"}
        })
        added = True
    if new_params:
        op.setdefault("parameters", []).extend(new_params)
        print(f"Patched existing path {path} with missing params: {[p['name'] for p in new_params]}")
    return added


INJECTED_ENDPOINTS = [
    {"path": "/v1/accounts", "schema_name": "account", "query_params": ["limit", "starting_after"]},
    {"path": "/v1/application_fees", "schema_name": "application_fee", "query_params": ["limit", "starting_after", "created"]},
    {"path": "/v1/issuing/authorizations", "schema_name": "issuing.authorization", "query_params": ["limit", "starting_after", "created"]},
    {"path": "/v1/issuing/cards", "schema_name": "issuing.card", "query_params": ["limit", "starting_after", "created"]},
    {"path": "/v1/radar/early_fraud_warnings", "schema_name": "radar.early_fraud_warning", "query_params": ["limit", "starting_after", "created"]},
    {"path": "/v1/events", "schema_name": "event", "query_params": ["limit", "starting_after", "created", "type"]},
    {"path": "/v1/balance_transactions", "schema_name": "balance_transaction", "query_params": ["limit", "starting_after", "created", "payout"]},
    {"path": "/v1/reviews", "schema_name": "review", "query_params": ["limit", "starting_after", "created"]},
    {"path": "/v1/setup_attempts", "schema_name": "setup_attempt", "query_params": ["limit", "starting_after", "created", "setup_intent"]},
    {"path": "/v1/setup_intents", "schema_name": "setup_intent", "query_params": ["limit", "starting_after", "created"]},
    {"path": "/v1/payouts", "schema_name": "payout", "query_params": ["limit", "starting_after", "created"]},
    {"path": "/v1/issuing/transactions", "schema_name": "issuing.transaction", "query_params": ["limit", "starting_after", "created"]},
    
    # Sub-resources with path parameters
    {"path": "/v1/application_fees/{id}/refunds", "schema_name": "fee_refund", "path_params": ["id"], "query_params": ["limit", "starting_after"]},
    {"path": "/v1/customers/{customer}/bank_accounts", "schema_name": "bank_account", "path_params": ["customer"], "query_params": ["limit", "starting_after"]},
    {"path": "/v1/customers/{customer}/payment_methods", "schema_name": "payment_method", "path_params": ["customer"], "query_params": ["limit", "starting_after"]},
    {"path": "/v1/accounts/{account}/external_accounts", "schema_name": "bank_account", "path_params": ["account"], "query_params": ["limit", "starting_after"]},
    {"path": "/v1/accounts/{account}/persons", "schema_name": "person", "path_params": ["account"], "query_params": ["limit", "starting_after"]}
]


def prune_required(obj):
    """Recursively prunes all required lists to only keep id and object."""
    if isinstance(obj, dict):
        if "required" in obj and isinstance(obj["required"], list):
            obj["required"] = [r for r in obj["required"] if r in ["id", "object"]]
        for k, v in obj.items():
            prune_required(v)
    elif isinstance(obj, list):
        for item in obj:
            prune_required(item)


def flatten_deep_objects(spec_path):
    print(f"Reading specification from {spec_path}...")
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    
    # Inject missing referenced schemas
    schemas_modified = False
    if "event" not in schemas:
        schemas["event"] = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "object": {"type": "string"},
                "created": {"type": "integer"},
                "type": {"type": "string"},
                "data": {"type": "object"}
            }
        }
        print("Injected event schema component.")
        schemas_modified = True
    if "radar.early_fraud_warning" not in schemas:
        schemas["radar.early_fraud_warning"] = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "object": {"type": "string"},
                "created": {"type": "integer"}
            }
        }
        print("Injected radar.early_fraud_warning schema component.")
        schemas_modified = True

    # Prune all strict required constraints
    prune_required(spec)

    # Declaratively inject all missing paths
    spec_modified = False
    for endpoint in INJECTED_ENDPOINTS:
        if inject_list_endpoint(
            spec,
            endpoint["path"],
            endpoint["schema_name"],
            endpoint.get("path_params"),
            endpoint.get("query_params")
        ):
            spec_modified = True
        else:
            # Path already exists — patch any missing query params
            if patch_existing_endpoint_params(spec, endpoint["path"], endpoint.get("query_params", [])):
                spec_modified = True

    modified_count = 0
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if not isinstance(op, dict) or "parameters" not in op:
                continue

            new_parameters = []
            for param in op["parameters"]:
                new_parameters.append(param)

                # Check for deepObject style query parameters
                if param.get("in") == "query" and param.get("style") == "deepObject":
                    name = param.get("name")
                    schema = param.get("schema", {})

                    # Extract properties to generate flat parameters for
                    properties = {}
                    if "properties" in schema:
                        properties = schema["properties"]
                    elif "anyOf" in schema:
                        for sub in schema["anyOf"]:
                            if sub.get("type") == "object" and "properties" in sub:
                                properties.update(sub["properties"])

                    if properties:
                        for prop_name, prop_schema in properties.items():
                            flat_name = f"{name}[{prop_name}]"
                            # Skip if parameter already exists
                            if any(p.get("name") == flat_name for p in op["parameters"]):
                                continue
                            print(
                                f"Flattening deepObject parameter '{name}' in {method.upper()} {path} with properties: {list(properties.keys())}"
                            )
                            flat_param = {
                                "name": flat_name,
                                "in": "query",
                                "required": False,
                                "schema": prop_schema,
                                "description": f"Flat query parameter representing {name}.{prop_name}",
                            }
                            new_parameters.append(flat_param)
                            modified_count += 1

                # Duplicate array query parameters (e.g. 'expand' to 'expand[]', 'type' to 'type[]' and 'types[]')
                if param.get("in") == "query":
                    name = param.get("name")
                    if name in ["expand", "type"]:
                        target_names = [f"{name}[]"]
                        if name == "type":
                            target_names.append("types[]")
                        for target_name in target_names:
                            # Skip if parameter already exists
                            if any(p.get("name") == target_name for p in op["parameters"]):
                                continue
                            print(f"Duplicating '{name}' parameter as '{target_name}' in {method.upper()} {path}")
                            dup_param = {
                                "name": target_name,
                                "in": "query",
                                "required": False,
                                "schema": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "description": f"Duplicated query parameter representing {name} array",
                            }
                            new_parameters.append(dup_param)
                            modified_count += 1

            op["parameters"] = new_parameters

    print(f"Writing updated specification back to {spec_path} (added {modified_count} flat parameters, modified=True)...")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)


if __name__ == "__main__":
    flatten_deep_objects("specmatic_test/specs/stripe-official.json")
    flatten_deep_objects("specmatic_test/specs/stripe-drifted.json")
