"""Security regressions exercise DNS resolution and redirects without networking."""

import socket

import pytest

from backend import extraction


def resolve_to(monkeypatch, addresses):
    def fake_resolver(*_args, **_kwargs):
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
            for address in addresses
        ]

    monkeypatch.setattr(extraction.socket, "getaddrinfo", fake_resolver)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.2", "172.16.0.1", "192.168.1.1", "169.254.169.254",
    "0.0.0.0", "224.0.0.1", "192.0.2.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1",
])
def test_private_reserved_and_local_addresses_are_rejected(monkeypatch, address):
    resolve_to(monkeypatch, [address])
    with pytest.raises(extraction.ExtractionError):
        extraction.validate_url("https://article.example/read")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/read", "https://user:password@example.com/read",
    "http://example.com:8080/read", "https://example.com/\r\nInjected:header", "http://example.com\\@127.0.0.1",
])
def test_unsafe_url_shapes_fail_before_dns(monkeypatch, url):
    def unexpected_dns(*_args, **_kwargs):
        pytest.fail("Invalid input must not perform DNS lookup")

    monkeypatch.setattr(extraction.socket, "getaddrinfo", unexpected_dns)
    with pytest.raises(extraction.ExtractionError):
        extraction.validate_url(url)


def test_mixed_public_and_private_dns_answers_are_rejected(monkeypatch):
    resolve_to(monkeypatch, ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(extraction.ExtractionError):
        extraction.validate_url("https://article.example")


def test_connection_uses_vetted_numeric_address_without_second_dns_lookup(monkeypatch):
    connected = []

    class Socket:
        def settimeout(self, _timeout):
            pass

        def connect(self, address):
            connected.append(address)

        def close(self):
            pass

    def unexpected_dns(*_args, **_kwargs):
        pytest.fail("Pinned connection must not resolve the hostname again")

    monkeypatch.setattr(extraction.socket, "getaddrinfo", unexpected_dns)
    monkeypatch.setattr(extraction.socket, "socket", lambda *_args: Socket())
    connection = extraction._PinnedHTTPConnection(
        "article.example", 80, socket.AF_INET, ("93.184.216.34", 80), tls=False, timeout=1,
    )
    connection.connect()
    assert connected == [("93.184.216.34", 80)]


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = headers or {"Content-Type": "text/html"}
        self.body = body
        self.read_count = 0

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, count):
        self.read_count += 1
        chunk, self.body = self.body[:count], self.body[count:]
        return chunk


def install_responses(monkeypatch, responses):
    connections = []

    class Connection:
        sock = None

        def __init__(self, *_args, **_kwargs):
            self.response = responses[len(connections)]
            self.closed = False
            connections.append(self)

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return self.response

        def close(self):
            self.closed = True

    monkeypatch.setattr(extraction, "_PinnedHTTPConnection", Connection)
    return connections


def test_redirect_target_is_checked_before_any_second_connection(monkeypatch):
    def resolver(host, *_args, **_kwargs):
        address = "127.0.0.1" if host == "internal.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))]

    monkeypatch.setattr(extraction.socket, "getaddrinfo", resolver)
    connections = install_responses(monkeypatch, [FakeResponse(302, {"Location": "http://internal.example/secret"})])
    with pytest.raises(extraction.ExtractionError):
        extraction.fetch_article("https://article.example/read")
    assert len(connections) == 1
    assert connections[0].closed


def test_html_extraction_keeps_article_and_removes_navigation_scripts(monkeypatch):
    resolve_to(monkeypatch, ["93.184.216.34"])
    html = (
        "<html><head><title>备用标题</title></head><body><nav>广告导航</nav>"
        "<article><h1>阅读研究</h1><p>第一段正文介绍主动阅读如何帮助理解复杂问题。</p>"
        "<script>stealSecrets()</script><p>第二段正文指出，这个研究不能单独证明因果关系。</p></article>"
        "<footer>无关页脚</footer></body></html>"
    ).encode("utf-8")
    install_responses(monkeypatch, [FakeResponse(headers={"Content-Type": "text/html; charset=utf-8"}, body=html)])
    title, text = extraction.fetch_article("https://article.example/read")
    assert title == "阅读研究"
    assert "第一段正文" in text and "第二段正文" in text
    assert "广告导航" not in text and "stealSecrets" not in text and "无关页脚" not in text


def test_large_announced_response_is_rejected_without_downloading(monkeypatch):
    resolve_to(monkeypatch, ["93.184.216.34"])
    response = FakeResponse(headers={"Content-Type": "text/html", "Content-Length": str(extraction.MAX_BYTES + 1)})
    install_responses(monkeypatch, [response])
    with pytest.raises(extraction.ExtractionError):
        extraction.fetch_article("https://article.example/read")
    assert response.read_count == 0


def test_large_unannounced_stream_is_bounded(monkeypatch):
    resolve_to(monkeypatch, ["93.184.216.34"])
    response = FakeResponse(body=b"x" * (extraction.MAX_BYTES + 10))
    install_responses(monkeypatch, [response])
    with pytest.raises(extraction.ExtractionError):
        extraction.fetch_article("https://article.example/read")
    assert len(response.body) == 9
