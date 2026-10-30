"""CSS to source: the author rules that match an element, via the Chrome DevTools Protocol (guide section 7.1).

JSX elements are located through data-loc; plain CSS and CSS modules need this. Vite dev injects stylesheets as
<style data-vite-dev-id="/abs/path.css">, so the owner node's attribute gives the file. Served CSS is post-processed,
so callers find the rule in the source file by its selector text, not by line number.
"""
from pathlib import Path
from urllib.parse import urlparse


def url_to_repo_path(url: str, app_root: Path | None = None) -> str | None:
    """http://localhost:5173/src/index.css?t=1 -> src/index.css; a data: or inline sheet has no file."""
    u = urlparse(url)
    if u.scheme in ("data", "blob", "about", "chrome"):
        return None
    path = u.path.lstrip("/")
    return path or None


def abs_to_app_path(p: str, app_root: Path | None) -> str:
    if app_root is not None:
        try:
            return str(Path(p).resolve().relative_to(app_root.resolve()))
        except ValueError:
            pass
    return p.lstrip("/")


async def matched_rules(page, fixel_id: int, app_root: Path | None = None) -> list[dict]:
    """Author (non user-agent) rules matched to the element tagged data-fixel-id=<id>.

    Returns [{"selector", "css", "file"}]; `file` is app-relative when known, None for inline <style> sheets.
    """
    cdp = await page.context.new_cdp_session(page)
    sheets: dict[str, dict] = {}
    cdp.on("CSS.styleSheetAdded", lambda e: sheets.__setitem__(e["header"]["styleSheetId"], e["header"]))
    try:
        await cdp.send("DOM.enable")
        await cdp.send("CSS.enable")                   # replays styleSheetAdded for sheets already loaded
        root = await cdp.send("DOM.getDocument", {"depth": 0})
        node = await cdp.send("DOM.querySelector", {"nodeId": root["root"]["nodeId"],
                                                    "selector": f'[data-fixel-id="{fixel_id}"]'})
        if not node.get("nodeId"):
            return []
        matched = await cdp.send("CSS.getMatchedStylesForNode", {"nodeId": node["nodeId"]})
        out = []
        for m in matched.get("matchedCSSRules", []):
            rule = m["rule"]
            if rule.get("origin") != "regular":          # skip user-agent styles
                continue
            hdr = sheets.get(rule.get("styleSheetId"), {})
            out.append({"selector": rule["selectorList"]["text"], "css": rule["style"].get("cssText", "").strip(),
                        "file": await sheet_file(cdp, hdr, app_root)})
        return out
    finally:
        await cdp.detach()


async def sheet_file(cdp, hdr: dict, app_root: Path | None = None) -> str | None:
    if hdr.get("sourceURL"):
        return url_to_repo_path(hdr["sourceURL"], app_root)
    if hdr.get("ownerNode"):
        d = await cdp.send("DOM.describeNode", {"backendNodeId": hdr["ownerNode"]})
        attrs = d["node"].get("attributes", [])
        vite_id = dict(zip(attrs[::2], attrs[1::2])).get("data-vite-dev-id")
        return abs_to_app_path(vite_id, app_root) if vite_id else None
    return None
