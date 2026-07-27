from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from html import unescape
from typing import Any

from .digests import sha256_digest
from .models import Opportunity, OpportunityValue
from .normalization import compile_opportunity, snapshot_from_response


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def compile(self, *, url: str, content: bytes, content_type: str, source_type: str) -> list[Opportunity]:
        raise NotImplementedError


class StructuredFeedAdapter(SourceAdapter):
    name = "structured-json-rss"

    def compile(self, *, url: str, content: bytes, content_type: str, source_type: str) -> list[Opportunity]:
        snapshot = snapshot_from_response(url=url, content=content, content_type=content_type, http_status=200, source_type=source_type, document_role="announcement")
        text = content.decode("utf-8", errors="replace")
        if "json" in content_type:
            payload: Any = json.loads(text)
            items = payload.get("opportunities", payload) if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                raise ValueError("Structured feed must contain an opportunity array")
        else:
            items = []
            for block in re.findall(r"<item\b.*?</item>|<entry\b.*?</entry>", text, flags=re.I | re.S):
                def tag(name: str) -> str:
                    match = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, flags=re.I | re.S)
                    return unescape(re.sub(r"<[^>]+>", " ", match.group(1))).strip() if match else ""
                link_match = re.search(r"<link\b[^>]*href=[\"']([^\"']+)", block, flags=re.I)
                items.append({"title": tag("title"), "summary": tag("description") or tag("summary"), "sourceUrl": link_match.group(1) if link_match else tag("link"), "issuer": tag("author") or "Unknown issuer", "type": "other"})
        compiled = []
        for index, raw in enumerate(items):
            if not isinstance(raw, dict):
                continue
            raw.setdefault("id", f"feed_{sha256_digest(raw)[:16]}")
            raw.setdefault("sourceUrl", url)
            raw.setdefault("sourceTimestamp", datetime.now(timezone.utc).isoformat())
            raw.setdefault("sourceType", source_type)
            raw.setdefault("value", {"currency": "USD"})
            raw.setdefault("issuer", "Unknown issuer")
            raw.setdefault("title", f"Opportunity {index + 1}")
            raw.setdefault("type", "other")
            opportunity = Opportunity.model_validate(raw)
            compiled.append(compile_opportunity(opportunity, [snapshot]))
        return compiled


class GitHubIssueAdapter(SourceAdapter):
    name = "github-issues"

    def compile_issue(self, issue: dict[str, Any]) -> Opportunity:
        content = json.dumps(issue, sort_keys=True).encode()
        labels = {str(item.get("name", "")).lower() for item in issue.get("labels", [])}
        repository_url = issue.get("repository_url", "").replace("api.github.com/repos", "github.com")
        issuer = repository_url.removeprefix("https://github.com/") or "GitHub repository"
        snapshot = snapshot_from_response(url=issue["html_url"], content=content, content_type="application/json", http_status=200, source_type="official", document_role="issue", issuer=issuer, title=issue.get("title"))
        requirements = [f"Resolve the scoped GitHub issue: {issue.get('title', '')}"]
        if labels:
            requirements.append("Work within issue labels: " + ", ".join(sorted(labels)))
        opportunity = Opportunity(
            id=f"github_{issue['id']}", title=issue.get("title", "GitHub opportunity"),
            type="bounty" if any("bounty" in label or "reward" in label for label in labels) else "other",
            issuer=issuer, summary=(issue.get("body") or "")[:1500],
            value=OpportunityValue(currency="USD", originalText="Check issue for reward terms"),
            requirements=requirements, preferredCapabilities=sorted(labels), sourceUrl=issue["html_url"],
            applicationUrl=issue["html_url"], sourceTimestamp=issue.get("updated_at", datetime.now(timezone.utc).isoformat()),
            sourceType="official", applicationEffort="medium", competitiveIntensity="unknown", status="open",
        )
        return compile_opportunity(opportunity, [snapshot], programme=issuer, track=f"issue-{issue.get('number', issue['id'])}")

    def compile(self, *, url: str, content: bytes, content_type: str, source_type: str) -> list[Opportunity]:
        payload = json.loads(content)
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        return [self.compile_issue(issue) for issue in items if isinstance(issue, dict)]


class OfficialHtmlAdapter(SourceAdapter):
    name = "official-html"

    def compile(self, *, url: str, content: bytes, content_type: str, source_type: str) -> list[Opportunity]:
        text = content.decode("utf-8", errors="replace")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
        title = unescape(re.sub(r"<[^>]+>", " ", title_match.group(1))).strip() if title_match else "Untitled opportunity"
        visible = unescape(re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", text, flags=re.I | re.S))
        visible = re.sub(r"<[^>]+>", " ", visible)
        visible = re.sub(r"\s+", " ", visible).strip()
        deadline_match = re.search(r"(?:deadline|closes?|submit by)\D{0,25}(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", visible, flags=re.I)
        deadline = deadline_match.group(1).replace("/", "-") if deadline_match else None
        snapshot = snapshot_from_response(url=url, content=content, content_type=content_type, http_status=200, source_type="official", document_role="announcement", title=title)
        requirements = []
        for statement in re.findall(r"(?:must|required to|requirements?[:])\s*([^.;]{12,220})", visible, flags=re.I):
            cleaned = statement.strip(" :-")
            if cleaned and cleaned not in requirements:
                requirements.append(cleaned)
        opportunity = Opportunity(
            id=f"html_{sha256_digest({'url': url, 'title': title})[:16]}", title=title,
            type="other", issuer="Unknown issuer", summary=visible[:1200], deadline=deadline,
            requirements=requirements[:20], sourceUrl=url, applicationUrl=url,
            sourceTimestamp=datetime.now(timezone.utc), sourceType="official", status="open",
        )
        compiled = compile_opportunity(opportunity, [snapshot], programme=title)
        if not requirements:
            compiled.intelligence.reviewReasons.append("No explicit requirements extracted from HTML")
            compiled.intelligence.dossierStatus = "review_required"
        return [compiled]
