"""The Next.js data-loc injection: a Node preload wraps next.config.js, a webpack pre-loader stamps source locations."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fixel.config import Target
from fixel.target import FIXEL_HOME, NEXT_PRELOAD, build_env

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
TOOLING = FIXEL_HOME / "tooling"


def node(script: str, cwd: Path, env_extra: dict | None = None) -> dict:
    import os
    env = {**os.environ, "FIXEL": "1", "FIXEL_APP_ROOT": str(cwd), **(env_extra or {})}
    r = subprocess.run(["node", "-e", script], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


STUB = """
Object.defineProperty(exports, '__esModule', {{ value: true }});
Object.defineProperty(exports, 'default', {{ enumerable: true, get() {{ return loadConfig }} }});
Object.defineProperty(exports, 'normalizeConfig', {{ enumerable: true, get() {{ return () => 'normalized' }} }});
let calls = 0;
async function loadConfig(phase, dir, opts) {{ calls++; return {config} }}
"""


def probe(cwd: Path, config_expr: str, dir_arg: str = "cwd", env_extra: dict | None = None) -> dict:
    """A stand-in for next/dist/server/config.js (Next's loadConfig) under cwd/node_modules, required through the preload;
    call its default export the way Next does and run the returned config's webpack() hook."""
    mod = cwd / "node_modules" / "next" / "dist" / "server"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "config.js").write_text(STUB.format(config=config_expr))
    return node(f"""
      require({json.dumps(str(NEXT_PRELOAD))});
      (async () => {{
        const m = require({json.dumps(str(mod / 'config.js'))});
        const cwd = {json.dumps(str(cwd))};
        const other = {json.dumps(str(cwd / 'elsewhere'))};
        const cfg = await m.default('phase-development-server', {dir_arg}, {{}});
        const out = {{ name: m.default.name, normalize: m.normalizeConfig(), esm: m.__esModule, other: cfg.reactStrictMode,
                       hasWebpack: typeof cfg.webpack === 'function' }};
        if (out.hasWebpack) {{
          const w = cfg.webpack({{ module: {{ rules: [{{ test: 'existing' }}] }}, marker: 1 }}, {{ dev: true, isServer: false }});
          out.rules = w.module.rules.map(r => r.test instanceof RegExp ? r.test.source : r.test);
          out.first = w.module.rules[0];
          out.marker = w.marker;
          out.prodRules = cfg.webpack({{ module: {{ rules: [] }} }}, {{ dev: false }}).module.rules.length;
          const again = await m.default('phase-development-server', cwd, {{}});
          out.sameHookWhenPatchedTwice = again.webpack.__fixel === true;
        }}
        console.log(JSON.stringify(out, (k, v) => v instanceof RegExp ? v.source : v));
      }})();
    """, cwd, env_extra)


def test_the_config_next_loads_gets_a_pre_loader_in_dev_only(tmp_path):
    out = probe(tmp_path, "{ reactStrictMode: true, webpack: null }")           # webpack: null is Next's default
    assert out["hasWebpack"] and out["other"] is True                         # the user's other options survive
    assert out["rules"] == [r"\.(jsx|tsx)$", "existing"]                      # prepended, existing rules kept
    first = out["first"]
    assert first["enforce"] == "pre" and first["use"][0]["loader"].endswith("next-data-loc-loader.cjs")
    assert first["use"][0]["options"]["root"] == str(tmp_path) and first["include"] == [str(tmp_path)]
    assert out["prodRules"] == 0 and out["sameHookWhenPatchedTwice"]          # never in a production build; no double wrap


def test_an_existing_webpack_hook_still_runs_first_and_its_result_is_used(tmp_path):
    out = probe(tmp_path, "{ webpack(c) { c.marker = 'user'; c.module.rules.push({ test: 'added' }); return c } }")
    assert out["marker"] == "user" and out["rules"][0] == r"\.(jsx|tsx)$" and "added" in out["rules"]


def test_the_rest_of_nexts_config_module_is_untouched(tmp_path):
    out = probe(tmp_path, "{ reactStrictMode: true }")
    assert out["normalize"] == "normalized" and out["esm"] is True            # other exports and __esModule still work


def test_only_the_scanned_apps_config_is_patched(tmp_path):
    assert probe(tmp_path, "{ reactStrictMode: true }", dir_arg="other")["hasWebpack"] is False


def test_inactive_without_the_fixel_flag(tmp_path):
    out = probe(tmp_path, "{ reactStrictMode: true }", env_extra={"FIXEL": "0"})
    assert out["hasWebpack"] is False and out["name"] == "loadConfig"          # Next's own function, not the wrapper


