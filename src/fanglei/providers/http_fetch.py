"""Bounded direct HTTP document fetcher; search snippets are never returned as evidence."""

from __future__ import annotations

import ipaddress
import http.client
import socket
import ssl
from urllib.parse import urljoin, urlparse
from datetime import datetime
from html.parser import HTMLParser

from fanglei.errors import ProviderError
from fanglei.research import FetchedDocument


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
            current_url = url
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
                raw = response.read(self.max_bytes + 1)
                charset = response.headers.get_content_charset() or "utf-8"
                connection.close()
                break
            else:
                raise ValueError("too many redirects")
            if len(raw) > self.max_bytes:
                raise ValueError("document exceeds size limit")
            parser = _TextParser()
            parser.feed(raw.decode(charset, errors="replace"))
            text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
            if not text:
                raise ValueError("no readable page text")
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(f"Source fetch failed (retryable): {url}: {error}") from error
        final_url = current_url
        host = urlparse(final_url).hostname or ""
        source_type = self._classify_source_type(host)
        return FetchedDocument(
            source_id, final_url, title, text, source_type, None,
            datetime.now().astimezone().isoformat(timespec="seconds"), None,
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
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        connection.request("GET", path, headers={"User-Agent": "fanglei-research-bot/0.2", "Accept": "text/html,text/plain"})
        return connection.getresponse(), connection

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
