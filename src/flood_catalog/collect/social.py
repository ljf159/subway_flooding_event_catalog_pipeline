"""Social-media collectors: X (Twitter) and Weibo.

Both need authenticated API access (X API v2 is paid; Weibo needs a developer
account), so the live ``_fetch`` reads a token from the environment and raises a
clear error if it's missing. Stub mode reads a local fixture, so the offline demo
and tests run with no credentials. We store the post text + link, never bulk
archives, and respect each platform's Terms of Service and rate limits.
"""

from __future__ import annotations

import datetime as _dt
import os
import urllib.parse

from flood_catalog.collect._http import get_json
from flood_catalog.collect.base import CollectedItem, Collector, CollectionQuery


def _iso(raw: str | None) -> _dt.datetime | None:
    if not raw:
        return None
    try:
        return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:  # Weibo: "Wed Sep 01 12:00:00 +0800 2021"
            return _dt.datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            return None


class XCollector(Collector):
    platform = "x"
    _ENDPOINT = "https://api.twitter.com/2/tweets/search/recent"

    def __init__(self, stub: bool = True, fixture=None, token_env: str = "X_BEARER_TOKEN") -> None:
        super().__init__(stub=stub)
        self.fixture = fixture
        self.token_env = token_env

    def _stub_items(self, query: CollectionQuery) -> list[CollectedItem]:
        import json
        from pathlib import Path

        data = json.loads(Path(self.fixture).read_text()) if self.fixture else {}
        return self._parse(data)

    def _fetch(self, query: CollectionQuery) -> list[CollectedItem]:  # pragma: no cover
        token = os.environ.get(self.token_env)
        if not token:
            raise RuntimeError(
                f"X live collection needs a bearer token in ${self.token_env} "
                "(X API v2, paid). Run with stub=True to use the fixture."
            )
        q = " ".join(query.terms) or "subway flood"
        if query.lang:
            q += f" lang:{query.lang}"
        params = {
            "query": q,
            "max_results": str(max(10, min(query.limit, 100))),
            "tweet.fields": "created_at,lang,author_id",
            "expansions": "author_id",
            "user.fields": "username",
        }
        url = f"{self._ENDPOINT}?{urllib.parse.urlencode(params)}"
        return self._parse(get_json(url, headers={"Authorization": f"Bearer {token}"}))

    def _parse(self, data: dict) -> list[CollectedItem]:
        users = {u["id"]: u.get("username") for u in data.get("includes", {}).get("users", [])}
        items: list[CollectedItem] = []
        for t in data.get("data", []):
            uid = t.get("author_id")
            handle = users.get(uid, uid)
            url = f"https://x.com/{handle}/status/{t['id']}" if handle else ""
            items.append(
                CollectedItem(
                    platform=self.platform, source_url=url, external_id=t.get("id"),
                    author=handle, posted_at=_iso(t.get("created_at")),
                    text=t.get("text", ""), lang=t.get("lang"), raw=t,
                )
            )
        return items


class WeiboCollector(Collector):
    platform = "weibo"

    def __init__(
        self, stub: bool = True, fixture=None,
        endpoint: str = "https://api.weibo.com/2/search/statuses.json",
        token_env: str = "WEIBO_ACCESS_TOKEN",
    ) -> None:
        super().__init__(stub=stub)
        self.fixture = fixture
        self.endpoint = endpoint
        self.token_env = token_env

    def _stub_items(self, query: CollectionQuery) -> list[CollectedItem]:
        import json
        from pathlib import Path

        data = json.loads(Path(self.fixture).read_text()) if self.fixture else {}
        return self._parse(data)

    def _fetch(self, query: CollectionQuery) -> list[CollectedItem]:  # pragma: no cover
        token = os.environ.get(self.token_env)
        if not token:
            raise RuntimeError(
                f"Weibo live collection needs an access token in ${self.token_env} "
                "(Weibo Open API). The exact search endpoint depends on your API "
                "tier; pass endpoint=. Run with stub=True to use the fixture."
            )
        q = " ".join(query.terms) or "地铁 内涝"
        params = {"access_token": token, "q": q, "count": str(min(query.limit, 50))}
        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"
        return self._parse(get_json(url))

    def _parse(self, data: dict) -> list[CollectedItem]:
        items: list[CollectedItem] = []
        for s in data.get("statuses", []):
            user = s.get("user") or {}
            handle = user.get("screen_name")
            sid = str(s.get("id") or s.get("idstr") or "")
            url = f"https://weibo.com/{user.get('id', '')}/{sid}" if handle else ""
            items.append(
                CollectedItem(
                    platform=self.platform, source_url=url, external_id=sid,
                    author=handle, posted_at=_iso(s.get("created_at")),
                    text=s.get("text_raw") or s.get("text", ""),
                    lang=s.get("lang", "zh"), raw=s,
                )
            )
        return items
