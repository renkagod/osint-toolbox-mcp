import asyncio
import json
import sys
from pathlib import Path

import pytest

from osint_toolbox_mcp import tools
from osint_toolbox_mcp.locate import Located
from osint_toolbox_mcp.process import Completed
from osint_toolbox_mcp.tools import TOOLS_BY_NAME, ToolError, limit_output

PROGRAM = Located(("tool",))


class FakeRunner:
    """Stands in for process.run: records each command and answers with `respond(command, cwd)`."""

    def __init__(self):
        self.commands: list[list[str]] = []
        self.respond = lambda command, cwd: Completed(0, "", "")

    async def __call__(self, command, cwd=None):
        self.commands.append(command)
        return self.respond(command, cwd)

    @property
    def arguments(self) -> list[str]:
        return self.commands[-1][1:]


@pytest.fixture
def runner(monkeypatch):
    fake = FakeRunner()
    monkeypatch.setattr(tools.process, "run", fake)
    return fake


def run_tool(name, arguments, located=PROGRAM):
    return asyncio.run(TOOLS_BY_NAME[name].run(arguments, located))


def option_value(arguments, option):
    return arguments[arguments.index(option) + 1]


# Input checks

@pytest.mark.parametrize("username", ["-x", "--output=/etc/passwd", "a\nb", "", "   ", 42, "x" * 300])
def test_bad_usernames_are_rejected(runner, username):
    with pytest.raises(ToolError):
        run_tool("sherlock_username_search", {"username": username})
    assert runner.commands == []


@pytest.mark.parametrize("timeout", [0, 601, True, "30", 1.5])
def test_bad_timeouts_are_rejected(runner, timeout):
    with pytest.raises(ToolError):
        run_tool("maigret_username_search", {"username": "alice", "timeout": timeout})


def test_integral_float_timeout_is_accepted(runner):
    runner.respond = lambda command, cwd: Completed(0, "", "")
    run_tool("blackbird_username_search", {"username": "alice", "timeout": 20.0}, Located(("python", "blackbird.py")))
    assert option_value(runner.arguments, "--timeout") == "20"


def test_failure_reports_exit_code_and_stderr(runner):
    runner.respond = lambda command, cwd: Completed(2, "", "boom\nreal reason")
    with pytest.raises(ToolError, match="exited with code 2:\nboom\nreal reason"):
        run_tool("phoneinfoga_scan", {"number": "+14155552671"})


@pytest.mark.skipif(sys.platform != "win32", reason=".bat/.cmd wrappers only matter on Windows")
def test_batch_wrappers_refuse_cmd_metacharacters(runner):
    with pytest.raises(ToolError, match="cmd.exe"):
        run_tool("holehe_email_search", {"email": "a&calc@example.com"}, Located(("C:\\tools\\holehe.cmd",)))
    assert runner.commands == []


def test_output_limit(monkeypatch):
    monkeypatch.setenv("OSINT_MAX_OUTPUT_CHARS", "10")
    assert limit_output("x" * 10) == "x" * 10
    limited = limit_output("x" * 25)
    assert limited.startswith("x" * 10 + "\n\n[Output truncated to 10 of 25 characters")


# Tools

def test_sherlock(runner):
    def respond(command, cwd):
        Path(option_value(command, "--folderoutput"), "alice.csv").write_text("username,url_user\nalice,https://github.com/alice\n")
        return Completed(0, "[+] GitHub: https://github.com/alice", "")

    runner.respond = respond
    result = run_tool("sherlock_username_search", {"username": "alice", "sites": ["GitHub"], "timeout": 15})
    arguments = runner.arguments
    assert arguments[0] == "alice"
    assert {"--no-color", "--print-found", "--csv", "--no-txt"} <= set(arguments)
    assert option_value(arguments, "--site") == "GitHub"
    assert option_value(arguments, "--timeout") == "15"
    assert result.startswith("alice.csv:\nusername,url_user")


def test_sherlock_txt_and_default_timeout(runner):
    run_tool("sherlock_username_search", {"username": "alice", "output_format": "txt"})
    assert "--csv" not in runner.arguments
    assert "--timeout" not in runner.arguments


