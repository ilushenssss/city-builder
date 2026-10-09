"""Главный объект игры: связывает мир, камеру, ввод и отрисовку.

Game — «дирижёр». Сам почти ничего не делает, а создаёт все части
и вызывает их в нужном порядке. Схема зависимостей:

    Game
     ├── Catalog       — база товаров магазина (из data/shop.json)
     ├── Grid          — данные карты (что где лежит)
     ├── Camera        — откуда мы смотрим на карту
     ├── InputHandler  — читает ввод, двигает Camera, ищет клетку в Grid
     ├── BuildMode     — строительство: выбранный товар, место, подтверждение
     ├── DemolishMode  — снос: выбор здания, подтверждение
     ├── Renderer      — рисует Grid через Camera (и призрак здания из BuildMode)
     ├── UIManager     — интерфейс поверх карты: кнопки, меню, панель строительства
     └── GameLoop      — крутит цикл и вызывает методы Game каждый кадр
"""

import sys

import pygame

from city_builder.config import (
    FPS,
    FULLSCREEN,
    GRID_HEIGHT,
    GRID_WIDTH,
    SHOP_DATA_FILE,
    TILE_SIZE,
    WINDOW_HEIGHT,
    WINDOW_TITLE,
    WINDOW_WIDTH,
)
from city_builder.construction.build_mode import BuildMode
from city_builder.construction.demolish_mode import DemolishMode
from city_builder.core.game_loop import GameLoop
from city_builder.data.catalog import load_catalog
from city_builder.input.input_handler import InputHandler
from city_builder.render.camera import Camera
from city_builder.render.renderer import Renderer
from city_builder.ui.ui_manager import UIManager
from city_builder.world.grid import Grid


def enable_dpi_awareness() -> None:
    """Сообщить Windows, что игра сама учитывает масштаб экрана (DPI).

    Если в настройках Windows включено масштабирование (например, 125% или 150%),
    без этого вызова система «обманывает» программу: вместо 1920x1080 сообщает
    1536x864, а потом растягивает картинку — и всё выглядит размытым.
    На других системах (macOS, Linux) функция ничего не делает.
    """
    if sys.platform != "win32":
        return
    import ctypes  # стандартный модуль для вызова функций Windows

    try:
        # Windows 8.1+: 2 = учитывать DPI каждого монитора отдельно
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # запасной вариант для старых Windows
        except (AttributeError, OSError):
            pass  # не получилось — не страшно, просто картинка может быть размытой


class Game:
    def __init__(self) -> None:
        # --- Данные ---
        # Каталог товаров загружаем первым: если в data/shop.json ошибка,
        # игра остановится с сообщением ещё до открытия окна (см. main.py).
        self.catalog = load_catalog(SHOP_DATA_FILE)

        # --- Запуск pygame и создание окна ---
        enable_dpi_awareness()  # обязательно ДО создания окна
        pygame.init()  # инициализирует все модули pygame (графика, шрифты, звук...)
        pygame.display.set_caption(WINDOW_TITLE)
        # set_mode создаёт окно и возвращает его поверхность для рисования
        if FULLSCREEN:
            # Размер (0, 0) означает «возьми текущее разрешение монитора»
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        # Реальный размер окна узнаём у самой поверхности — он мог выбраться автоматически
        screen_width, screen_height = self.screen.get_size()
        self.running = True  # пока True — игровой цикл крутится

        # --- Мир ---
        self.grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self.grid.generate()  # озеро и река; generate(seed=42) — всегда одна и та же карта

        # --- Камера ---
        # Размер мира в пикселях (при zoom = 1): клеток * TILE_SIZE
        world_width = self.grid.width * TILE_SIZE
        world_height = self.grid.height * TILE_SIZE
        self.camera = Camera(screen_width, screen_height, world_width, world_height)
        self.camera.center_on(world_width / 2, world_height / 2)  # старт — в центре карты

        # --- Ввод, отрисовка, цикл ---
        self.input = InputHandler(self.camera, self.grid)
        self.build = BuildMode(self.grid)
        self.demolish = DemolishMode(self.grid)
        self.renderer = Renderer(self.screen)
        self.ui = UIManager(self.screen.get_size(), self.catalog, self.build, self.demolish)
        self.loop = GameLoop(self, FPS)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Шаг 1 кадра: GameLoop передаёт сюда каждое событие pygame.

        Событие передаётся по цепочке, пока кто-то его не «съест»:
          1. интерфейс (кнопки, меню, панель строительства, клавиша Delete);
          2. режим строительства (клик по карте, Esc, Enter);
          3. режим сноса (клик по зданию, Esc, Enter);
          4. управление камерой (колесо, перетаскивание, Esc = выход).
        «or» вызывает следующего, только если предыдущий вернул False.
        Строительство и снос не включены одновременно, поэтому не мешают друг другу.
        """
        consumed = (self.ui.handle_event(event)
                    or self.build.handle_event(event)
                    or self.demolish.handle_event(event))
        if not consumed:
            self.input.handle_event(event)
        # Выйти можно с клавиатуры/крестика окна (input) или кнопкой выхода (ui)
        if self.input.quit_requested or self.ui.quit_requested:
            self.running = False  # цикл в GameLoop завершится

    def update(self, dt: float) -> None:
        """Шаг 2 кадра: обновление состояния. dt — секунды с прошлого кадра."""
        mouse_pos = pygame.mouse.get_pos()
        self.ui.update(mouse_pos)  # подсветка кнопок и карточек

        if self.ui.blocks_world:
            # Меню открыто — карту не двигаем и клетку не подсвечиваем
            self.input.hovered_tile = None
        else:
            self.input.update(dt)  # движение камеры с клавиатуры + клетка под курсором
            if self.ui.is_mouse_over(mouse_pos):
                self.input.hovered_tile = None  # курсор над кнопкой, а не над картой

        # Режим строительства пересчитывает, куда встанет здание и можно ли там строить
        self.build.update_hover(self.input.hovered_tile)
        # Режим сноса запоминает, какое здание под курсором
        self.demolish.update_hover(self.input.hovered_tile)

        self.camera.clamp()    # после всех движений не даём камере уехать с карты
        # На этапе 2 здесь появится тик экономики

    def draw(self) -> None:
        """Шаг 3 кадра: отрисовка. Порядок важен — то, что рисуется позже, оказывается сверху."""
        self.renderer.draw(self.grid, self.camera)  # карта и здания
        if self.build.active:
            self.renderer.draw_build_preview(self.build, self.camera)  # призрак здания
        elif self.demolish.active:
            self.renderer.draw_demolish_preview(self.demolish, self.camera)  # красная подсветка
        else:
            self.renderer.draw_hover(self.input.hovered_tile, self.camera)  # рамка клетки

        # Отладочная информация поверх всего
        tile = self.input.hovered_tile
        tile_info = f"{tile.x}, {tile.y} ({tile.type.value})" if tile else "-"
        if tile and tile.building:
            tile_info += f" — {tile.building.item.name}"
        self.renderer.draw_debug([
            f"FPS: {self.loop.current_fps:.0f}",
            f"Zoom: {self.camera.zoom:.2f}",
            f"Tile: {tile_info}",
        ])

        # Интерфейс рисуем последним — он всегда поверх карты
        self.ui.draw(self.screen)

    def run(self) -> None:
        """Запустить игру. Возвращается только после закрытия окна."""
        try:
            self.loop.run()
        finally:
            # finally выполнится даже при ошибке — окно корректно закроется
            pygame.quit()
