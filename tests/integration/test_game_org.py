import pytest

from db.dao.holder import HolderDao
from shvatka.models import dto
from shvatka.services.organizers import get_orgs, get_spying_orgs, get_secondary_orgs, check_allow_add_orgs, \
    check_game_token, save_invite_to_orgs, dismiss_to_be_org, agree_to_be_org
from shvatka.utils.exceptions import SaltNotExist
from tests.mocks.org_notifier import OrgNotifierMock


@pytest.mark.asyncio
async def test_only_org(game: dto.FullGame, author: dto.Player, dao: HolderDao):
    orgs = await get_orgs(game, dao.organizer)
    assert 1 == len(orgs)
    assert author.id == orgs[0].player.id

    orgs = await get_spying_orgs(game, dao.organizer)
    assert 1 == len(orgs)
    assert author.id == orgs[0].player.id

    assert [] == await get_secondary_orgs(game, dao.organizer)

    check_allow_add_orgs(game, author.id)
    check_game_token(game, game.manage_token)


@pytest.mark.asyncio
async def test_dismiss_invite(game: dto.FullGame, author: dto.Player, dao: HolderDao):
    token = await save_invite_to_orgs(game, author, dao.secure_invite)
    assert {"game_id": game.id, "inviter_id": author.id} == await dao.secure_invite.get_invite(token)
    await dismiss_to_be_org(token, dao.secure_invite)
    with pytest.raises(SaltNotExist):
        await dao.secure_invite.get_invite(token)


@pytest.mark.asyncio
async def test_agree_invite(
    game: dto.FullGame, author: dto.Player, harry: dto.Player, dao: HolderDao,
):
    token = await save_invite_to_orgs(game, author, dao.secure_invite)
    org_notifier = OrgNotifierMock()  # TODO check actually invocations
    actual = await agree_to_be_org(
        token=token, inviter_id=author.id, player=harry, org_notifier=org_notifier, dao=dao.org_adder,
    )
    assert game.id == actual.game.id
    assert harry.id == actual.player.id
    assert not actual.can_spy
    assert not actual.can_see_log_keys
    assert not actual.can_validate_waivers
    assert not actual.deleted