def test_sherlock_rejects_option_like_sites(runner):
    with pytest.raises(ToolError):
        run_tool("sherlock_username_search", {"username": "alice", "sites": ["--output"]})


def test_holehe(runner):
    output = "Twitter : @palenath\n\n[+] github.com\n121 websites checked\nFor BTC Donations : 1FHD\n"
    runner.respond = lambda command, cwd: Completed(0, output, "")
    assert run_tool("holehe_email_search", {"email": "alice@example.com"}) == "[+] github.com\n121 websites checked"
    assert runner.arguments == ["alice@example.com", "--no-color", "--no-clear", "--only-used"]


def test_holehe_all_sites_with_timeout(runner):
    run_tool("holehe_email_search", {"email": "alice@example.com", "only_used": False, "timeout": 20})
    assert "--only-used" not in runner.arguments
    assert option_value(runner.arguments, "--timeout") == "20"


def test_holehe_needs_an_email(runner):
    with pytest.raises(ToolError, match="email address"):
        run_tool("holehe_email_search", {"email": "alice"})


def test_maigret_returns_the_accounts_from_its_report(runner):
    report = {
        "GitHub": {
            "url_user": "https://github.com/alice",
            "status": {"ids": {"fullname": "Alice"}, "tags": ["coding"], "url": "https://github.com/alice"},
            "site": {"checkType": "status_code", "headers": {}},
            "is_similar": False,
        }
    }

    def respond(command, cwd):
        Path(option_value(command, "--folderoutput"), "report_alice_simple.json").write_text(json.dumps(report))
        return Completed(0, "", "")

    runner.respond = respond
    result = json.loads(run_tool("maigret_username_search", {"username": "alice", "all_sites": True}))
    assert result == {"GitHub": {"url": "https://github.com/alice", "data": {"fullname": "Alice"}, "tags": ["coding"]}}
    assert option_value(runner.arguments, "--json") == "simple"
    assert "--all-sites" in runner.arguments


def test_maigret_nothing_found(runner):
    def respond(command, cwd):
        Path(option_value(command, "--folderoutput"), "report_alice_simple.json").write_text("{}")
        return Completed(0, "", "")

    runner.respond = respond
    assert run_tool("maigret_username_search", {"username": "alice"}) == "No accounts found for 'alice'."


def test_theharvester_returns_its_json_report(runner):
    def respond(command, cwd):
        Path(option_value(command, "-f") + ".json").write_text('{"hosts": ["www.example.com"]}')
        return Completed(0, "banner", "")

    runner.respond = respond
    result = run_tool("theharvester_domain_search", {"domain": "example.com", "sources": "crtsh,hackertarget"})
    assert json.loads(result) == {"hosts": ["www.example.com"]}
    assert option_value(runner.arguments, "-b") == "crtsh,hackertarget"
    assert option_value(runner.arguments, "-l") == "500"


@pytest.mark.parametrize("sources", ["crtsh;rm -rf", "crtsh,", "a b"])
def test_theharvester_rejects_bad_sources(runner, sources):
    with pytest.raises(ToolError):
        run_tool("theharvester_domain_search", {"domain": "example.com", "sources": sources})


def test_spiderfoot_groups_events(runner):
    events = [
        {"type": "Internet Name", "data": "www.example.com", "module": "sfp_a"},
        {"type": "Internet Name", "data": "www.example.com", "module": "sfp_b"},
        {"type": "IP Address", "data": "93.184.216.34", "module": "sfp_a"},
    ]
    # What sf.py really prints: the scan process's events first, the main process's brackets last
    output = ",\n".join(json.dumps(event) for event in events) + "[]\n"
    runner.respond = lambda command, cwd: Completed(0, output, "")
    located = Located(("python", "sf.py"), cwd="/opt/spiderfoot")
    result = run_tool("spiderfoot_scan", {"target": "example.com", "use_case": "passive"}, located)
    assert json.loads(result) == {"Internet Name": ["www.example.com"], "IP Address": ["93.184.216.34"]}
    assert runner.commands[-1] == ["python", "sf.py", "-s", "example.com", "-u", "passive", "-o", "json", "-q"]


