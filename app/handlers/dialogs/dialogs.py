from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from app.handlers.dialogs.getters import get_my_games, get_game
from app.handlers.dialogs.handlers import select_my_game
from app.states import MyGamesPanel

games = Dialog(
    Window(
        Const("Список игр твоего авторства"),
        ScrollingGroup(
            Select(
                Format("{item.name}"),
                id="my_games",
                item_id_getter=lambda x: x.id,
                items="games",
                on_click=select_my_game,
            ),
            id="my_games_sg",
            width=1,
            height=10,
        ),
        state=MyGamesPanel.choose_game,
        getter=get_my_games,
    ),
    Window(
        Format("Редактирование {game.name}"),
        SwitchTo(
            Const("Назад к списку игр"),
            id="to_my_games",
            state=MyGamesPanel.choose_game,
        ),
        state=MyGamesPanel.game_menu,
        getter=get_game,
    ),
)
