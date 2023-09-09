from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from shvatka.core.models import dto
from shvatka.core.utils.datetime_utils import tz_utc
from shvatka.infrastructure.db import models
from .base import BaseDAO


class LevelTimeDao(BaseDAO[models.LevelTime]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(models.LevelTime, session)

    async def set_to_level(
        self, team: dto.Team, game: dto.Game, level_number: int, at: datetime | None = None
    ):
        if at is None:
            at = datetime.now(tz=tz_utc)
        level_time = models.LevelTime(
            game_id=game.id,
            team_id=team.id,
            level_number=level_number,
            start_at=at,
        )
        self._save(level_time)

    async def is_team_on_level(self, team: dto.Team, level: dto.Level) -> bool:
        assert level.game_id is not None
        return (
            await self._get_current(team.id, level.game_id)
        ).level_number == level.number_in_game

    async def get_current_level(self, team: dto.Team, game: dto.Game) -> int:
        return (await self.get_current_level_time(team=team, game=game)).level_number

    async def get_current_level_time(self, team: dto.Team, game: dto.Game) -> dto.LevelTime:
        db: models.LevelTime = await self._get_current(team.id, game.id)
        return db.to_dto(team=team, game=game)

    async def _get_current(self, team_id: int, game_id: int) -> models.LevelTime:
        result = await self.session.execute(
            select(models.LevelTime)
            .where(
                models.LevelTime.team_id == team_id,
                models.LevelTime.game_id == game_id,
            )
            .order_by(models.LevelTime.level_number.desc())
            .limit(1)
        )
        return result.scalar_one()

    async def get_game_level_times(self, game: dto.Game) -> list[dto.LevelTime]:
        result = await self.session.scalars(
            select(models.LevelTime)
            .where(models.LevelTime.game_id == game.id)
            .options(
                joinedload(models.LevelTime.team)
                .joinedload(models.Team.captain)
                .joinedload(models.Player.user),
                joinedload(models.LevelTime.team)
                .joinedload(models.Team.captain)
                .joinedload(models.Player.forum_user),
                joinedload(models.LevelTime.team).joinedload(models.Team.chat),
                joinedload(models.LevelTime.team).joinedload(models.Team.forum_team),
            )
            .order_by(
                models.LevelTime.team_id,
                models.LevelTime.level_number,
            )
        )
        return [
            lt.to_dto(
                game=game,
                team=lt.team.to_dto_chat_prefetched(),
            )
            for lt in result.all()
        ]

    async def get_game_level_times_by_teams(
        self, game: dto.Game, levels_count: int
    ) -> dict[dto.Team, list[dto.LevelTimeOnGame]]:
        level_times = await self.get_game_level_times(game)
        result: dict[dto.Team, list[dto.LevelTimeOnGame]] = {}
        for lt in level_times:
            result.setdefault(lt.team, []).append(lt.to_on_game(levels_count))
        return result

    async def replace_team_levels(self, primary: dto.Team, secondary: dto.Team):
        await self.session.execute(
            update(models.LevelTime)
            .where(models.LevelTime.team_id == secondary.id)
            .values(team_id=primary.id)
        )