def test_spiderfoot_reads_a_well_formed_array_too(runner):
    runner.respond = lambda command, cwd: Completed(0, '[{"type": "Country Name", "data": "Spain"}]', "")
    assert json.loads(run_tool("spiderfoot_scan", {"target": "example.com"})) == {"Country Name": ["Spain"]}
    assert option_value(runner.arguments, "-u") == "all"


def test_spiderfoot_keeps_output_it_cannot_parse(runner):
    runner.respond = lambda command, cwd: Completed(0, "[{broken", "")
    assert run_tool("spiderfoot_scan", {"target": "example.com"}) == "[{broken"


def test_spiderfoot_found_nothing(runner):
    runner.respond = lambda command, cwd: Completed(0, "[]\n", "")
    assert run_tool("spiderfoot_scan", {"target": "example.com"}) == "SpiderFoot found nothing for 'example.com'."


def test_spiderfoot_rejects_unknown_use_case(runner):
    with pytest.raises(ToolError, match="use_case"):
        run_tool("spiderfoot_scan", {"target": "example.com", "use_case": "everything"})


@pytest.mark.parametrize(("identifier", "mode"), [("alice@gmail.com", "email"), ("117492842498221023473", "gaia")])
def test_ghunt_modes(runner, identifier, mode):
    def respond(command, cwd):
        Path(option_value(command, "--json")).write_text('{"profile": {"name": "Alice"}}')
        return Completed(0, "banner", "")

    runner.respond = respond
    assert json.loads(run_tool("ghunt_google_search", {"identifier": identifier})) == {"profile": {"name": "Alice"}}
    assert runner.arguments[:2] == [mode, identifier]


def test_ghunt_without_a_report_returns_its_status_lines(runner):
    output = '  .d8888b.  888\n  "Y8888P88 888\n\n🎉 You are up to date !\n\n[+] Authenticated !\n\n[-] The target wasn\'t found.\n'
    runner.respond = lambda command, cwd: Completed(0, output, "")
    result = run_tool("ghunt_google_search", {"identifier": "nobody@gmail.com"})
    assert result == "[+] Authenticated !\n[-] The target wasn't found."


def test_ghunt_rejects_other_identifiers(runner):
    with pytest.raises(ToolError):
        run_tool("ghunt_google_search", {"identifier": "alice"})


@pytest.mark.parametrize(
    "error",
    [
        "GHuntInvalidSession: Please generate a new session by doing => ghunt login",
        "GHuntAndroidAppOAuth2Error: Expected \"Expiry\" in the response.\nThe master token may be revoked.",
    ],
)
def test_ghunt_without_a_valid_login(runner, error):
    runner.respond = lambda command, cwd: Completed(1, "", error)
    with pytest.raises(ToolError, match="run `ghunt login`"):
        run_tool("ghunt_google_search", {"identifier": "alice@gmail.com"})


def test_blackbird_drops_its_banner(runner):
    output = "\n    ▄▄▄▄    ██▓\n    ░▒▓███▀▒░\n             Made with love | by Lucas\n\n  ✔️  [GitHub] https://github.com/alice\n"
    runner.respond = lambda command, cwd: Completed(0, output, "")
    result = run_tool("blackbird_username_search", {"username": "alice"}, Located(("python", "blackbird.py")))
    assert result == "✔️  [GitHub] https://github.com/alice"
    assert runner.commands[-1] == ["python", "blackbird.py", "-u", "alice"]


@pytest.mark.parametrize("number", ["+14155552671", "+7 (911) 222-33-44"])
def test_phoneinfoga(runner, number):
    run_tool("phoneinfoga_scan", {"number": number})
    assert runner.arguments == ["scan", "-n", number]


@pytest.mark.parametrize("number", ["call me", "+1", "12345678901234567890123456789012345"])
def test_phoneinfoga_rejects_non_numbers(runner, number):
    with pytest.raises(ToolError):
        run_tool("phoneinfoga_scan", {"number": number})


