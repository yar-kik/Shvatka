import asyncio
import logging
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from aiohttp import ClientSession, ClientConnectorError, ClientResponseError
from dataclass_factory import Factory
from lxml import etree

from infrastructure.crawler.auth import get_auth_cookie
from infrastructure.crawler.constants import GAME_URL_TEMPLATE, GAMES_URL
from shvatka.models.dto import scn
from shvatka.services.scenario.scn_zip import pack_scn

logger = logging.getLogger(__name__)


async def get_all_games() -> list[scn.ParsedCompletedGameScenario]:
    games = []
    async with ClientSession(cookies=await get_auth_cookie()) as session:
        for game_id in reversed(await get_games_ids(session)):
            await asyncio.sleep(1)
            html_text = await download(game_id, session)
            try:
                games.append(await GameParser(html_text, session=session).build())
            except (ValueError, AttributeError) as e:
                logger.error("cant parsed game %s", game_id, exc_info=e)
    return games


async def get_games_ids(session: ClientSession) -> list[int]:
    async with session.get(GAMES_URL) as resp:
        return list(range(120, 130))


async def download(game_id: int, session: ClientSession) -> str:
    async with session.get(GAME_URL_TEMPLATE.format(game_id=game_id)) as resp:
        return await resp.text(encoding="cp1251")


class GameParser:
    def __init__(self, html_str: str, *, session: ClientSession):
        self.html = etree.HTML(html_str, base_url="shvatka.ru")
        self.session = session
        self.id: int = 0
        self.name: str = ""
        self.start_at: datetime | None = None
        self.current_hint_parts: list[str] = []
        self.levels: list[scn.LevelScenario] = []
        self.hints: list[scn.BaseHint] = []
        self.time_hints: list[scn.TimeHint] = []
        self.level_number = 0
        self.keys: set[str] = set()
        self.time: int = 0
        self.files: dict[str, BinaryIO] = {}
        self.files_meta: list[scn.FileMetaLightweight] = []

    def parse_game_head(self):
        self.id = int(self.html.xpath("//div[@class='maintitle']/b")[0].text)
        logger.info("parsing game %s ...", self.id)
        self.name = self.html.xpath("//div[@class='maintitle']/b/a")[0].text
        started_at_text = self.html.xpath("//div[@class='maintitle']/b/span[@id='dt']")[0].text
        self.start_at = datetime.strptime(started_at_text, "%d.%m.%y в %H:%M")

    async def parse_scenario(self):
        scn_element, = self.html.xpath("//div[@id='sc']//div[@class='borderwrap']//tr[@class='ipbtable']/td")
        for element in scn_element.xpath("./*"):
            if element.tag == "center":
                prompt: tuple[str, ...] = element.xpath("./b")[0].text.split()
                if prompt[0] == "Уровень" and prompt[1].strip(".").isnumeric() and prompt[2] == "Ключ:":
                    if self.keys:  # if not - it's first level
                        self.build_level()
                    self.keys = {b.tail for b in element.xpath("./b")}
                    self.level_number = int(prompt[1].strip("."))
                    continue
            if element.tag == "b":
                if element.text and len(element.text.split()) == 4:
                    hint_caption, number, time, minutes_caption = element.text.split()  # type: str
                    if hint_caption == "Подсказка" and minutes_caption == "мин.)":
                        self.build_time_hint()
                        time = time.removeprefix("(")
                        self.time = int(time or -1)
                        continue
            if img_tags := element.xpath("descendant-or-self::img"):
                for img in img_tags:
                    self.build_current_hint()
                    guid = str(uuid.uuid4())
                    self.hints.append(scn.PhotoHint(file_guid=guid))
                    self.files[guid] = await self.download_content(img.get("src"))
                    self.files_meta.append(scn.FileMetaLightweight(
                        guid=guid,
                        original_filename=guid,
                        extension=".jpg",
                    ))
            if element.text:
                self.current_hint_parts.append(element.text)
            if element.tail:
                self.current_hint_parts.append(element.tail)
        self.build_level()

    async def download_content(self, url: str) -> BinaryIO:
        try:
            async with self.session.get(url.strip()) as resp:
                resp.raise_for_status()
                return BytesIO(await resp.content.read())
        except (ClientConnectorError, ClientResponseError) as e:
            logger.error("couldnt load content for url %s", url, exc_info=e)
            return BytesIO()

    def build_current_hint(self):
        if not self.current_hint_parts:
            return
        self.hints.append(scn.TextHint(text="\n".join(self.current_hint_parts)))
        self.current_hint_parts = []

    def build_time_hint(self):
        self.build_current_hint()
        self.time_hints.append(
            scn.TimeHint(time=self.time, hint=[
                *self.hints,
            ])
        )
        self.hints = []

    def build_level(self):
        self.build_time_hint()
        level = scn.LevelScenario(
            id=f"game_{self.id}:lvl_{self.level_number}",
            time_hints=self.time_hints,
            keys=self.keys,
        )
        self.levels.append(level)
        logger.debug("for game %s parsed level %s", self.id, self.level_number)
        self.time_hints = []
        self.keys = set()
        self.time = 0
        self.level_number = 0

    async def build(self) -> scn.ParsedCompletedGameScenario:
        self.parse_game_head()
        await self.parse_scenario()
        game = scn.ParsedCompletedGameScenario(
            id=self.id,
            name=self.name,
            start_at=self.start_at,
            levels=self.levels,
            files_contents=self.files,
            files=self.files_meta,
        )
        return game


async def save_all_scns_to_files():
    games = await get_all_games()
    dcf = Factory()
    path = Path() / "scn"
    path.mkdir(exist_ok=True)
    for game in games:
        dct = dcf.dump(game, scn.ParsedGameScenario)
        scenario = scn.RawGameScenario(scn=dct, files=game.files_contents)
        packed_scenario = pack_scn(scenario)
        with open(path / f"{game.id}.zip", "wb") as f:
            f.write(packed_scenario.read())


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(save_all_scns_to_files())
