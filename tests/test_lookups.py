import asyncio
import json

import pytest

from osint_toolbox_mcp import lookups, web
from osint_toolbox_mcp.inputs import ToolError


@pytest.fixture
def answers(monkeypatch):
    """Canned JSON per URL prefix instead of the network; records every URL asked for."""
    canned: dict[str, object] = {}
    asked: list[str] = []

    def fake_fetch_json(url, **options):
        asked.append(url)
        for prefix, answer in canned.items():
            if url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise web.WebError(f"unexpected request {url}")

    monkeypatch.setattr(web, "fetch_json", fake_fetch_json)
    canned["asked"] = asked
    return canned


def run(coroutine):
    return asyncio.run(coroutine)


RDAP_DOMAIN = {
    "ldhName": "EXAMPLE.COM",
    "status": ["client transfer prohibited"],
    "events": [{"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"}],
    "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}],
    "secureDNS": {"delegationSigned": True},
    "entities": [
        {
            "roles": ["registrar"],
            "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "RESERVED-Internet Assigned Numbers Authority"]]],
            "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["email", {}, "text", "abuse@iana.org"]]]}],
        }
    ],
}


def test_whois_domain_summary(answers):
    answers["https://rdap.org/domain/example.com"] = RDAP_DOMAIN
    result = json.loads(run(lookups.whois_lookup({"query": "https://Example.com/path"})))
    assert result["ldhName"] == "EXAMPLE.COM"
    assert result["events"] == {"registration": "1995-08-14T04:00:00Z"}
    assert result["nameservers"] == ["A.IANA-SERVERS.NET"]
    assert result["dnssec"] is True
    registrar = result["contacts"][0]
    assert registrar["fn"] == "RESERVED-Internet Assigned Numbers Authority"
    assert registrar["contacts"] == [{"roles": ["abuse"], "email": "abuse@iana.org"}]


@pytest.mark.parametrize(
    ("query", "url"),
    [
        ("8.8.8.8", "https://rdap.org/ip/8.8.8.8"),
        ("2001:db8::1", "https://rdap.org/ip/2001:db8::1"),
        ("192.0.2.0/24", "https://rdap.org/ip/192.0.2.0/24"),
        ("AS13335", "https://rdap.org/autnum/13335"),
        ("13335", "https://rdap.org/autnum/13335"),
    ],
)
def test_whois_other_objects(answers, query, url):
    answers[url] = {"handle": "X"}
    assert json.loads(run(lookups.whois_lookup({"query": query}))) == {"handle": "X"}


def test_whois_falls_back_to_port_43_without_rdap(answers, monkeypatch):
    answers["https://rdap.org/domain/"] = web.WebError("rdap.org answered HTTP 404", 404)
    queries = []

    def fake_whois_query(server, query):
        queries.append(server)
        if server == "whois.iana.org":
            return "% IANA WHOIS\nrefer:        whois.tcinet.ru\n"
        return "% TCI Whois\ndomain:        EXAMPLE.RU\nregistrar:     RU-CENTER-RU\n"

    monkeypatch.setattr(lookups, "_whois_query", fake_whois_query)
    result = run(lookups.whois_lookup({"query": "example.ru"}))
    assert queries == ["whois.iana.org", "whois.tcinet.ru"]
    assert "registrar:     RU-CENTER-RU" in result
    assert "% TCI" not in result


def test_whois_rejects_junk(answers):
    with pytest.raises(ToolError):
        run(lookups.whois_lookup({"query": "not a domain"}))


def test_dns_records(answers):
    answers["https://cloudflare-dns.com/dns-query?name=example.com&type=MX"] = {
        "Status": 0,
        "Answer": [{"type": 5, "data": "alias.example.com."}, {"type": 15, "data": "10 mail.example.com."}],
    }
    answers["https://cloudflare-dns.com/dns-query?name=example.com&type=TXT"] = {"Status": 0}
    result = json.loads(run(lookups.dns_lookup({"name": "example.com", "types": ["mx", "TXT"]})))
    assert result == {"name": "example.com", "records": {"MX": ["10 mail.example.com."]}}


def test_dns_reverse_lookup_and_fallback_resolver(answers):
    answers["https://cloudflare-dns.com/"] = web.WebError("cloudflare-dns.com could not be reached")
    answers["https://dns.google/resolve?name=1.1.1.1.in-addr.arpa&type=PTR"] = {
        "Status": 0,
        "Answer": [{"type": 12, "data": "one.one.one.one."}],
    }
    result = json.loads(run(lookups.dns_lookup({"name": "1.1.1.1"})))
    assert result["records"] == {"PTR": ["one.one.one.one."]}


def test_dns_nxdomain(answers):
    answers["https://cloudflare-dns.com/"] = {"Status": 3}
    assert "does not exist" in run(lookups.dns_lookup({"name": "nope.example.com", "types": ["A"]}))


def test_dns_rejects_unknown_types(answers):
    with pytest.raises(ToolError):
        run(lookups.dns_lookup({"name": "example.com", "types": ["ANY"]}))


def test_crtsh_splits_hostnames_and_emails(answers):
    answers["https://crt.sh/?q=%25.example.com&output=json&exclude=expired"] = [
        {"name_value": "example.com\nwww.example.com"},
        {"name_value": "*.example.com\nuser@example.com"},
        {"name_value": "Test Intermediate - example.com"},
        {"name_value": "www.example.com"},
    ]
    result = json.loads(run(lookups.crtsh_certificate_search({"domain": "example.com", "include_expired": False})))
    assert result == {
        "domain": "example.com",
        "certificates": 4,
        "hostnames": ["*.example.com", "example.com", "www.example.com"],
        "emails": ["user@example.com"],
    }


def test_wayback_newest_first(answers):
    answers["https://web.archive.org/cdx/search/cdx?"] = [
        ["timestamp", "original", "statuscode", "mimetype"],
        ["20190101000000", "https://example.com/", "200", "text/html"],
        ["20240101000000", "https://example.com/", "200", "text/html"],
    ]
    result = json.loads(run(lookups.wayback_snapshots({"url": "example.com", "limit": 2, "from": "2019"})))
    assert [snapshot["time"] for snapshot in result["newest_first"]] == ["20240101000000", "20190101000000"]
    assert result["newest_first"][0]["url"] == "https://web.archive.org/web/20240101000000/https://example.com/"
    assert "limit=-2" in answers["asked"][0] and "from=2019" in answers["asked"][0]


def test_wayback_rejects_bad_dates(answers):
    with pytest.raises(ToolError, match="date"):
        run(lookups.wayback_snapshots({"url": "example.com", "to": "last year"}))
