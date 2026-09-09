"""Bounded direct HTTP document fetcher; search snippets are never returned as evidence."""

from __future__ import annotations

import ipaddress
import http.client
import json
import socket
import ssl
from urllib.parse import parse_qs, quote, urljoin, urlparse
from datetime import datetime
from html.parser import HTMLParser

from fanglei.errors import ProviderError
from fanglei.research import FetchedDocument
from fanglei.security import safe_error_message, sanitize_url


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer"}:
            self._ignored += 1
        if tag in {"p", "h1", "h2", "h3", "li", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data):
        if not self._ignored:
            self.parts.append(data)


class HttpDocumentFetcher:
    def __init__(self, timeout: int = 20, max_bytes: int = 2_000_000):
        self.timeout = timeout
        self.max_bytes = max_bytes

    def fetch(self, source_id: str, url: str, title: str) -> FetchedDocument:
        try:
            discovery_url = url
            official_data_url = self._official_data_url(url)
            current_url = official_data_url or url
            for _ in range(4):
                response, connection = self._request_once(current_url)
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    connection.close()
                    if not location:
                        raise ValueError("redirect has no Location header")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status >= 400:
                    raise ValueError(f"HTTP {response.status}")
                content_type = response.getheader("Content-Type", "")
                is_official_json = bool(official_data_url) and content_type.split(";", 1)[0].strip().lower() == "application/json"
                if not self._supports_content_type(content_type) and not is_official_json:
                    raise ValueError(f"unsupported Content-Type: {content_type or 'missing'}")
                raw = response.read(self.max_bytes + 1)
                charset = response.headers.get_content_charset() or "utf-8"
                connection.close()
                break
            else:
                raise ValueError("too many redirects")
            if len(raw) > self.max_bytes:
                raise ValueError("document exceeds size limit")
            decoded = raw.decode(charset, errors="replace")
            if official_data_url:
                text = self._world_bank_text(json.loads(decoded))
            else:
                parser = _TextParser()
                parser.feed(decoded)
                text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
            if not text:
                raise ValueError("no readable page text")
        except ProviderError as error:
            raise ProviderError(safe_error_message(error)) from None
        except Exception as error:
            raise ProviderError(
                f"Source fetch failed (retryable): {sanitize_url(url)}: {safe_error_message(error)}"
            ) from None
        final_url = current_url
        host = urlparse(final_url).hostname or ""
        source_type = self._classify_source_type(host)
        return FetchedDocument(
            source_id, discovery_url, title, text, source_type, None,
            datetime.now().astimezone().isoformat(timespec="seconds"), final_url if official_data_url else None,
        )

    def _request_once(self, url: str) -> tuple[http.client.HTTPResponse, http.client.HTTPConnection]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ProviderError(f"Source URL blocked: only public HTTP(S) targets are allowed: {url}")
        if parsed.hostname.lower() == "localhost":
            raise ProviderError(f"Source URL blocked: private target: {url}")
        try:
            default_port = 443 if parsed.scheme == "https" else 80
            addresses = [info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or default_port)]
        except OSError as error:
            raise ProviderError(f"Source fetch failed (retryable): DNS lookup: {url}: {error}") from error
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ProviderError(f"Source URL blocked: non-public target: {url}")
        selected_ip = addresses[0]
        port = parsed.port or default_port
        host = parsed.hostname

        if parsed.scheme == "https":
            context = ssl.create_default_context()
            class PinnedHTTPSConnection(http.client.HTTPSConnection):
                def connect(self):
                    raw = socket.create_connection((selected_ip, port), self.timeout)
                    self.sock = context.wrap_socket(raw, server_hostname=host)
            connection: http.client.HTTPConnection = PinnedHTTPSConnection(host, port, timeout=self.timeout)
        else:
            class PinnedHTTPConnection(http.client.HTTPConnection):
                def connect(self):
                    self.sock = socket.create_connection((selected_ip, port), self.timeout)
            connection = PinnedHTTPConnection(host, port, timeout=self.timeout)
        path = self._request_target(url)
        connection.request("GET", path, headers={"User-Agent": "fanglei-research-bot/0.2", "Accept": "text/html,text/plain,application/json"})
        return connection.getresponse(), connection

    @staticmethod
    def _official_data_url(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.hostname != "data.worldbank.org" or not parsed.path.startswith("/indicator/"):
            return None
        indicator = parsed.path.removeprefix("/indicator/").strip("/")
        locations = parse_qs(parsed.query).get("locations", [])
        if indicator != "NY.GDP.MKTP.KD.ZG" or not locations or locations[0].upper() not in {"US", "USA"}:
            return None
        return (
            "https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.KD.ZG"
            "?format=json&date=2020:2025&per_page=10"
        )

    @staticmethod
    def _world_bank_text(payload: object) -> str:
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
            raise ValueError("unexpected World Bank API response")
        lines: list[str] = []
        for row in payload[1]:
            if not isinstance(row, dict) or row.get("value") is None:
                continue
            country = row.get("country", {}).get("value", "United States")
            indicator = row.get("indicator", {}).get("value", "GDP growth (annual %)")
            raw_value = row["value"]
            rounded = f"{float(raw_value):.1f}"
            lines.append(
                f"World Bank reports {country} real GDP growth was {rounded}% in {row.get('date')} "
                f"for indicator {indicator} (raw value {raw_value})."
            )
        if not lines:
            raise ValueError("World Bank API returned no observations")
        return "\n".join(lines)

    @staticmethod
    def _request_target(url: str) -> str:
        parsed = urlparse(url)
        path = quote(parsed.path or "/", safe="/%:@")
        if parsed.query:
            path += f"?{quote(parsed.query, safe='=&%:@/?')}"
        return path

    @staticmethod
    def _supports_content_type(value: str) -> bool:
        media_type = value.split(";", 1)[0].strip().lower()
        return media_type in {"text/html", "text/plain", "application/xhtml+xml"}

    @staticmethod
    def _classify_source_type(host: str) -> str:
        host = host.lower().rstrip(".")
        organizations = ("worldbank.org", "imf.org", "oecd.org")
        government_suffixes = (".gov", ".gov.cn", ".gov.uk", ".gov.hk", ".gov.au", ".gov.sg", ".go.jp")
        if any(host == domain or host.endswith(f".{domain}") for domain in organizations):
            return "international_organization"
        if any(host.endswith(suffix) for suffix in government_suffixes):
            return "official"
        return "mainstream_media"
