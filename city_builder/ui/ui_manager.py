"""Менеджер интерфейса: собирает все элементы UI в одном месте.

Game общается только с UIManager, а не с каждой кнопкой по отдельности.
Главная задача UIManager — решить, кому достаётся событие:
интерфейсу или карте. Интерфейс всегда «выше» карты, поэтому
получает события первым.

Панель ресурсов (деньги, жители, скорость) — вверху слева, под ней — панель цели
и панель «Город» (энергия, вода, счастье, склад). При наведении на здание —
подсказка о нём (BuildingInfo).
Экран итогов (победа / банкротство) — поверх всего, когда игра закончилась.

Кнопки в правом верхнем углу:   [🗑] [☰] [⏻]
                                 снос меню выход

Панель строительства/сноса — внизу по центру, видна только в этих режимах.

Строительство и снос не могут быть включены одновременно:
выбор товара выключает снос, включение сноса выключает строительство.
"""

from __future__ import annotations

import pygame

from city_builder.config import (
    COLOR_UI_DANGER_HOVER,
    MENU_BUTTON_SIZE,
    UI_BUTTON_GAP,
    UI_MARGIN,
    VIEW_POWER,
    VIEW_TRAFFIC,
    VIEW_WATER,
)
from city_builder.construction.build_mode import BuildMode
from city_builder.construction.demolish_mode import DemolishMode
from city_builder.data.catalog import Catalog
from city_builder.economy.clock import GameClock
from city_builder.economy.economy import Economy
from city_builder.economy.goals import GoalTracker
from city_builder.render.images import ImageLibrary
from city_builder.ui.build_panel import BuildPanel
from city_builder.ui.building_info import BuildingInfo
from city_builder.ui.button import ICON_DEMOLISH, ICON_EXIT, ICON_MENU, Button
from city_builder.ui.city_panel import CityPanel
from city_builder.ui.end_screen import EndScreen
from city_builder.ui.goal_panel import GoalPanel
from city_builder.ui.level_banner import LevelBanner
from city_builder.ui.view_panel import ViewPanel
from city_builder.ui.menu import Menu
from city_builder.ui.resource_bar import ResourceBar

LEFT_BUTTON = 1


class UIManager:
    def __init__(self, screen_size: tuple[int, int], catalog: Catalog,
                 build_mode: BuildMode, demolish_mode: DemolishMode,
                 images: ImageLibrary, economy: Economy, clock: GameClock,
                 goals: GoalTracker) -> None:
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
        self.menu = Menu(screen_size, catalog, self._on_item_selected, images)

        self.build_panel = BuildPanel(screen_size, build_mode, demolish_mode)
        self.resource_bar = ResourceBar(economy, clock)
        self.goal_panel = GoalPanel(goals)
        self.view_panel = ViewPanel()
        self.level_banner = LevelBanner(screen_size, goals, catalog)
        self.menu.is_unlocked = goals.is_unlocked  # закрытые уровнем товары — с замком
        self.city_panel = CityPanel(economy)
        self.building_info = BuildingInfo(screen_size)
        self.end_screen = EndScreen(screen_size, goals, economy)

    @property
    def new_game_requested(self) -> bool:
        """Игрок нажал «Новая игра» на экране итогов — Game создаст мир заново."""
        return self.end_screen.new_game_requested

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
        """True, если интерфейс сейчас перекрывает игру (открыто меню или экран итогов).
        Тогда Game не обновляет управление картой."""
        return self.menu.is_open or self.end_screen.visible

    def is_mouse_over(self, pos: tuple[int, int]) -> bool:
        """Находится ли курсор над каким-то элементом интерфейса.
        Нужно, чтобы не подсвечивать клетку карты под кнопкой."""
        # any() — True, если хотя бы одна кнопка содержит курсор
        over_button = any(button.contains(pos) for button in self.buttons)
        over_panel = (self.build_panel.contains(pos) or self.resource_bar.contains(pos)
                      or self.goal_panel.contains(pos) or self.city_panel.contains(pos)
                      or self.view_panel.contains(pos))
        return over_button or over_panel or self.blocks_world

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Возвращает True, если событие обработано интерфейсом
        и до карты его доводить не нужно."""
        # Экран итогов — самый главный: пока он показан, всё остальное недоступно
        if self.end_screen.handle_event(event):
            if self.end_screen.quit_requested:
                self.quit_requested = True
            return True

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

        # Панель ресурсов тоже работает всегда: можно поставить паузу,
        # даже пока выбираешь товар в магазине
        if self.resource_bar.handle_event(event):
            return True
        # Режимы просмотра (кнопки и F5–F8) — тоже всегда
        if self.view_panel.handle_event(event):
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

    @property
    def view(self) -> str:
        """Текущий режим просмотра (обычный, свет, вода, пробки)."""
        return self.view_panel.view

    def update(self, mouse_pos: tuple[int, int], dt: float = 0.0) -> None:
        """Подсветка элементов под курсором, раскладка панелей, баннер уровня."""
        # Строим линию, трубу или светофор — сам включается нужный режим просмотра
        layer = self.build_mode.item.layer if self.build_mode.active and self.build_mode.item else None
        self.view_panel.auto_view = {"power": VIEW_POWER, "pipe": VIEW_WATER, "signal": VIEW_TRAFFIC}.get(layer or "")
        # Трубы можно сносить, только когда их видно (режим «Вода»)
        self.demolish_mode.show_pipes = self.view == VIEW_WATER
        # Кнопка сноса «горит», пока режим включён — видно, что он активен
        self.demolish_button.active = self.demolish_mode.active
        for button in self.buttons:
            button.update(mouse_pos)
        self.menu.update(mouse_pos)
        self.build_panel.update(mouse_pos)
        # Панель ресурсов не должна заезжать под кнопки в правом верхнем углу
        self.resource_bar.update(mouse_pos, max_right=self.demolish_button.rect.left - UI_BUTTON_GAP)
        # Панель цели — сразу под панелью ресурсов (её ширина меняется, а левый край — нет)
        self.goal_panel.update((self.resource_bar.rect.left, self.resource_bar.rect.bottom + 6))
        self.city_panel.update((self.goal_panel.rect.left, self.goal_panel.rect.bottom + 6))
        self.view_panel.update(mouse_pos, (self.city_panel.rect.left, self.city_panel.rect.bottom + 6))
        self.level_banner.update(dt)
        self.end_screen.update(mouse_pos)

    def draw(self, screen: pygame.Surface) -> None:
        # Порядок: панель строительства, меню (с затемнением — накроет панель),
        # потом панель ресурсов и кнопки в углу — чтобы они оставались яркими
        # поверх затемнения (деньги видно и во время покупок)
        self.build_panel.draw(screen)
        # Панель цели — под меню: на невысоком экране она иначе закрыла бы заголовок меню
        self.goal_panel.draw(screen)
        self.city_panel.draw(screen)
        self.view_panel.draw(screen)
        self.level_banner.draw(screen)
        self.building_info.draw(screen)  # подсказка о здании — над картой, но под меню
        self.menu.draw(screen)
        self.resource_bar.draw(screen)
        for button in self.buttons:
            button.draw(screen)
        # Экран итогов — поверх всего
        self.end_screen.draw(screen)