# ----------------------------------------------------------------------------- the loader
def run_loader(tmp_path: Path, name: str, source: str) -> dict:
    (tmp_path / "components").mkdir(exist_ok=True)
    f = tmp_path / "components" / name
    f.write_text(source)
    return node(f"""
      const loader = require({json.dumps(str(TOOLING / 'next-data-loc-loader.cjs'))});
      const warnings = [];
      const ctx = {{ resourcePath: {json.dumps(str(f))}, rootContext: {json.dumps(str(tmp_path))}, sourceMap: false,
                     getOptions: () => ({{ root: {json.dumps(str(tmp_path))} }}),
                     emitWarning: (e) => warnings.push(e.message),
                     async: () => (err, code, map) => console.log(JSON.stringify({{ err: err && err.message, code, warnings }})) }};
      loader.call(ctx, {json.dumps(source)}, undefined);
    """, tmp_path)


TSX = """import React from 'react'
type Props<T> = { items: T[]; label?: string }
export function List<T extends {id: number}>({ items, label }: Props<T>) {
  return (
    <section className="p-4">
      <h2>{label as string}</h2>
      <Item data={items[0]} />
      <ul>{items.map((i) => <li key={i.id}>{i.id}</li>)}</ul>
    </section>
  )
}
"""


def test_loader_stamps_intrinsic_elements_with_relative_locations_and_keeps_typescript(tmp_path):
    out = run_loader(tmp_path, "List.tsx", TSX)
    code = out["code"]
    assert out["err"] is None and out["warnings"] == []
    assert 'data-loc="components/List.tsx:5:5"' in code                     # <section>, relative to the app root
    assert 'data-loc="components/List.tsx:6:7"' in code                     # <h2>
    assert 'data-loc="components/List.tsx:8:7"' in code                     # <ul>
    assert 'data-loc="components/List.tsx:8:29"' in code                    # <li> inside the map callback
    assert "<Item " in code and code.count("data-loc") == 4                 # section, h2, ul, li; components are not stamped
    assert "type Props<T>" in code and "label as string" in code            # TypeScript is preserved for SWC to compile


def test_loader_does_not_stamp_twice(tmp_path):
    src = 'export const A = () => <div data-loc="manual">x</div>\n'
    assert run_loader(tmp_path, "A.jsx", src)["code"].count("data-loc") == 1


def test_loader_passes_unparseable_files_through_with_a_warning(tmp_path):
    src = "export const A = () => <div>unclosed\n"
    out = run_loader(tmp_path, "Broken.tsx", src)
    assert out["code"] == src and out["err"] is None
    assert len(out["warnings"]) == 1 and "Broken.tsx" in out["warnings"][0]


# ----------------------------------------------------------------------------- the Python side
def test_build_env_for_a_next_app_sets_the_preload_and_keeps_existing_node_options(tmp_path, monkeypatch):
    (tmp_path / "next.config.js").write_text("module.exports = {}")
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=2048")
    env, cmd, notes = build_env(Target(name="n"), tmp_path)
    assert env["FIXEL"] == "1" and env["FIXEL_APP_ROOT"] == str(tmp_path)
    assert env["NODE_OPTIONS"] == f"--require {NEXT_PRELOAD} --max-old-space-size=2048"
    assert cmd.startswith("npx next dev") and notes == [] and "FIXEL_TARGET_CONFIG" not in env


def test_build_env_for_a_vite_app_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("NODE_OPTIONS", raising=False)
    (tmp_path / "vite.config.js").write_text("export default {}")
    env, cmd, _ = build_env(Target(name="v"), tmp_path)
    assert env["FIXEL_TARGET_CONFIG"] == str(tmp_path / "vite.config.js") and "NODE_OPTIONS" not in env and "vite" in cmd


def test_esm_and_typescript_configs_need_no_special_handling(tmp_path):
    # the hook sits on Next's loader, which returns the normalized config whatever file format produced it
    (tmp_path / "next.config.mjs").write_text("export default {}")
    env, cmd, notes = build_env(Target(name="n"), tmp_path)
    assert env["FIXEL_APP_ROOT"] == str(tmp_path) and "--require" in env["NODE_OPTIONS"] and notes == []


# ----------------------------------------------------------------------------- a real Next app
EBROKER = Path(__file__).resolve().parents[1] / "targets" / "e-broker"


@pytest.mark.skipif(not (EBROKER / "node_modules" / ".bin" / "next").exists(), reason="run `make targets` first")
async def test_a_real_next_app_serves_html_with_source_locations():
    import re
    import urllib.request

    from fixel import config as cfg
    from fixel.target import TargetServer

    conf = cfg.load(FIXEL_HOME / "targets" / "e-broker.yaml")
    conf.target.path = str(EBROKER)
    async with TargetServer(conf.target, timeout=120) as url:
        html = urllib.request.urlopen(url + "/auth/login", timeout=120).read().decode()
    locs = re.findall(r'data-loc="([^"]+)"', html)
    assert len(locs) > 10
    assert all(re.match(r"^[\w()\[\]./-]+\.tsx:\d+:\d+$", l) for l in locs)
    assert not any("node_modules" in l or l.startswith("/") for l in locs)
    assert any(l.startswith("app/") for l in locs) and any(l.startswith("components/") for l in locs)
