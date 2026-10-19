"""Generate versioned Python TypedDict views and TypeScript structures from frozen JSON Schemas.

Only data shape is generated. Runtime validation must use canonical JSON Schema + existing
semantic validators. Use --check in CI to reject stale generated code.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts/schema"
OUT_PY = ROOT / "backend/app/contracts/generated.py"
OUT_TS = ROOT / "frontend/src/api/generated/contracts.ts"


def identifier(s: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", s)
    return ("_" if cleaned[0].isdigit() else "") + cleaned


def types(node: dict, name: str, language: str, declarations: list[str]) -> str:
    if "$ref" in node:
        return identifier(node["$ref"].split("/")[-1].replace(".schema.json", "").replace(".", "_"))
    if "const" in node:
        return ("Literal[" + repr(node["const"]) + "]" if language == "py" else json.dumps(node["const"]))
    if "enum" in node:
        variants = node["enum"]
        if language == "py":
            return "Literal[" + ", ".join(repr(x) for x in variants) + "]"
        return " | ".join(json.dumps(x) for x in variants)
    if "oneOf" in node or "anyOf" in node:
        variants = node.get("oneOf", node.get("anyOf"))
        ts = [types(x, name + "Alt" + str(i), language, declarations) for i, x in enumerate(variants)]
        return ("Union[" + ", ".join(ts) + "]" if language == "py" else " | ".join(f"({x})" for x in ts))
    t = node.get("type")
    if isinstance(t, list):
        return ("Union[" + ", ".join(types({"type":x}, name, language, declarations) for x in t) + "]"
                if language == "py" else " | ".join(types({"type":x}, name, language, declarations) for x in t))
    if t == "object" or "properties" in node:
        fields = node.get("properties", {})
        required = set(node.get("required", []))
        if language == "py":
            lines = ["class " + name + "(TypedDict):"]
            lines += [f"    {identifier(key)}: {'Required' if key in required else 'NotRequired'}[{types(value, name+identifier(key).title(), language, declarations)}]" for key, value in fields.items()]
            if not fields:
                lines.append("    pass")
            declarations.append("\n".join(lines))
        else:
            lines = ["export interface " + name + " {"]
            lines += [f"  {json.dumps(key)}{' ' if key in required else '?'}: {types(value, name+identifier(key).title(), language, declarations)};" for key, value in fields.items()]
            if node.get("additionalProperties") not in (False, None):
                lines.append("  [key: string]: unknown;")
            lines.append("}")
            declarations.append("\n".join(lines))
        return name
    if t == "array":
        inner = types(node.get("items", {}), name + "Item", language, declarations)
        return f"list[{inner}]" if language == "py" else f"Array<{inner}>"
    if language == "py":
        return {"integer":"int","number":"float","boolean":"bool","string":"str","null":"None"}.get(t,"Any")
    return {"integer":"number","number":"number","boolean":"boolean","string":"string","null":"null"}.get(t,"unknown")


def generate() -> tuple[str, str]:
    schemas = sorted(SCHEMAS.glob("*.schema.json"))
    results = []
    for language in ("py","ts"):
        declarations = []
        for path in schemas:
            name = identifier(path.name.replace(".schema.json", "").replace(".", "_"))
            types(json.loads(path.read_text(encoding="utf-8")), name, language, declarations)
        # OpenAPI core plus extension: operation names and methods are generated together.
        import yaml
        base = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
        ext = json.loads((ROOT / "contracts/openapi-fullflow-extension.json").read_text(encoding="utf-8"))
        operations = {}
        for source in (base,ext):
            for path, verbs in source["paths"].items():
                for verb, value in verbs.items():
                    if verb.lower() not in ("get","post","put","patch","delete"):
                        continue
                    key = verb.upper()+" "+path
                    if key in operations:
                        raise ValueError(f"Duplicate OpenAPI route {key}")
                    operations[key] = value.get("operationId") or key
        if len(ext["paths"]) != 26:
            raise ValueError("Expected 26 additive OpenAPI paths")
        if language == "py":
            content = "from __future__ import annotations\nfrom typing import Any, Literal, Required, NotRequired, TypedDict, Union\n\n"
            content += "\n\n".join(reversed(declarations)) + "\n"
            content += "\nAPI_OPERATIONS = " + repr(dict(sorted(operations.items()))) + "\n"
        else:
            content = "// Generated from canonical 12 schemas + base OpenAPI + 26 extension paths. Do not edit.\n"
            content += "\n\n".join(reversed(declarations)) + "\n"
            content += "\nexport const API_OPERATIONS = " + json.dumps(dict(sorted(operations.items())),indent=2) + " as const;\n"
        results.append(content)
    return tuple(results)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    for path, content in zip((OUT_PY, OUT_TS),generate()):
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"STALE GENERATED TYPES: {path}")
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding="utf-8")
    print("12 schemas + base/extension OpenAPI generated types: PASS")


if __name__ == "__main__":
    main()
