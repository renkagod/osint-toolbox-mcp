import asyncio

from osint_toolbox_mcp import check
from osint_toolbox_mcp.locate import Located
from osint_toolbox_mcp.process import Completed


def fake_tools(monkeypatch, missing=(), failing=()):
    def fake_locate(requirement):
        env = getattr(requirement, "env", None) or requirement.dir_env
        return (None, f"{env} is not set") if env in missing else (Located((env,)), "")

    async def fake_run(command, cwd=None):
        return Completed(1, "", "Traceback\nImportError: boom") if command[0] in failing else Completed(0, "", "")

    monkeypatch.setattr(check, "locate", fake_locate)
    monkeypatch.setattr(check.process, "run", fake_run)


def test_everything_ready(monkeypatch, capsys):
    fake_tools(monkeypatch)
    assert asyncio.run(check.run()) == 0
    assert "12 of 12 tools ready." in capsys.readouterr().out


def test_missing_and_broken_tools(monkeypatch, capsys):
    fake_tools(monkeypatch, missing={"OSINT_SPIDERFOOT_DIR"}, failing={"OSINT_SHERLOCK"})
    assert asyncio.run(check.run()) == 1
    output = capsys.readouterr().out
    assert "missing  spiderfoot" in output
    assert "broken   sherlock" in output and "ImportError: boom" in output
    assert "10 of 12 tools ready." in output


def test_docker_image_does_not_count_tools_left_out_of_it(monkeypatch, capsys):
    monkeypatch.setattr(check, "IN_CONTAINER", True)
    fake_tools(monkeypatch, missing={"OSINT_BLACKBIRD_DIR"})
    assert asyncio.run(check.run()) == 0
    output = capsys.readouterr().out
    assert "absent   blackbird" in output
    assert "11 of 11 tools ready." in output
