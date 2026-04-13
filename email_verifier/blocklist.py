"""
Static blocklist - downloads and merges 3 GitHub sources at startup.
"""

import concurrent.futures
import requests

from email_verifier.config import Config


class StaticBlocklist:
    def __init__(self):
        self.domains = self._load()

    @staticmethod
    def _fetch_source(source: dict) -> set:
        try:
            response = requests.get(source["url"], timeout=Config.LIST_TIMEOUT)
            response.raise_for_status()

            if source["format"] == "json":
                import json
                raw = json.loads(response.text)
                domains = {d.strip().lower() for d in raw if isinstance(d, str) and d.strip()}
            else:
                domains = {
                    line.strip().lower()
                    for line in response.text.splitlines()
                    if line.strip() and not line.startswith("#")
                }

            print(f"[INIT] ✓ {len(domains):>7} domains  ← {source['name']}")
            return domains

        except Exception as e:
            print(f"[INIT] ✗ Skipped (error: {e})  ← {source['name']}")
            return set()

    def _load(self) -> set:
        print("[INIT] Loading blocklists concurrently from 3 GitHub sources …")
        merged: set = set()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(self._fetch_source, src): src
                for src in Config.BLOCKLIST_SOURCES
            }
            for future in concurrent.futures.as_completed(futures):
                merged |= future.result()

        if merged:
            print(f"[INIT] ✅ {len(merged):>7} unique disposable domains loaded (3 sources merged)")
            return merged

        print(f"[INIT] ⚠️  All GitHub sources unreachable → using built-in fallback list")
        return Config.FALLBACK_BLOCKLIST

    def contains(self, domain: str) -> bool:
        return domain.lower() in self.domains