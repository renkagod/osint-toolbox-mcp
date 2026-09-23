# OSINT tools

Личный набор для OSINT: MCP-сервер, через который агенты (Claude Code, Antigravity) запускают OSINT-утилиты, и настройка этих утилит на машине.

## Что здесь
- `osint-tools-mcp-server/` — MCP-сервер (stdio). Основа — [frishtik/osint-tools-mcp-server](https://github.com/frishtik/osint-tools-mcp-server) на коммите `6a64661` (MIT). Доработки: запросы выполняются параллельно, есть отмена и `ping`, утилиты не наследуют stdin сервера, добавлены PhoneInfoga и ExifTool, пути прописаны под `D:\Coding`.
- `.agents/mcp_config.json` — подключение сервера для Antigravity.
- `patches/` — локальные правки сторонних утилит.
- `opt/`, `reports/` и `logs/` в git не хранятся: утилиты ставятся заново (см. ниже), а результаты сканов могут содержать персональные данные.

## Установка утилит
Пути прописаны в `osint-tools-mcp-server/src/osint_tools_mcp_server.py`, поэтому репозиторий должен лежать в `D:\Coding\Projects\OSINT`.

| Утилита | Как поставить |
|---|---|
| Sherlock, Holehe, Maigret, GHunt, theHarvester | `D:\Coding\Python\python.exe -m pip install sherlock-project==0.16.0 holehe==1.61 maigret==0.6.1 ghunt==2.3.4 theHarvester==4.11.1` |
| SpiderFoot | `git clone https://github.com/smicallef/spiderfoot opt/spiderfoot`, коммит `0f815a20`, затем в `opt/spiderfoot`: `git apply ../../patches/spiderfoot-requirements.patch` и `pip install -r requirements.txt` |
| Blackbird | `git clone https://github.com/p1ngul1n0/blackbird opt/blackbird`, коммит `b455050` |
| PhoneInfoga 2.11.0 | релиз с [sundowndev/phoneinfoga](https://github.com/sundowndev/phoneinfoga/releases), `phoneinfoga.exe` положить в `D:\Coding\Python\Scripts` |
| ExifTool 13.59 | [exiftool.org](https://exiftool.org), распаковать в `D:\Coding\ExifTool` |

## Подключение к агентам
- Утилиты ходят в сеть через локальный прокси Throne `socks5h://127.0.0.1:2080` (переменные `*_PROXY` в конфиге).
- Antigravity читает `.agents/mcp_config.json`.
- Claude Code, только для этой папки: из неё выполнить `claude mcp add-json --scope local osint-tools '<JSON сервера osint-tools из .agents/mcp_config.json>'`.
