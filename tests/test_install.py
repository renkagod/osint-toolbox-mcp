import asyncio
import hashlib
import io
import sys
import tarfile
import zipfile

import pytest
from conftest import fake_executable

from osint_toolbox_mcp import install
from osint_toolbox_mcp.install import InstallError


def zip_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    return buffer.getvalue()


def tar_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            bundle.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_checksum_listing():
    listing = b"abc123  tool_linux_amd64.zip\ndef456  tool_windows_amd64.zip\n"
    assert install._checksum(listing, "tool_windows_amd64.zip") == "def456"
    assert install._checksum(listing, "tool_macOS_arm64.zip") is None


def test_verify():
    data = b"binary"
    install._verify(data, hashlib.sha256(data).hexdigest(), "tool.zip")
    with pytest.raises(InstallError, match="checksum mismatch"):
        install._verify(data, "0" * 64, "tool.zip")
    with pytest.raises(InstallError, match="no published checksum"):
        install._verify(data, None, "tool.zip")


@pytest.mark.parametrize("make", [zip_archive, tar_archive])
def test_unpack_strips_the_top_folder(tmp_path, make):
    target = tmp_path / "spiderfoot"
    target.mkdir()
    (target / "stale.txt").write_text("from an older install")
    install._unpack(make({"spiderfoot-abc/sf.py": b"print()", "spiderfoot-abc/modules/a.py": b""}), target, strip_root=True)
    assert (target / "sf.py").read_bytes() == b"print()"
    assert (target / "modules" / "a.py").is_file()
    assert not (target / "stale.txt").exists()


@pytest.mark.parametrize("name", ["../evil.py", "/etc/evil", "C:/evil.py"])
def test_unpack_refuses_paths_outside_the_target(tmp_path, name):
    with pytest.raises(InstallError, match="outside"):
        install._unpack(zip_archive({name: b""}), tmp_path / "target", strip_root=False)


def test_extract_one(tmp_path):
    archive = tar_archive({"README.md": b"", "phoneinfoga": b"\x7fELF"})
    install._extract_one(archive, "phoneinfoga", tmp_path / "bin" / "phoneinfoga")
    assert (tmp_path / "bin" / "phoneinfoga").read_bytes() == b"\x7fELF"
    with pytest.raises(InstallError):
        install._extract_one(archive, "subfinder", tmp_path / "bin" / "subfinder")


@pytest.mark.parametrize(
    ("machine", "arch"), [("x86_64", "amd64"), ("AMD64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64")]
)
def test_platform(monkeypatch, machine, arch):
    monkeypatch.setattr(install.platform, "machine", lambda: machine)
    assert install._platform()[1] == arch


def test_platform_without_a_build(monkeypatch):
    monkeypatch.setattr(install.platform, "machine", lambda: "riscv64")
    with pytest.raises(InstallError):
        install._platform()


def test_phoneinfoga_release(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "_platform", lambda: ("linux", "amd64"))
    archive = tar_archive({"phoneinfoga": b"binary"})
    files = {
        "phoneinfoga_Linux_x86_64.tar.gz": archive,
        "phoneinfoga_checksums.txt": f"{hashlib.sha256(archive).hexdigest()}  phoneinfoga_Linux_x86_64.tar.gz\n".encode(),
    }

    async def fake_release(repository):
        return {"tag_name": "v2.11.0", "assets": [{"name": name, "browser_download_url": name} for name in files]}

    monkeypatch.setattr(install, "_release", fake_release)
    monkeypatch.setattr(install.web, "fetch", lambda url, **options: files[url])
    assert "v2.11.0" in asyncio.run(install._phoneinfoga(tmp_path))
    assert (tmp_path / "bin" / "phoneinfoga").read_bytes() == b"binary"


def test_run_installs_only_whats_missing(monkeypatch, capsys, isolated_tools):
    fake_executable(isolated_tools, "sherlock")
    installed, checked = [], []

    async def fake_install(tool, home):
        installed.append(tool.label)
        if tool.label == "exiftool":
            raise InstallError("needs Perl")
        return "done"

    async def fake_check(labels):
        checked.append(labels)
        return 0

    monkeypatch.setattr(install, "_install", fake_install)
    monkeypatch.setattr(install.check, "run", fake_check)
    assert asyncio.run(install.run(["sherlock", "maigret", "exiftool"])) == 1
    output = capsys.readouterr().out
    assert installed == ["maigret", "exiftool"]
    assert checked == [["sherlock", "maigret", "exiftool"]]
    assert "already installed" in output and "failed: needs Perl" in output


def test_run_rejects_unknown_tools(capsys):
    assert asyncio.run(install.run(["nmap"])) == 2
    assert "Unknown tool: nmap" in capsys.readouterr().out


def test_run_refuses_inside_the_container(monkeypatch):
    monkeypatch.setattr(install, "IN_CONTAINER", True)
    assert asyncio.run(install.run([])) == 1


def test_uv_tool_uses_python_3_12(monkeypatch):
    commands = []

    async def fake_run(command, cwd=None):
        commands.append(command)
        return install.process.Completed(0, "", "")

    monkeypatch.setenv("UV", sys.executable)
    monkeypatch.setattr(install.process, "run", fake_run)
    assert "ghunt login" in asyncio.run(install._uv_tool("ghunt"))
    assert commands == [[sys.executable, "tool", "install", "--python", "3.12", "ghunt"]]


def test_github_packages_install_the_latest_release(monkeypatch):
    commands = []

    async def fake_run(command, cwd=None):
        commands.append(command)
        return install.process.Completed(0, "", "")

    async def fake_release(repository):
        return {"tag_name": "4.11.1"}

    monkeypatch.setenv("UV", "uv")
    monkeypatch.setattr(install.process, "run", fake_run)
    monkeypatch.setattr(install, "_release", fake_release)
    asyncio.run(install._uv_tool("theharvester"))
    requirement = "theHarvester @ https://github.com/laramies/theHarvester/archive/refs/tags/4.11.1.zip"
    assert commands == [["uv", "tool", "install", "--python", "3.12", requirement]]


def test_dnstwist_gets_only_the_extras_it_uses(monkeypatch):
    commands = []

    async def fake_run(command, cwd=None):
        commands.append(command)
        return install.process.Completed(0, "", "")

    monkeypatch.setenv("UV", "uv")
    monkeypatch.setattr(install.process, "run", fake_run)
    asyncio.run(install._uv_tool("dnstwist"))
    assert commands[0][-7:] == ["dnstwist", "--with", "dnspython", "--with", "tld", "--with", "idna"]
