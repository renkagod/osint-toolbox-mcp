"""Lookups the server makes itself over the network: nothing to install and no API keys."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import urllib.parse
from typing import Any

from . import web
from .inputs import ToolError, choice, domain, flag, integer, text


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)


async def _get_json(url: str, **options: Any) -> Any:
    try:
        return await asyncio.to_thread(web.fetch_json, url, **options)
    except web.WebError as error:
        raise ToolError(str(error)) from error


# WHOIS: RDAP first, the WHOIS protocol (port 43) for registries without RDAP, like .ru

async def whois_lookup(arguments: dict[str, Any], located: Any = None) -> str:
    query = text(arguments, "query")
    kind, value = _rdap_target(query)
    try:
        data = await asyncio.to_thread(
            web.fetch_json,
            f"https://rdap.org/{kind}/{urllib.parse.quote(value, safe='/:')}",
            headers={"Accept": "application/rdap+json"},
            timeout=40,
        )
    except web.WebError as error:
        if kind != "domain" or error.status not in (404, None):
            raise ToolError(str(error)) from error
        return await asyncio.to_thread(_whois, value)
    return _json(_rdap_summary(data))


def _rdap_target(query: str) -> tuple[str, str]:
    """RDAP object class and value: an IP address or network, an AS number, or a domain."""
    candidate = query.strip()
    try:
        if "/" in candidate:
            return "ip", str(ipaddress.ip_network(candidate, strict=False))
        return "ip", str(ipaddress.ip_address(candidate))
    except ValueError:
        pass
    asn = re.fullmatch(r"(?i)(?:AS)?(\d{1,10})", candidate)
    if asn:
        return "autnum", asn.group(1)
    return "domain", domain({"query": candidate}, "query")


def _rdap_summary(data: dict[str, Any]) -> dict[str, Any]:
    keys = ("ldhName", "unicodeName", "handle", "name", "type", "country", "startAddress", "endAddress",
            "startAutnum", "endAutnum", "status")
    summary: dict[str, Any] = {key: data[key] for key in keys if data.get(key)}
    events = {event.get("eventAction"): event.get("eventDate") for event in data.get("events", []) if isinstance(event, dict)}
    if events:
        summary["events"] = events
    nameservers = [ns.get("ldhName") for ns in data.get("nameservers", []) if isinstance(ns, dict) and ns.get("ldhName")]
    if nameservers:
        summary["nameservers"] = nameservers
    if isinstance(data.get("secureDNS"), dict):
        summary["dnssec"] = bool(data["secureDNS"].get("delegationSigned"))
    contacts = [_rdap_entity(entity) for entity in data.get("entities", []) if isinstance(entity, dict)]
    if contacts:
        summary["contacts"] = contacts
    return summary


def _rdap_entity(entity: dict[str, Any]) -> dict[str, Any]:
    contact: dict[str, Any] = {"roles": entity.get("roles", [])}
    if entity.get("handle"):
        contact["handle"] = entity["handle"]
    vcard = entity.get("vcardArray")
    if isinstance(vcard, list) and len(vcard) == 2 and isinstance(vcard[1], list):
        for field in vcard[1]:
            if not (isinstance(field, list) and len(field) >= 4):
                continue
            name, params, value = field[0], field[1], field[3]
            if name in ("fn", "org", "email", "tel") and value:
                contact[name] = value
            elif name == "adr":
                label = params.get("label") if isinstance(params, dict) else None
                contact["address"] = label or " ".join(str(part) for part in _flatten(value) if part)
    nested = [_rdap_entity(child) for child in entity.get("entities", []) if isinstance(child, dict)]
    if nested:
        contact["contacts"] = nested
    return contact


def _flatten(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for part in value for item in _flatten(part)]
    return [value]


def _whois(name: str) -> str:
    """Plain WHOIS: ask IANA which server knows the TLD, then ask that server."""
    answer = _whois_query("whois.iana.org", name)
    referral = re.search(r"^(?:refer|whois):\s*(\S+)", answer, re.MULTILINE | re.IGNORECASE)
    if referral:
        answer = _whois_query(referral.group(1), name)
    lines = [line.rstrip() for line in answer.splitlines() if line.strip() and not line.lstrip().startswith(("%", "#", ">>>"))]
    return "RDAP has no record for this domain; WHOIS answer:\n\n" + "\n".join(lines)


def _whois_query(server: str, query: str) -> str:
    try:
        with web.open_socket(server, 43, timeout=20) as sock:
            sock.sendall(query.encode("idna") + b"\r\n")
            chunks = []
            while chunk := sock.recv(65536):
                chunks.append(chunk)
    except OSError as error:
        raise ToolError(f"WHOIS server {server} could not be reached: {error}") from error
    return b"".join(chunks).decode("utf-8", errors="replace")


# DNS over HTTPS

DNS_TYPES = {"A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "PTR": 12, "MX": 15, "TXT": 16, "AAAA": 28, "SRV": 33,
             "DS": 43, "DNSKEY": 48, "CAA": 257}
DEFAULT_DNS_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "CAA")


async def dns_lookup(arguments: dict[str, Any], located: Any = None) -> str:
    name = text(arguments, "name")
    types = arguments.get("types") or list(DEFAULT_DNS_TYPES)
    if not isinstance(types, list) or not all(isinstance(kind, str) and kind.upper() in DNS_TYPES for kind in types):
        raise ToolError(f"'types' must be a list of record types: {', '.join(DNS_TYPES)}")
    try:
        name = ipaddress.ip_address(name).reverse_pointer
        types = ["PTR"]
    except ValueError:
        name = domain({"name": name}, "name")
    answers = await asyncio.gather(*(asyncio.to_thread(_resolve, name, kind.upper()) for kind in types))
    if any(answer is None for answer in answers):
        return f"{name} does not exist (NXDOMAIN)."
    records = {kind.upper(): answer for kind, answer in zip(types, answers) if answer}
    return _json({"name": name, "records": records}) if records else f"No DNS records found for {name}."


def _resolve(name: str, kind: str) -> list[str] | None:
    """Record data from Cloudflare's resolver, or Google's: both speak the same JSON API. None for NXDOMAIN."""
    query = urllib.parse.urlencode({"name": name, "type": kind})
    error: web.WebError | None = None
    for resolver in ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"):
        try:
            data = web.fetch_json(f"{resolver}?{query}", headers={"Accept": "application/dns-json"}, timeout=20)
        except web.WebError as failure:
            error = failure
            continue
        if data.get("Status") == 3:
            return None
        return [answer["data"] for answer in data.get("Answer", []) if answer.get("type") == DNS_TYPES[kind]]
    raise ToolError(f"DNS lookup failed: {error}")


# Certificate transparency

async def crtsh_certificate_search(arguments: dict[str, Any], located: Any = None) -> str:
    name = domain(arguments, "domain")
    query = {"q": f"%.{name}", "output": "json"}
    if not flag(arguments, "include_expired", True):
        query["exclude"] = "expired"
    url = f"https://crt.sh/?{urllib.parse.urlencode(query)}"
    try:
        certificates = await asyncio.to_thread(web.fetch_json, url, timeout=90)
    except web.WebError:
        # crt.sh often fails under load; one retry usually gets through
        await asyncio.sleep(3)
        certificates = await _get_json(url, timeout=90)
    entries = {entry.strip().lower() for certificate in certificates
               for entry in str(certificate.get("name_value", "")).splitlines() if entry.strip()}
    # Certificates also name email addresses and, in test certificates, free text
    hostnames = sorted(entry for entry in entries if _HOSTNAME.fullmatch(entry) and entry.endswith(name))
    emails = sorted(entry for entry in entries if "@" in entry and " " not in entry)
    if not hostnames and not emails:
        return f"crt.sh has no certificates for {name} or its subdomains."
    result: dict[str, Any] = {"domain": name, "certificates": len(certificates), "hostnames": hostnames}
    if emails:
        result["emails"] = emails
    return _json(result)


_HOSTNAME = re.compile(r"(\*\.)?([a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?\.)*[a-z0-9-]{1,63}")


# Wayback Machine

async def wayback_snapshots(arguments: dict[str, Any], located: Any = None) -> str:
    target = text(arguments, "url", max_length=2048)
    match = choice(arguments, "match", ("exact", "prefix", "host", "domain"), "exact")
    limit = integer(arguments, "limit", 1, 1000) or 50
    query = {"url": target, "output": "json", "matchType": match, "collapse": "digest",
             "fl": "timestamp,original,statuscode,mimetype", "limit": str(-limit)}
    for key in ("from", "to"):
        value = text(arguments, key, required=False, max_length=14)
        if value:
            if not re.fullmatch(r"\d{4,14}", value):
                raise ToolError(f"'{key}' must be a date like 2019 or 20190131")
            query[key] = value
    rows = await _get_json(f"https://web.archive.org/cdx/search/cdx?{urllib.parse.urlencode(query)}", timeout=60)
    entries = rows[1:] if rows else []
    if not entries:
        return f"The Wayback Machine has no snapshots of {target}."
    snapshots = [
        {"time": time, "status": status, "type": mimetype, "url": f"https://web.archive.org/web/{time}/{original}"}
        for time, original, status, mimetype in reversed(entries)
    ]
    return _json({"url": target, "newest_first": snapshots})
