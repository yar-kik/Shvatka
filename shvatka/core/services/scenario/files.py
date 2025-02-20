from typing import BinaryIO, Sequence

from shvatka.core.interfaces.clients.file_storage import FileGateway
from shvatka.core.interfaces.dal.complex import GamePackager
from shvatka.core.interfaces.dal.game import GameUpserter
from shvatka.core.models import dto
from shvatka.core.models.dto import scn
from shvatka.core.utils.exceptions import NotAuthorizedForEdit


async def upsert_files(
    author: dto.Player,
    contents: dict[str, BinaryIO],
    files: list[scn.UploadedFileMeta],
    dao: GameUpserter,
    file_gateway: FileGateway,
) -> set[str]:
    guids = set()
    for file in files:
        await dao.check_author_can_own_guid(author, file.guid)
        await file_gateway.put(file, contents[file.guid], author)
        guids.add(file.guid)
    return guids


async def get_file_metas(
    game: dto.FullGame, author: dto.Player, dao: GamePackager
) -> Sequence[scn.FileMeta]:
    file_metas: list[scn.FileMeta] = []
    for guid in game.get_guids():
        file_meta = await dao.get_by_guid(guid)
        check_file_meta_can_read(author, file_meta, game)
        file_metas.append(file_meta)
    return file_metas


async def get_file_contents(
    file_metas: Sequence[scn.FileMeta], file_gateway: FileGateway
) -> dict[str, BinaryIO]:
    contents = {}
    for file_meta in file_metas:
        content = await file_gateway.get(file_meta)
        contents[file_meta.guid] = content
    return contents


def check_file_meta_can_read(
    author: dto.Player, file_meta: scn.VerifiableFileMeta, game: dto.Game
):
    if game.is_complete():
        return
    if file_meta.author_id != author.id:
        raise NotAuthorizedForEdit(
            permission_name="file_edit",
            player=author,
            notify_user="невозможно открыть этот файл",
        )
