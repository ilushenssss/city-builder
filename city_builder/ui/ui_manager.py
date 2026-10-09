"""Менеджер интерфейса: собирает все элементы UI в одном месте.

Game общается только с UIManager, а не с каждой кнопкой по отдельности.
Главная задача UIManager — решить, кому достаётся событие:
интерфейсу или карте. Интерфейс всегда «выше» карты, поэтому
получает события первым.

Кнопки в правом верхнем углу:   [🗑] [☰] [⏻]
                                 снос меню выход

Панель строительства/сноса — внизу по центру, видна только в этих режимах.

Строительство и снос не могут быть включены одновременно:
выбор товара выключает снос, включение сноса выключает строительство.
"""

import pygame

from city_builder.config import COLOR_UI_DANGER_HOVER, MENU_BUTTON_SIZE, UI_BUTTON_GAP, UI_MARGIN
from city_builder.construction.build_mode import BuildMode
from city_builder.construction.demolish_mode import DemolishMode
from city_builder.data.catalog import Catalog
from city_builder.ui.build_panel import BuildPanel
from city_builder.ui.button import ICON_DEMOLISH, ICON_EXIT, ICON_MENU, Button
from city_builder.ui.menu import Menu

LEFT_BUTTON = 1


class UIManager:
    def __init__(self, screen_size: tuple[int, int], catalog: Catalog,
                 build_mode: BuildMode, demolish_mode: DemolishMode) -> None:
        screen_w, _ = screen_size
        self.catalog = catalog
        self.build_mode = build_mode
        self.demolish_mode = demolish_mode
        # Game проверяет этот флаг и завершает игру (как InputHandler.quit_requested)
        self.quit_requested = False

        # Кнопки в углу — справа налево: выход, меню, снос.
        # Каждая следующая левее предыдущей на UI_BUTTON_GAP.
        exit_rect = pygame.Rect(0, 0, MENU_BUTTON_SIZE, MENU_BUTTON_SIZE)
        exit_rect.topright = (screen_w - UI_MARGIN, UI_MARGIN)
        self.exit_button = Button(exit_rect, ICON_EXIT, hover_color=COLOR_UI_DANGER_HOVER)

        menu_rect = pygame.Rect(0, 0, MENU_BUTTON_SIZE, MENU_BUTTON_SIZE)
        menu_rect.topright = (exit_rect.left - UI_BUTTON_GAP, UI_MARGIN)
        self.menu_button = Button(menu_rect, ICON_MENU)

        demolish_rect = pygame.Rect(0, 0, MENU_BUTTON_SIZE, MENU_BUTTON_SIZE)
        demolish_rect.topright = (menu_rect.left - UI_BUTTON_GAP, UI_MARGIN)
        self.demolish_button = Button(demolish_rect, ICON_DEMOLISH, hover_color=COLOR_UI_DANGER_HOVER)

        # Все кнопки панели в одном списке — удобно обновлять, рисовать и проверять курсор
        self.buttons = [self.demolish_button, self.menu_button, self.exit_button]

        # Каталог нужен, чтобы построить магазин. Последний аргумент — функция,
        # которую меню вызовет при клике по товару (обратите внимание: без скобок —
        # мы передаём саму функцию, а не вызываем её).
        self.menu = Menu(screen_size, catalog, self._on_item_selected)

        self.build_panel = BuildPanel(screen_size, build_mode, demolish_mode)

    def _on_item_selected(self, item_id: str) -> None:
        """Игрок кликнул по товару в магазине -> включаем режим строительства."""
        self.demolish_mode.cancel()  # строить и сносить одновременно нельзя
        self.build_mode.select(self.catalog.get_item(item_id))

    def _toggle_demolish(self) -> None:
        """Кнопка 🗑 или клавиша Delete: включить/выключить снос."""
        self.build_mode.cancel()  # строить и сносить одновременно нельзя
        self.demolish_mode.toggle()

    @property
    def blocks_world(self) -> bool:
        """True, если интерфейс сейчас перекрывает игру (открыто меню).
        Тогда Game не обновляет управление картой."""
        return self.menu.is_open

    def is_mouse_over(self, pos: tuple[int, int]) -> bool:
        """Находится ли курсор над каким-то элементом интерфейса.
        Нужно, чтобы не подсвечивать клетку карты под кнопкой."""
        # any() — True, если хотя бы одна кнопка содержит курсор
        over_button = any(button.contains(pos) for button in self.buttons)
        return over_button or self.build_panel.contains(pos) or self.blocks_world

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Возвращает True, если событие обработано интерфейсом
        и до карты его доводить не нужно."""
        # Кнопки в углу работают всегда, даже при открытом меню
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == LEFT_BUTTON:
            if self.exit_button.contains(event.pos):
                self.quit_requested = True
                return True
            if self.menu_button.contains(event.pos):
                self.menu.toggle()  # и чтобы открыть, и чтобы закрыть
                return True
            if self.demolish_button.contains(event.pos):
                self.menu.close()  # чтобы сразу было видно карту
                self._toggle_demolish()
                return True

        # Дальше событие получает меню (если оно открыто).
        # «or» останавливается на первом True: если меню съело событие, дальше оно не идёт.
        if self.menu.handle_event(event):
            return True

        # Горячая клавиша сноса (меню закрыто — иначе клавиши съело бы меню)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_DELETE:
            self._toggle_demolish()
            return True

        return self.build_panel.handle_event(event)

    def update(self, mouse_pos: tuple[int, int]) -> None:
        """Подсветка элементов под курсором."""
        # Кнопка сноса «горит», пока режим включён — видно, что он активен
        self.demolish_button.active = self.demolish_mode.active
        for button in self.buttons:
            button.update(mouse_pos)
        self.menu.update(mouse_pos)
        self.build_panel.update(mouse_pos)

    def draw(self, screen: pygame.Surface) -> None:
        # Порядок: панель строительства, меню (с затемнением — накроет панель),
        # потом кнопки в углу — чтобы они оставались яркими поверх затемнения
        self.build_panel.draw(screen)
        self.menu.draw(screen)
        for button in self.buttons:
            button.draw(screen)
