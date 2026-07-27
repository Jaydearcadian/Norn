from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from .compiler import classify_page, compile_candidate, snapshot_id, source_id
from .config import Settings
from .digests import sha256_digest
from .models import DiscoverRequest, Opportunity, SourceSnapshot
from .store import JsonStore


class DiscoveryEngine:
    def __init__(self, settings: Settings, store: JsonStore):
        self.settings = settings
        self.store = store

    async def discover(self, request: DiscoverRequest) -> list[Opportunity]:
        candidates = self.store.list_opportunities()
        if self.settings.enable_live_discovery:
            feed_items, github_items = await asyncio.gather(self._fetch_configured_sources(), self._fetch_github_queries())
            live = [*feed_items, *github_items]
            if live:
                candidates = self.store.save_opportunities(live)
        if request.query:
            terms = set(re.findall(r"[a-z0-9+#.-]+", request.query.lower()))
            candidates = [
                item for item in candidates
                if terms & set(re.findall(r"[a-z0-9+#.-]+", self._search_text(item).lower()))
            ]
        if request.types:
            allowed = set(request.types)
            candidates = [item for item in candidates if item.type in allowed]
        return candidates[: request.maximumResults]

    @staticmethod
    def _search_text(item: Opportunity) -> str:
        requirements = " ".join(r.statement for r in [*item.eligibility, *item.requirements, *item.deliverables])
        return " ".join([item.title, item.summary, item.issuer, item.programme or "", item.track or "", requirements, *item.themes, *item.technicalDomains])

    async def _fetch_github_queries(self) -> list[Opportunity]:
        if not self.settings.github_queries:
            return []
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Norn/0.2"}
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=False, headers=headers) as client:
            results = await asyncio.gather(
                *(client.get("https://api.github.com/search/issues", params={"q": query, "per_page": 25}) for query in self.settings.github_queries),
                return_exceptions=True,
            )
        compiled: list[Opportunity] = []
        run_id = self.store.start_normalization_run("github")
        input_count = 0
        for result in results:
            if isinstance(result, Exception) or result.status_code != 200:
                continue
            for issue in result.json().get("items", []):
                input_count += 1
                body = json.dumps(issue, sort_keys=True).encode()
                url = issue["html_url"]
                digest = "sha256:" + sha256_digest(body.decode())
                labels = [str(item.get("name", "")) for item in issue.get("labels", [])]
                repository_url = issue.get("repository_url", "").replace("api.github.com/repos", "github.com")
                issuer = repository_url.removeprefix("https://github.com/") or "GitHub repository"
                snapshot = SourceSnapshot(
                    id=snapshot_id(url, digest), sourceId=source_id(url), url=url, sourceType="official",
                    pageType="github_issue", retrievedAt=datetime.now(timezone.utc), publishedAt=issue.get("created_at"),
                    contentDigest=digest, contentType="application/vnd.github+json", httpStatus=200,
                    issuer=issuer, title=issue.get("title"),
                )
                self.store.save_source_snapshot(snapshot, body)
                raw = {
                    "id": f"github_{issue['id']}", "title": issue.get("title"), "body": issue.get("body") or "",
                    "issuer": issuer, "programme": issuer, "track": f"Issue #{issue.get('number')}",
                    "type": "bounty" if any("bounty" in label.lower() or "reward" in label.lower() for label in labels) else "other",
                    "labels": labels, "applicationUrl": url, "deadline": None, "status": "open",
                    "requirements": [f"Resolve the scoped GitHub issue: {issue.get('title', '')}"] + (["Work within issue labels: " + ", ".join(sorted(labels))] if labels else []),
                    "preferredCapabilities": labels, "independentlyActionable": True,
                }
                compiled.extend(compile_candidate(raw, snapshot, "github"))
        self.store.save_opportunities(compiled, run_id)
        self.store.finish_normalization_run(run_id, len(compiled), sum(item.reviewStatus == "pending" for item in compiled), f"inputs={input_count}")
        return compiled

    async def _fetch_configured_sources(self) -> list[Opportunity]:
        if not self.settings.source_feed_urls:
            return []
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=True, headers={"User-Agent": "Norn/0.2"}) as client:
            results = await asyncio.gather(*(self._fetch_source(client, url) for url in self.settings.source_feed_urls), return_exceptions=True)
        compiled: list[Opportunity] = []
        for result in results:
            if isinstance(result, list):
                compiled.extend(result)
        return compiled

    async def _fetch_source(self, client: httpx.AsyncClient, url: str) -> list[Opportunity]:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("Only HTTPS discovery sources are accepted")
        response = await client.get(url)
        response.raise_for_status()
        body = response.content
        content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
        digest = "sha256:" + sha256_digest(body.decode(errors="replace"))
        title = self._html_title(body.decode(errors="replace")) if "html" in content_type else None
        page_type = classify_page(title or "", body.decode(errors="replace"), content_type, str(response.url))
        snapshot = SourceSnapshot(
            id=snapshot_id(str(response.url), digest), sourceId=source_id(str(response.url)), url=str(response.url),
            sourceType="official" if parsed.netloc == urlparse(str(response.url)).netloc else "aggregator",
            pageType=page_type, retrievedAt=datetime.now(timezone.utc), contentDigest=digest,
            contentType=content_type, httpStatus=response.status_code, title=title,
        )
        self.store.save_source_snapshot(snapshot, body)
        adapter = "official_html"
        raw_items: list[dict[str, Any]] = []
        if "json" in content_type:
            adapter = "structured_json"
            payload: Any = response.json()
            items = payload.get("opportunities", payload.get("items", payload)) if isinstance(payload, dict) else payload
            raw_items = items if isinstance(items, list) else [payload] if isinstance(payload, dict) else []
        elif any(marker in content_type for marker in ("xml", "rss", "atom")):
            adapter = "rss"
            raw_items = self._rss_items(body)
        else:
            text = self._html_text(body.decode(errors="replace"))
            raw_items = [{"title": title or parsed.path.rstrip("/").split("/")[-1].replace("-", " ").title(), "summary": text[:12000], "applicationUrl": str(response.url)}]
        run_id = self.store.start_normalization_run(adapter, len(raw_items))
        compiled: list[Opportunity] = []
        for raw in raw_items:
            if isinstance(raw, dict):
                compiled.extend(compile_candidate(raw, snapshot, adapter))
        self.store.save_opportunities(compiled, run_id)
        self.store.finish_normalization_run(run_id, len(compiled), sum(item.reviewStatus == "pending" for item in compiled))
        return compiled

    @staticmethod
    def _html_title(html: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else None

    @staticmethod
    def _html_text(html: str) -> str:
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "\n", html)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())

    @staticmethod
    def _rss_items(body: bytes) -> list[dict[str, Any]]:
        root = ET.fromstring(body)
        items = []
        for node in root.findall(".//item") + root.findall(".//{*}entry"):
            def text(name: str) -> str:
                child = node.find(name) or node.find(f"{{*}}{name}")
                return (child.text or "").strip() if child is not None else ""
            link = text("link")
            if not link:
                link_node = node.find("{*}link")
                link = link_node.attrib.get("href", "") if link_node is not None else ""
            items.append({"title": text("title"), "summary": text("description") or text("summary") or text("content"), "applicationUrl": link, "publishedAt": text("pubDate") or text("updated")})
        return items
