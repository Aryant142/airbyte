# Copyright (c) 2025 Airbyte, Inc., all rights reserved.

import json
import os


def flatten_deep_objects(spec_path):
    print(f"Reading specification from {spec_path}...")
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

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

    if modified_count > 0:
        print(f"Writing updated specification back to {spec_path} (added {modified_count} flat parameters)...")
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)
    else:
        print("No deepObject parameters required flattening.")


if __name__ == "__main__":
    flatten_deep_objects("specmatic_test/specs/stripe-official.json")
    flatten_deep_objects("specmatic_test/specs/stripe-drifted.json")
