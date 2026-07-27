from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .adapters import GitHubIssueAdapter, OfficialHtmlAdapter, StructuredFeedAdapter
from .config import Settings
from .models import DiscoverRequest, Opportunity
from .store import JsonStore


class DiscoveryEngine:
    def __init__(self, settings: Settings, store: JsonStore):
        self.settings = settings
        self.store = store
        self.feed_adapter = StructuredFeedAdapter()
        self.github_adapter = GitHubIssueAdapter()
        self.html_adapter = OfficialHtmlAdapter()

    async def discover(self, request: DiscoverRequest) -> list[Opportunity]:
        candidates = self.store.list_opportunities()
        if self.settings.enable_live_discovery:
            feed_items, github_items = await asyncio.gather(self._fetch_configured_feeds(), self._fetch_github_queries())
            live = [*feed_items, *github_items]
            if live:
                candidates = self.store.save_opportunities(live)
        if request.query:
            terms = set(re.findall(r"[a-z0-9+#.-]+", request.query.lower()))
            candidates = [
                item for item in candidates
                if terms & set(re.findall(
                    r"[a-z0-9+#.-]+",
                    f"{item.title} {item.summary} {' '.join(req.statement for req in item.requirements)}".lower(),
                ))
            ]
        if request.types:
            candidates = [item for item in candidates if item.type in set(request.types)]
        return candidates[: request.maximumResults]

    async def ingest_url(self, url: str, source_type: str = "official") -> list[Opportunity]:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("Only HTTPS sources are accepted")
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Norn/0.2"})
            response.raise_for_status()
        content_type = response.headers.get("content-type", "application/octet-stream")
        if "json" in content_type or "rss" in content_type or "xml" in content_type:
            items = self.feed_adapter.compile(url=str(response.url), content=response.content, content_type=content_type, source_type=source_type)
        else:
            items = self.html_adapter.compile(url=str(response.url), content=response.content, content_type=content_type, source_type=source_type)
        for item in items:
            for snapshot_id in item.intelligence.sourceSnapshotIds:
                # adapters produce immutable IDs; snapshot metadata is persisted by imports below when supplied
                pass
        return self.store.save_opportunities(items)

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
        opportunities: list[Opportunity] = []
        for result in results:
            if isinstance(result, Exception) or result.status_code != 200:
                continue
            for issue in result.json().get("items", []):
                try:
                    opportunities.append(self.github_adapter.compile_issue(issue))
                except Exception:
                    continue
        return opportunities

    async def _fetch_configured_feeds(self) -> list[Opportunity]:
        if not self.settings.source_feed_urls:
            return []
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=True) as client:
            results = await asyncio.gather(*(self._fetch_feed(client, url) for url in self.settings.source_feed_urls), return_exceptions=True)
        opportunities: list[Opportunity] = []
        for result in results:
            if isinstance(result, list):
                opportunities.extend(result)
        return opportunities

    async def _fetch_feed(self, client: httpx.AsyncClient, url: str) -> list[Opportunity]:
        if urlparse(url).scheme != "https":
            raise ValueError("Only HTTPS discovery feeds are accepted")
        response = await client.get(url, headers={"User-Agent": "Norn/0.2"})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "application/json")
        if "json" in content_type or "rss" in content_type or "xml" in content_type:
            return self.feed_adapter.compile(url=str(response.url), content=response.content, content_type=content_type, source_type="aggregator")
        return self.html_adapter.compile(url=str(response.url), content=response.content, content_type=content_type, source_type="official")
