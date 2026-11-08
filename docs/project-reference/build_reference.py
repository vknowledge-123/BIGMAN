"""Regenerate documentation sidecars from source; never import app.main or read data/."""
from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def read(path):
    return path.read_text(encoding='utf-8-sig')


def relative(path):
    return path.relative_to(ROOT).as_posix()


def models():
    from pydantic import BaseModel
    result = {}
    for module_name in ('app.schemas', 'app.preopen', 'app.algo_strategy'):
        module = importlib.import_module(module_name)
        for name, value in vars(module).items():
            if (inspect.isclass(value) and value.__module__ == module_name
                    and issubclass(value, BaseModel)):
                result[name] = value
    return result


def route_inventory(tree):
    routes = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == 'app'
                    and decorator.func.attr in ('get', 'post', 'put', 'patch', 'delete')):
                continue
            response = next((ast.unparse(k.value) for k in decorator.keywords if k.arg == 'response_model'), 'dynamic / HTML')
            routes.append({'method': decorator.func.attr.upper(), 'path': ast.literal_eval(decorator.args[0]),
                           'handler': node.name, 'parameters': ast.unparse(node.args),
                           'response_model': response, 'source_line': node.lineno})
    return routes


def main():
    all_models = models()
    from app.fno_symbols import FNO_SYMBOLS
    dump('FNO_SYMBOLS.json', {'classification': 'Static app equity-underlying list; not an automatically refreshed exchange list',
                             'count': len(FNO_SYMBOLS), 'symbols': sorted(FNO_SYMBOLS)})
    dump('MODEL_SCHEMAS.json', {name: model.model_json_schema() for name, model in all_models.items()})
    dump('DEFAULT_SETTINGS.json', {
        'scanner': all_models['VolumeFilterSettings']().model_dump(),
        'algo_api': all_models['AlgoSettings']().model_dump(),
        'preopen_csv': all_models['PreopenSettings']().model_dump(),
        'browser_display': {'volume_enabled': False, 'volume_min_shares': 100000,
                            'price_enabled': False, 'price_max_rupees': 250,
                            'circuit_enabled': True, 'circuit_min_percent': 20, 'circuit_scope': 'live'},
        'browser_algo_policy': {'mode_on_load': 'paper', 'sizing': 'capital',
                               'reference': 'original', 'reversal_size': 'initial'},
        'pending_not_current': [],
    })
    routes = route_inventory(ast.parse(read(ROOT / 'app/main.py')))
    dump('API_ROUTES.json', routes)
    parts = ['# Interfaces and source map', '',
             'Generated from the main source on 8 November 2026. No runtime account or cache data was read.', '',
             'This file complements PROJECT_SPECIFICATION.md. Line references identify this snapshot and can change after edits.', '',
             '## HTTP route inventory', '',
             '| Method | Path | Handler parameters | Response model | Source |',
             '|---|---|---|---|---|']
    for row in routes:
        parts.append(f"| {row['method']} | `{row['path']}` | `{row['handler']}({row['parameters']})` | `{row['response_model']}` | app/main.py:{row['source_line']} |")
    parts += ['', 'FastAPI also serves its standard /docs, /redoc and /openapi.json surfaces. Static resources are mounted at /static.', '',
              '## Exact model field inventory', '',
              'The JSON schema sidecar is authoritative for validation constraints and unions. Fields inherited from base models are included below. These are code defaults, not saved account settings.', '']
    for name, model in all_models.items():
        parts += [f'### {name}', '', '| Field | Python type | Default | Validation metadata |', '|---|---|---|---|']
        for field, definition in model.model_fields.items():
            default = 'REQUIRED' if definition.is_required() else ('factory: ' + getattr(definition.default_factory, '__name__', str(definition.default_factory)) if definition.default_factory else repr(definition.default))
            values = [field, str(definition.annotation), default, str(definition.metadata)]
            parts.append('| ' + ' | '.join('`' + v.replace('|', '\\|') + '`' for v in values) + ' |')
        parts.append('')
    parts += ['## Python definitions by file', '',
              'Public and internal functions are listed to make the implementation navigable. Names alone are not a substitute for the behavioral specification.', '']
    python_files = sorted((ROOT / 'app').glob('*.py')) + sorted((ROOT / 'scripts').glob('*.py'))
    for path in python_files:
        tree = ast.parse(read(path))
        parts += [f'### {relative(path)}', '']
        doc = ast.get_docstring(tree)
        if doc:
            parts += [doc, '']
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                parts.append(f'- Class `{node.name}` — line {node.lineno}.')
                if any(isinstance(d, ast.Name) and d.id == 'dataclass' for d in node.decorator_list):
                    fields = [n for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
                    for item in fields:
                        parts.append(f'  - Field `{item.target.id}: {ast.unparse(item.annotation)}`' + (f' = `{ast.unparse(item.value)}`' if item.value else '') + '.')
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        sig = ast.unparse(method.args).replace('\n', ' ')
                        parts.append(f'  - `{method.name}({sig})` — line {method.lineno}.')
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parts.append(f'- `{node.name}({ast.unparse(node.args)})` — line {node.lineno}.')
        parts.append('')
    parts += ['## Browser function and control inventory', '']
    for name in ('app.js', 'preopen.js'):
        content = read(ROOT / 'app/static' / name)
        parts += [f'### app/static/{name}', '']
        for match in re.finditer(r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)', content):
            line = content[:match.start()].count('\n') + 1
            parts.append(f'- `{match.group(1)}({match.group(2)})` — line {line}.')
        keys = sorted(set(re.findall(r'[\'\"](scanner\.[^\'\"]+)[\'\"]', content)))
        if keys:
            parts += ['', 'Browser preference identifiers: ' + ', '.join(f'`{key}`' for key in keys) + '.']
        parts.append('')
    html = read(ROOT / 'app/static/index.html')
    parts += ['### HTML controls', '', '| Element | ID | Input type |', '|---|---|---|']
    for match in re.finditer(r'<(input|select|textarea|button|form)\b([^>]+)>', html):
        attrs = match.group(2)
        identifier = re.search(r'\bid="([^"]+)"', attrs)
        kind = re.search(r'\btype="([^"]+)"', attrs)
        if identifier:
            parts.append(f"| {match.group(1)} | `{identifier.group(1)}` | {kind.group(1) if kind else '—'} |")
    (OUT / 'INTERFACES_AND_SOURCE_MAP.md').write_text('\n'.join(parts) + '\n', encoding='utf-8')

    inventory = ['# Test source inventory', '',
                 'Source-derived declarations, not a test execution or pass report. Parameterized tests may generate many more cases than the declared function count. Browser dependencies may be optional or skipped in a given environment.', '',
                 'Read the behavioral acceptance matrix in PROJECT_SPECIFICATION.md before treating any suite as sufficient for deployment.', '']
    count = 0
    for path in sorted((ROOT / 'tests').glob('test_*.py')):
        tree = ast.parse(read(path))
        names = [(n.name, n.lineno) for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')]
        inventory += [f'## {relative(path)}', '', f'{len(names)} test function declarations.', '']
        for name, line in sorted(names, key=lambda row: row[1]):
            inventory.append(f'- `{name}` — line {line}.')
        inventory.append('')
        count += len(names)
    js_count = 0
    for path in sorted((ROOT / 'tests').glob('*.cjs')):
        names = re.findall(r'\btest\(\s*[\'\"]([^\'\"]+)[\'\"]', read(path))
        inventory += [f'## {relative(path)}', '']
        inventory += [f'- {name}' for name in names] or ['Standalone browser/test harness; inspect source for workflows.']
        inventory.append('')
        js_count += len(names)
    inventory.insert(6, f'Inventory totals: {count} Python test-function declarations and {js_count} named JavaScript test declarations. These are not collected-case or passing-case totals.\n')
    (OUT / 'TEST_INVENTORY.md').write_text('\n'.join(inventory) + '\n', encoding='utf-8')

    paths = sorted(set(list((ROOT / 'app').rglob('*.py')) + list((ROOT / 'app/static').glob('*'))
                       + list((ROOT / 'tests').glob('*.py')) + list((ROOT / 'tests').glob('*.cjs'))
                       + list((ROOT / 'scripts').glob('*.py')) + list((ROOT / 'scripts').glob('*.ps1'))
                       + [ROOT / 'requirements.txt', ROOT / 'README.md', ROOT / 'Start Scanner.bat']))
    files = [{'path': relative(p), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in paths if p.is_file()]
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dump('SOURCE_MANIFEST.json', {'document_date_ist': '2026-11-08', 'git_head': commit,
         'snapshot_note': 'Working source includes uncommitted changes. Per-file hashes, not HEAD alone, identify the documented baseline.',
         'scope': 'Application, tests, launch scripts, requirements and README only; no data/ or account files.', 'files': files})
    print(json.dumps({'models': len(all_models), 'routes': len(routes), 'source_files': len(files),
                      'python_test_functions': count, 'javascript_test_declarations': js_count}))


if __name__ == '__main__':
    main()
