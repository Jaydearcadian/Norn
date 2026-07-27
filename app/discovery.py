from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import Settings
from .digests import sha256_digest
from .models import DiscoverRequest, Opportunity, OpportunityValue
from .store import JsonStore


class DiscoveryEngine:
    def __init__(self, settings: Settings, store: JsonStore):
        self.settings = settings
        self.store = store

    async def discover(self, request: DiscoverRequest) -> list[Opportunity]:
        candidates = self.store.list_opportunities()
        if self.settings.enable_live_discovery:
            feed_task = self._fetch_configured_feeds()
            github_task = self._fetch_github_queries()
            feed_items, github_items = await asyncio.gather(feed_task, github_task)
            live = [*feed_items, *github_items]
            if live:
                candidates = self.store.save_opportunities(live)
        if request.query:
            terms = set(re.findall(r"[a-z0-9+#.-]+", request.query.lower()))
            candidates = [
                item for item in candidates
                if terms & set(re.findall(r"[a-z0-9+#.-]+", f"{item.title} {item.summary} {' '.join(item.requirements)}".lower()))
            ]
        if request.types:
            allowed = set(request.types)
            candidates = [item for item in candidates if item.type in allowed]
        return candidates[: request.maximumResults]


    async def _fetch_github_queries(self) -> list[Opportunity]:
        if not self.settings.github_queries:
            return []
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Norn/0.1"}
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
                labels = {str(item.get("name", "")).lower() for item in issue.get("labels", [])}
                opp_type = "bounty" if any("bounty" in label or "reward" in label for label in labels) else "other"
                repository_url = issue.get("repository_url", "").replace("api.github.com/repos", "github.com")
                requirements = [f"Resolve the scoped GitHub issue: {issue.get('title', '')}"]
                if labels:
                    requirements.append("Work within issue labels: " + ", ".join(sorted(labels)))
                opportunities.append(Opportunity(
                    id=f"github_{issue['id']}",
                    title=issue.get("title", "GitHub opportunity"),
                    type=opp_type,
                    issuer=repository_url.rsplit("/", 2)[-2] + "/" + repository_url.rsplit("/", 1)[-1] if repository_url else "GitHub repository",
                    summary=(issue.get("body") or "")[:700],
                    value=OpportunityValue(currency="USD", note="Check the issue for reward terms."),
                    requirements=requirements,
                    preferredCapabilities=[label for label in labels if label],
                    sourceUrl=issue["html_url"],
                    sourceTimestamp=issue.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    sourceType="official",
                    applicationEffort="medium",
                    competitiveIntensity="unknown",
                    longTermValue=55,
                    status="open",
                ))
        return opportunities

    async def _fetch_configured_feeds(self) -> list[Opportunity]:
        if not self.settings.source_feed_urls:
            return []
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=False) as client:
            results = await asyncio.gather(
                *(self._fetch_feed(client, url) for url in self.settings.source_feed_urls),
                return_exceptions=True,
            )
        opportunities: list[Opportunity] = []
        for result in results:
            if isinstance(result, list):
                opportunities.extend(result)
        return opportunities

    async def _fetch_feed(self, client: httpx.AsyncClient, url: str) -> list[Opportunity]:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("Only HTTPS discovery feeds are accepted")
        response = await client.get(url, headers={"User-Agent": "Norn/0.1"})
        response.raise_for_status()
        payload: Any = response.json()
        items = payload.get("opportunities", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("Feed must return an array or {opportunities: []}")
        normalised: list[Opportunity] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item.setdefault("id", f"feed_{sha256_digest(item)[:16]}")
            item.setdefault("sourceTimestamp", datetime.now(timezone.utc).isoformat())
            item.setdefault("sourceType", "aggregator")
            item.setdefault("value", {"currency": "USD"})
            normalised.append(Opportunity.model_validate(item))
        return normalised
