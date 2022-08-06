from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.dao import BaseDAO
from app.models import db, dto
from app.models.dto.scn.game import GameScenario
from app.models.enums import GameStatus


class GameDao(BaseDAO[db.Game]):
    def __init__(self, session: AsyncSession):
        super().__init__(db.Game, session)

    async def upsert_game(
        self,
        author: dto.Player,
        scn: GameScenario,
    ) -> dto.Game:
        try:
            game = await self.get_by_author_and_scn(author, scn)
        except NoResultFound:
            game = db.Game(
                author_id=author.id,
                name=scn.name,
                status=GameStatus.underconstruction,
            )
            self.save(game)
        await self.flush(game)
        return dto.Game.from_db(game, author)

    async def get_by_author_and_scn(self, author: dto.Player, scn: GameScenario) -> db.Game:
        result = await self.session.execute(
            select(db.Game).where(
                db.Game.name == scn.name,
                db.Game.author_id == author.id,
            )
        )
        return result.scalar_one()
