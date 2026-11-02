"""Bounded HTML extraction with redirect and DNS-rebinding SSRF protection.

Only public HTTP(S) hosts on ports 80/443 are allowed. We validate *all*
resolved addresses, then open a socket to a validated numeric address while
retaining the original Host header, SNI and certificate verification hostname.
No proxy environment variables or cookies are used.
"""

import http.client
import ipaddress
import os
import re
import socket
import ssl
import time
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup
import certifi


class ExtractionError(ValueError):
    pass


MAX_BYTES = 3_000_000
MAX_TEXT = 100_000
SOCKET_TIMEOUT = 12
TOTAL_TIMEOUT = 30


def validate_url(url: str):
    try:
        if any(ord(char) < 33 for char in url) or "\\" in url:
            raise ExtractionError("链接包含无效字符")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ExtractionError("仅支持完整的 http:// 或 https:// 链接")
        if parsed.username is not None or parsed.password is not None:
            raise ExtractionError("链接不能包含用户名或密码")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in (80, 443):
            raise ExtractionError("仅允许使用 80 或 443 端口")
        host = parsed.hostname.encode("idna").decode("ascii")
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (ValueError, UnicodeError, OSError) as exc:
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError("链接无效或域名无法解析") from exc
    validated = []
    for family, _, _, _, address in addresses:
        ip = ipaddress.ip_address(address[0].split("%", 1)[0])
        def public_address(value):
            return value.is_global and not any((value.is_multicast, value.is_reserved, value.is_unspecified, value.is_loopback, value.is_link_local))

        if not public_address(ip) or (getattr(ip, "ipv4_mapped", None) and not public_address(ip.ipv4_mapped)):
            raise ExtractionError("为保护本机安全，不允许抓取内网、保留或本机地址")
        pair = (family, address)
        if pair not in validated:
            validated.append(pair)
    if not validated:
        raise ExtractionError("域名没有可用的公网地址")
    return parsed, validated


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, family, address, *, tls: bool, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self.family = family
        self.address = address
        self.tls = tls

    def connect(self):
        raw_socket = socket.socket(self.family, socket.SOCK_STREAM)
        raw_socket.settimeout(self.timeout)
        try:
            raw_socket.connect(self.address)
            if self.tls:
                context = ssl.create_default_context(cafile=os.getenv("SSL_CERT_FILE") or certifi.where())
                self.sock = context.wrap_socket(raw_socket, server_hostname=self.host)
            else:
                self.sock = raw_socket
        except Exception:
            raw_socket.close()
            raise


def _fetch(url: str) -> tuple[bytes, str]:
    started = time.monotonic()
    for _ in range(6):
        parsed, addresses = validate_url(url)
        if time.monotonic() - started >= TOTAL_TIMEOUT:
            raise ExtractionError("抓取超时，请改为粘贴正文")
        family, address = addresses[0]
        host = parsed.hostname.encode("idna").decode("ascii")
        connection = _PinnedHTTPConnection(
            host, parsed.port or (443 if parsed.scheme == "https" else 80), family, address,
            tls=parsed.scheme == "https", timeout=min(SOCKET_TIMEOUT, TOTAL_TIMEOUT - (time.monotonic() - started)),
        )
        try:
            path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
            if parsed.query:
                path += "?" + quote(parsed.query, safe="%/?@!$&'()*+,;=:-._~")
            connection.request("GET", path, headers={
                "User-Agent": "ReadingAssistant/1.0 (personal article reader)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                "Accept-Encoding": "identity",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ExtractionError("网页重定向缺少目标地址")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ExtractionError(f"网页返回 HTTP {response.status}，请改为粘贴正文")
            content_type = response.getheader("Content-Type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
                raise ExtractionError("该链接不是可读取的 HTML 或纯文本文章")
            if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
                raise ExtractionError("网页使用不支持的压缩格式，请改为粘贴正文")
            try:
                declared_length = int(response.getheader("Content-Length", "0"))
            except ValueError:
                declared_length = 0
            if declared_length > MAX_BYTES:
                raise ExtractionError("网页过大，请改为粘贴正文（最多 100000 字符）")
            chunks, size = [], 0
            while True:
                remaining = TOTAL_TIMEOUT - (time.monotonic() - started)
                if remaining <= 0:
                    raise ExtractionError("抓取超时，请改为粘贴正文")
                if connection.sock:
                    connection.sock.settimeout(min(SOCKET_TIMEOUT, remaining))
                chunk = response.read(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ExtractionError("网页过大，请改为粘贴正文")
            return b"".join(chunks), content_type
        except ExtractionError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise ExtractionError("无法读取网页，请检查链接或改为粘贴正文") from exc
        finally:
            connection.close()
    raise ExtractionError("网页重定向次数过多")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return "\n\n".join(re.sub(r"[ \t]+", " ", part).strip() for part in re.split(r"\n\s*\n", text) if part.strip())


def paragraphs(text: str) -> list[str]:
    """IDs in prompts and frontend source view share blank-line segmentation."""
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def fetch_article(url: str) -> tuple[str, str]:
    body, content_type = _fetch(url)
    charset = re.search(r"charset=([^;\s]+)", content_type)
    if "text/plain" in content_type:
        try:
            text = body.decode(charset.group(1).strip('"\'') if charset else "utf-8", errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        title = text.splitlines()[0].strip()[:150] if text.strip() else "导入文章"
    else:
        soup = BeautifulSoup(body, "html.parser", from_encoding=charset.group(1) if charset else None)
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(" ", strip=True)[:300] if title_tag else urlsplit(url).hostname
        for tag in soup.select("script,style,noscript,nav,header,footer,aside,form,iframe,svg"):
            tag.decompose()
        candidates = soup.select("article, main, [role='main']")
        if candidates:
            container = max(candidates, key=lambda element: len(element.get_text(" ", strip=True)))
        else:
            container = soup.body or soup
        parts = [element.get_text(" ", strip=True) for element in container.select("p,h1,h2,h3,h4,li,blockquote,pre")]
        text = "\n\n".join(parts) if parts else container.get_text("\n\n", strip=True)
    text = normalize_text(text)
    if len(text) < 20:
        raise ExtractionError("未能提取正文；动态网页、付费墙或登录文章请直接粘贴正文")
    if len(text) > MAX_TEXT:
        raise ExtractionError("正文超过 100000 字符，请拆分后粘贴")
    return str(title or "导入文章"), text