def test_exiftool(runner, tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"")
    runner.respond = lambda command, cwd: Completed(0, json.dumps([{"FileName": "photo.jpg", "Artist": "Alice"}]), "")
    assert json.loads(run_tool("exiftool_metadata", {"file_path": str(photo)})) == {"FileName": "photo.jpg", "Artist": "Alice"}
    assert runner.arguments == ["-j", str(photo)]


@pytest.mark.skipif(sys.platform != "win32", reason="the ANSI code page problem is Windows-only")
def test_exiftool_non_ascii_name_goes_through_an_argument_file(runner, tmp_path):
    photo = tmp_path / "фото.jpg"
    photo.write_bytes(b"")
    run_tool("exiftool_metadata", {"file_path": str(photo)})
    assert runner.arguments[:3] == ["-charset", "filename=utf8", "-@"]


def test_exiftool_needs_an_existing_absolute_path(runner, tmp_path):
    with pytest.raises(ToolError, match="absolute"):
        run_tool("exiftool_metadata", {"file_path": "photo.jpg"})
    with pytest.raises(ToolError, match="no such file"):
        run_tool("exiftool_metadata", {"file_path": str(tmp_path / "missing.jpg")})


def test_subfinder(runner):
    output = "\n".join([
        '{"host":"www.example.com","input":"example.com","sources":["crtsh","hackertarget"]}',
        '{"host":"API.example.com","input":"example.com","source":"alienvault"}',
        "not json",
    ])
    runner.respond = lambda command, cwd: Completed(0, output, "")
    result = json.loads(run_tool("subfinder_subdomain_search", {"domain": "Example.com", "all_sources": True, "timeout": 20}))
    assert result == {
        "domain": "example.com",
        "subdomains": {"api.example.com": ["alienvault"], "www.example.com": ["crtsh", "hackertarget"]},
    }
    assert runner.arguments[:2] == ["-d", "example.com"]
    assert {"-silent", "-oJ", "-cs", "-nc", "-all"} <= set(runner.arguments)
    assert option_value(runner.arguments, "-timeout") == "20"


def test_subfinder_rejects_non_domains(runner):
    with pytest.raises(ToolError, match="domain"):
        run_tool("subfinder_subdomain_search", {"domain": "not a domain"})


def test_dnstwist(runner):
    entries = [
        {"fuzzer": "*original", "domain": "example.com", "dns_a": ["93.184.215.14"]},
        {"fuzzer": "bitsquatting", "domain": "exampme.com", "dns_a": ["1.2.3.4"], "dns_mx": ["mx.exampme.com"]},
    ]
    runner.respond = lambda command, cwd: Completed(0, json.dumps(entries), "")
    result = json.loads(run_tool("dnstwist_lookalike_domains", {"domain": "example.com"}))
    assert result["lookalikes"] == [{"domain": "exampme.com", "fuzzer": "bitsquatting", "a": ["1.2.3.4"], "mx": ["mx.exampme.com"]}]
    assert runner.arguments == ["--format", "json", "--registered", "example.com"]


def test_dnsrecon(runner):
    def respond(command, cwd):
        records = [{"type": "ScanInfo", "arguments": "..."}, {"type": "A", "name": "example.com", "address": "1.2.3.4"}]
        Path(option_value(command, "-j")).write_text(json.dumps(records))
        return Completed(0, "", "")

    runner.respond = respond
    result = json.loads(run_tool("dnsrecon_domain_scan", {"domain": "example.com", "scan_type": "axfr"}))
    assert result == [{"type": "A", "name": "example.com", "address": "1.2.3.4"}]
    assert runner.arguments[:4] == ["-d", "example.com", "-t", "axfr"]


def test_status_lists_whats_missing(isolated_tools):
    from conftest import fake_executable

    fake_executable(isolated_tools, "sherlock")
    report = run_tool("osint_toolbox_status", {}, None)
    assert "sherlock_username_search" in report.split("Not installed")[0]
    assert "whois_lookup" in report.split("Not installed")[0]
    assert "- maigret_username_search (maigret)" in report
    assert "uvx osint-toolbox-mcp --install maigret" in report
