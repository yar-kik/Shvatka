from dataclass_factory import Factory

from app.dao import GameDao
from app.dao.holder import HolderDao
from app.models import dto
from app.services.player import check_allow_be_author
from app.services.scenario.game_ops import load_game
from app.utils.exceptions import NotAuthorizedForEdit, AnotherGameIsActive


async def upsert_game(scn: dict, author: dto.Player, dao: HolderDao, dcf: Factory) -> dto.Game:
    check_allow_be_author(author)
    game_scn = load_game(scn, dcf)
    game = await dao.game.upsert_game(author, game_scn)
    await dao.level.unlink_all(game)
    levels = []
    for number, level in enumerate(game_scn.levels):
        saved_level = await dao.level.upsert(author, level, game, number)
        levels.append(saved_level)
    game.levels = levels
    await dao.commit()
    return game


async def get_authors_games(author: dto.Player, dao: GameDao) -> list[dto.Game]:
    check_allow_be_author(author)
    return await dao.get_all_by_author(author)


async def get_game(id_: int, author: dto.Player, dao: GameDao) -> dto.Game:
    return await dao.get_by_id(id_, author)


async def get_active(dao: GameDao) -> dto.Game:
    return await dao.get_active_game()


async def start_waivers(game: dto.Game, author: dto.Player, dao: GameDao):
    check_allow_be_author(author)
    check_is_author(game, author)
    await check_no_game_active(dao)
    await dao.start_waivers(game)
    await dao.commit()


async def check_no_game_active(dao: GameDao):
    if game := await dao.get_active_game():
        raise AnotherGameIsActive(
            game=game,
            game_status=game.status,
        )


def check_is_author(game: dto.Game, player: dto.Player):
    if not game.is_author_id(player.id):
        raise NotAuthorizedForEdit(permission_name="game_edit", player=player, game=game)
