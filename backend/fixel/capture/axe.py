"""axe-core injection: color-contrast violations mapped to Fixel element ids inside the page."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AXE_MIN_JS = REPO_ROOT / "node_modules" / "axe-core" / "axe.min.js"


async def run_axe(page):
    if not AXE_MIN_JS.exists():
        raise FileNotFoundError(f"{AXE_MIN_JS} missing: run `npm install` in the repo root")
    await page.add_script_tag(path=str(AXE_MIN_JS))
    return await page.evaluate("""async () => {
      const r = await axe.run(document, {runOnly: {type: 'rule', values: ['color-contrast']}});
      return r.violations.flatMap(v => v.nodes.map(n => ({rule: v.id,
        fixel: document.querySelector(n.target[0])?.getAttribute('data-fixel-id') ?? null,
        summary: n.failureSummary})));
    }""")
