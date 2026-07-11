# Copyright (c) 2025 Airbyte, Inc., all rights reserved.

import json
import os


def inject_list_endpoint(spec, path: str, schema_name: str, query_params: list = None) -> bool:
    """Injects a list-based GET endpoint into the specification paths if not already present."""
    if path not in spec.get("paths", {}):
        if query_params is None:
            query_params = ["limit", "starting_after"]

        parameters = []
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

        # Sanitize operationId by removing dots
        sanitized_op_id = f"Get{schema_name.replace('.', '').capitalize()}s"

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


# Declarative configuration list of missing Stripe endpoints to inject
INJECTED_ENDPOINTS = [
    {
        "path": "/v1/accounts",
        "schema_name": "account",
        "query_params": ["limit", "starting_after"]
    }
]


def flatten_deep_objects(spec_path):
    print(f"Reading specification from {spec_path}...")
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    # Declaratively inject all missing paths
    spec_modified = False
    for endpoint in INJECTED_ENDPOINTS:
        if inject_list_endpoint(spec, endpoint["path"], endpoint["schema_name"], endpoint.get("query_params")):
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
                        print(
                            f"Flattening deepObject parameter '{name}' in {method.upper()} {path} with properties: {list(properties.keys())}"
                        )
                        for prop_name, prop_schema in properties.items():
                            flat_name = f"{name}[{prop_name}]"
                            flat_param = {
                                "name": flat_name,
                                "in": "query",
                                "required": False,
                                "schema": prop_schema,
                                "description": f"Flat query parameter representing {name}.{prop_name}",
                            }
                            new_parameters.append(flat_param)
                            modified_count += 1

                # Duplicate 'expand' query parameter as 'expand[]' for array parameters
                if param.get("in") == "query" and param.get("name") == "expand":
                    print(f"Duplicating 'expand' parameter as 'expand[]' in {method.upper()} {path}")
                    flat_param = {
                        "name": "expand[]",
                        "in": "query",
                        "required": False,
                        "schema": param.get("schema", {}),
                        "description": "Flat query parameter representing expand array",
                    }
                    new_parameters.append(flat_param)
                    modified_count += 1

            op["parameters"] = new_parameters

    if modified_count > 0 or spec_modified:
        print(f"Writing updated specification back to {spec_path} (added {modified_count} flat parameters, modified={spec_modified})...")
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)
    else:
        print("No deepObject parameters required flattening and all specified paths are already present.")


if __name__ == "__main__":
    flatten_deep_objects("specmatic_test/specs/stripe-official.json")
    flatten_deep_objects("specmatic_test/specs/stripe-drifted.json")
