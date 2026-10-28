"""Internet tools: web search and page reading (stdlib only).

* ``web_search``: DuckDuckGo's HTML endpoint (no account, no API key). Returns title, URL, snippet.
* ``read_web_page``: fetches one http(s) page and converts it to plain text.

Safety:
* Both need ``privacy.allow_network = true`` (the policy denies them otherwise).
* Everything returned is UNTRUSTED and fenced by the coordinator; reading a page taints the
  conversation, so any action afterwards needs your approval.
* ``read_web_page`` refuses localhost, private/LAN, link-local and other special addresses (after DNS
  resolution) so a web page can't make N.E.K.O. talk to things on your PC or home network
  (e.g. the Ollama server). Redirects are re-checked; size and time are capped.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..core.errors import PermissionDeniedError, ToolError
from ..core.types import RiskLevel
from .base import ToolContext, ToolRegistry, ToolResult, ToolSpec

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) N.E.K.O./0.3 (personal assistant)"
MAX_BYTES = 2_000_000


def _check_public(url: str) -> None:
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise PermissionDeniedError(f"only http(s) web addresses are allowed: {url}")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ToolError(f"could not resolve {u.hostname}: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise PermissionDeniedError(
                f"{u.hostname} points to a local/private address ({ip}); blocked for safety",
                user_message="That address points inside your PC or home network, so I won't open it.")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, D401
        _check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


def http_get(url: str, timeout: float = 15.0, data: bytes | None = None) -> tuple[str, str]:
    """Returns (final_url, decoded_text). Public addresses only."""
    _check_public(url)
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with _opener.open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES + 1)[:MAX_BYTES]
            charset = resp.headers.get_content_charset() or "utf-8"
            ctype = resp.headers.get_content_type()
            final = resp.geturl()
    except urllib.error.HTTPError as exc:
        raise ToolError(f"the website answered HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise ToolError(f"couldn't reach the website: {exc}") from exc
    if ctype not in ("text/html", "text/plain", "application/xhtml+xml", "application/json", "text/xml"):
        raise ToolError(f"that page is {ctype}, not text")
    return final, raw.decode(charset, errors="replace")


def http_get_image(url: str, timeout: float = 15.0, max_bytes: int = 4_000_000) -> bytes:
    """Download one picture (image/* only, size capped). Public addresses only."""
    _check_public(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with _opener.open(req, timeout=timeout) as resp:
            if not resp.headers.get_content_type().startswith("image/"):
                raise ToolError("that address is not a picture")
            raw = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise ToolError(f"the website answered HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise ToolError(f"couldn't reach the website: {exc}") from exc
    if len(raw) > max_bytes:
        raise ToolError("that picture is too large")
    return raw


def wiki_picture(topic: str, timeout: float = 12.0) -> dict[str, Any] | None:
    """Wikipedia's lead picture and one-paragraph summary for a topic (for the visual panel).
    Returns {"title", "extract", "page_url", "image": bytes | None} or None if nothing matched."""
    topic = topic.strip()[:120]
    if not topic:
        return None
    # relevance-ranked search (opensearch is prefix-only: "rainbow forms" matched "Rainbow Foods")
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": topic, "srlimit": 1,
                                "srnamespace": 0, "format": "json"})
    _, found = http_get("https://en.wikipedia.org/w/api.php?" + q, timeout=timeout)
    try:
        title = json.loads(found)["query"]["search"][0]["title"]
    except (ValueError, IndexError, KeyError, TypeError):
        return None
    _, raw = http_get("https://en.wikipedia.org/api/rest_v1/page/summary/"
                      + urllib.parse.quote(title.replace(" ", "_")), timeout=timeout)
    try:
        info = json.loads(raw)
    except ValueError:
        return None
    img_url = (info.get("thumbnail") or {}).get("source") or ""
    image = None
    if img_url.startswith("https://") and (urllib.parse.urlparse(img_url).hostname or "").endswith(".wikimedia.org"):
        try:
            image = http_get_image(img_url, timeout=timeout)
        except (ToolError, PermissionDeniedError):
            image = None
    return {"title": info.get("title", title), "extract": str(info.get("extract", ""))[:1200],
            "page_url": ((info.get("content_urls") or {}).get("desktop") or {}).get("page", ""), "image": image}


def html_to_text(page: str) -> tuple[str, str]:
    """Very small readability pass: title + visible text, scripts/styles/nav removed."""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    if m:
        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    page = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header|form|iframe)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section|article)>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines if len(ln) > 1)
    return title, re.sub(r"\n{3,}", "\n\n", text)


def parse_ddg(page: str, limit: int) -> list[dict[str, str]]:
    results = []
    anchors = list(re.finditer(r'(?s)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page))
    for i, a in enumerate(anchors):
        href = html.unescape(a.group(1))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        url = q.get("uddg", [href])[0]  # DuckDuckGo wraps result links in a redirect
        title = html.unescape(re.sub(r"<[^>]+>", "", a.group(2))).strip()
        # the snippet follows the title link, before the next result's link
        segment = page[a.end(): anchors[i + 1].start() if i + 1 < len(anchors) else len(page)]
        sn = re.search(r'(?s)class="result__snippet"[^>]*>(.*?)</a>', segment)
        snippet = html.unescape(re.sub(r"<[^>]+>", "", sn.group(1))).strip() if sn else ""
        if url.startswith("http") and "duckduckgo.com/y.js" not in url:
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def _web_search(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    q = args["query"].strip()
    # A normal form POST, exactly like DuckDuckGo's own search box (GET gets a bot-check page).
    # If DuckDuckGo ever shows a challenge, we report it instead of trying to get around it.
    _final, page = http_get("https://html.duckduckgo.com/html/", data=urllib.parse.urlencode({"q": q}).encode())
    if "anomaly" in page.lower() and "result__a" not in page:
        return ToolResult(False, "The search engine asked for a human check, so I couldn't search right now.")
    results = parse_ddg(page, args["limit"])
    if not results:
        return ToolResult(False, f"No web results found for: {q}")
    lines = [f"{i + 1}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results)]
    return ToolResult(True, f"Found {len(results)} web results for: {q}", "\n".join(lines))


def _read_page(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    final, page = http_get(args["url"])
    title, text = html_to_text(page)
    cut = text[: args["max_chars"]]
    return ToolResult(True, f"Read web page: {title or final}",
                      f"Title: {title}\nURL: {final}\n\n{cut}" + ("\n[...page truncated...]" if len(text) > len(cut) else ""))


def register_web_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="web_search", description="Search the internet. Use for current events, facts you don't know, "
                                        "prices, news, documentation. Returns titles, links and snippets.",
        params={"query": {"type": "string", "required": True, "max_length": 300, "description": "search words"},
                "limit": {"type": "integer", "default": 6, "min": 1, "max": 10}},
        handler=_web_search, risk=RiskLevel.READ_ONLY, category="network", needs_network=True, timeout_s=25,
    ))
    registry.register(ToolSpec(
        name="read_web_page", description="Open a web page (http/https) and read its text, e.g. a result "
                                          "from web_search. Content is untrusted.",
        params={"url": {"type": "string", "required": True, "max_length": 2000, "description": "the page address"},
                "max_chars": {"type": "integer", "default": 8000, "min": 500, "max": 30000}},
        handler=_read_page, risk=RiskLevel.READ_ONLY, category="network", needs_network=True, timeout_s=30,
    ))
