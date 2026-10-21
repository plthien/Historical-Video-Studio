"""Generate structural Python/TypeScript contract views from frozen 12 JSON Schemas and both OpenAPI files.

Build-generated policy: outputs are ignored by Git; CI compiles them, verifies
semantics and tests that --check detects stale/missing files without rewriting.
JSON Schema plus the existing semantic validators remain the runtime authority.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts/schema"
OUT_PY = ROOT / "backend/app/contracts/generated.py"
OUT_TS = ROOT / "frontend/src/api/generated/contracts.ts"


def identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return ("_" if cleaned[0].isdigit() else "") + cleaned


def reference(value: str) -> str:
    prefix = "#/components/schemas/"
    if value.startswith(prefix):
        return "Api" + identifier(value[len(prefix):])
    if value.startswith("./schema/") and value.endswith(".schema.json"):
        return identifier(value.split("/")[-1].removesuffix(".schema.json").replace(".", "_"))
    raise ValueError(f"Unsupported schema reference: {value}")


def emit_type(node: dict, name: str, lang: str, declarations: list[str]) -> str:
    if "$ref" in node:
        return reference(node["$ref"])
    if "const" in node:
        return f"Literal[{node['const']!r}]" if lang == "py" else json.dumps(node["const"])
    if "enum" in node:
        values = node["enum"]
        return ("Literal[" + ", ".join(repr(x) for x in values) + "]") if lang == "py" else " | ".join(json.dumps(x) for x in values)
    for key in ("oneOf", "anyOf"):
        if key in node:
            variants = [emit_type(n, name + f"Alt{i}", lang, declarations) for i, n in enumerate(node[key])]
            return ("Union[" + ", ".join(variants) + "]") if lang == "py" else " | ".join(f"({x})" for x in variants)
    t = node.get("type")
    if isinstance(t, list):
        variants = [emit_type({"type": item}, name, lang, declarations) for item in t]
        return ("Union[" + ", ".join(variants) + "]") if lang == "py" else " | ".join(variants)
    if t == "array":
        if "prefixItems" in node:
            entries = node["prefixItems"]
            if node.get("minItems") != len(entries) or node.get("maxItems") != len(entries):
                raise ValueError(f"Unsupported variable-length prefixItems: {name}")
            members = [emit_type(entry, name + f"Tuple{i}", lang, declarations) for i, entry in enumerate(entries)]
            return "tuple[" + ", ".join(members) + "]" if lang == "py" else "[" + ", ".join(members) + "]"
        member = emit_type(node.get("items", {}), name + "Item", lang, declarations)
        return f"list[{member}]" if lang == "py" else f"Array<{member}>"
    if t == "object" or "properties" in node:
        fields = node.get("properties", {})
        extra = node.get("additionalProperties", False)
        if not fields and isinstance(extra, dict):
            member = emit_type(extra, name + "Value", lang, declarations)
            return f"dict[str, {member}]" if lang == "py" else f"Record<string, {member}>"
        required = set(node.get("required", []))
        lines = [f"class {name}(TypedDict):"] if lang == "py" else [f"export interface {name} {{"]
        for key, child in fields.items():
            field_type = emit_type(child, name + identifier(key).title(), lang, declarations)
            if lang == "py":
                if not key.isidentifier():
                    raise ValueError(f"Unsupported Python contract field: {key}")
                lines.append(f"    {key}: {'Required' if key in required else 'NotRequired'}[{field_type}]")
            else:
                lines.append(f'  {json.dumps(key)}{" " if key in required else "?"}: {field_type};')
        if lang == "py" and not fields:
            lines.append("    pass")
        if lang == "ts":
            if isinstance(extra, dict):
                # Properties and dictionary additions must share compatible value types.
                member = emit_type(extra, name + "Additional", lang, declarations)
                lines.append(f"  [key: string]: {member};")
            lines.append("}")
        declarations.append("\n".join(lines))
        return name
    mapping = ({"integer": "int", "number": "float", "string": "str", "boolean": "bool", "null": "None"}
               if lang == "py" else
               {"integer": "number", "number": "number", "string": "string", "boolean": "boolean", "null": "null"})
    if t is None and not node:  # truly unconstrained schema only
        return "Any" if lang == "py" else "unknown"
    if t not in mapping:
        raise ValueError(f"Unsupported concrete schema node {name}: {node}")
    return mapping[t]


def collect_openapi():
    base = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
    extension = json.loads((ROOT / "contracts/openapi-fullflow-extension.json").read_text(encoding="utf-8"))
    # A3 adds scoped Europeana hydration and SHA-verified original preview.
    if len(extension["paths"]) != 30:
        raise ValueError("Expected exactly 30 fullflow extension paths")
    schemas = {}
    for source in (base, extension):
        for key, value in source.get("components", {}).get("schemas", {}).items():
            if key in schemas:
                raise ValueError(f"Duplicate API component {key}")
            schemas[key] = value
    operations, requests = {}, {}
    for source in (base, extension):
        for path, verbs in source["paths"].items():
            for verb, operation in verbs.items():
                if verb.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                key = verb.upper() + " " + path
                op_id = operation.get("operationId") or key
                if key in operations or op_id in operations.values():
                    raise ValueError(f"Duplicate API operation: {key} ({op_id})")
                operations[key] = op_id
                body = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
                if body:
                    requests[op_id] = body
    return schemas, dict(sorted(operations.items())), dict(sorted(requests.items()))


def generate() -> tuple[str, str]:
    contracts = sorted(SCHEMAS.glob("*.schema.json"))
    if len(contracts) != 12:
        raise ValueError(f"Expected 12 canonical schema files; found {len(contracts)}")
    api_schemas, operations, request_schemas = collect_openapi()
    outputs = []
    for lang in ("py", "ts"):
        declarations = []
        for path in contracts:
            name = identifier(path.name.removesuffix(".schema.json").replace(".", "_"))
            emit_type(json.loads(path.read_text(encoding="utf-8")), name, lang, declarations)
        for name, node in sorted(api_schemas.items()):
            emit_type(node, "Api" + identifier(name), lang, declarations)
        body_types = {}
        for op_id, schema in request_schemas.items():
            body_types[op_id] = emit_type(schema, "ApiRequest" + identifier(op_id), lang, declarations)
        if lang == "py":
            content = "from __future__ import annotations\nfrom typing import Any, Literal, Required, NotRequired, TypedDict, Union\n\n"
            content += "\n\n".join(declarations) + "\n\n"
            content += "API_OPERATIONS = " + repr(operations) + "\n"
            content += "API_REQUEST_MODELS = {\n" + "".join(f"    {op_id!r}: {model},\n" for op_id, model in body_types.items()) + "}\n"
        else:
            content = "// Build-generated from 12 JSON Schemas and both OpenAPI contracts. Do not edit.\n"
            content += "\n\n".join(declarations) + "\n\n"
            content += "export const API_OPERATIONS = " + json.dumps(operations, indent=2) + " as const;\n"
            content += "export interface APIRequestBodies {\n"
            content += "".join(f"  {json.dumps(op_id)}: {model};\n" for op_id, model in body_types.items())
            content += "}\n"
        outputs.append(content)
    return tuple(outputs)


def verify_artifacts(paths: tuple[Path, Path], generated: tuple[str, str]) -> None:
    for path, content in zip(paths, generated):
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"STALE GENERATED TYPES: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out-py", type=Path, default=OUT_PY)
    parser.add_argument("--out-ts", type=Path, default=OUT_TS)
    args = parser.parse_args()
    paths = (args.out_py, args.out_ts)
    generated = generate()
    if args.check:
        verify_artifacts(paths, generated)  # read-only, does not repair broken outputs
    else:
        for path, content in zip(paths, generated):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    print("12 canonical schema + core/extension OpenAPI types: PASS")


if __name__ == "__main__":
    main()
