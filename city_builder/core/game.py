"""Главный объект игры: связывает мир, камеру, ввод и отрисовку.

Game — «дирижёр». Сам почти ничего не делает, а создаёт все части
и вызывает их в нужном порядке. Схема зависимостей:

    Game
     ├── Catalog       — база товаров магазина (из data/shop.json)
     ├── Grid          — данные карты (что где лежит)
     ├── Economy       — деньги, жители, тик экономики
     ├── GameClock     — игровое время: пауза, скорость, когда делать тик
     ├── GoalTracker   — цель игры, победа и поражение
     ├── CitizenManager — человечки, которые ходят по дорогам по делам
     ├── Camera        — откуда мы смотрим на карту
     ├── InputHandler  — читает ввод, двигает Camera, ищет клетку в Grid
     ├── BuildMode     — строительство: выбранный товар, место, подтверждение
     ├── DemolishMode  — снос: выбор здания, подтверждение
     ├── Renderer      — рисует Grid в изометрии через Camera (и призрак здания из BuildMode)
     ├── UIManager     — интерфейс: панель ресурсов, кнопки, меню, панель строительства
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
    WINDOW_HEIGHT,
    WINDOW_TITLE,
    WINDOW_WIDTH,
)
from city_builder.citizens.citizens import CitizenManager
from city_builder.construction.build_mode import BuildMode
from city_builder.construction.demolish_mode import DemolishMode
from city_builder.core.game_loop import GameLoop
from city_builder.data.catalog import load_catalog
from city_builder.economy.clock import GameClock
from city_builder.economy.economy import Economy
from city_builder.economy.goals import GoalTracker
from city_builder.input.input_handler import InputHandler
from city_builder.render import iso
from city_builder.render.camera import Camera
from city_builder.render.images import ImageLibrary
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
        self.running = True  # пока True — игровой цикл крутится

        # --- То, что живёт всю программу (не меняется при «Новой игре») ---
        # Картинки зданий. Создаём только после окна: загрузчику нужен
        # convert_alpha(), а он работает лишь при открытом окне.
        self.images = ImageLibrary()
        self.renderer = Renderer(self.screen, self.images)
        self.show_debug = False  # отладочный текст (FPS, клетка) — включается клавишей F3
        self.loop = GameLoop(self, FPS)

        # --- Всё, что относится к одной партии ---
        self.new_game()

    def new_game(self) -> None:
        """Создать новую партию: карта, экономика, время, камера, интерфейс — с нуля.

        Вызывается при запуске и по кнопке «Новая игра» на экране итогов.
        Старые объекты просто заменяются новыми — Python сам удалит ненужные.
        """
        screen_width, screen_height = self.screen.get_size()

        # --- Мир ---
        self.grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self.grid.generate()  # озеро и река; generate(seed=42) — всегда одна и та же карта

        # --- Экономика, время, цель ---
        self.economy = Economy(self.grid)
        self.clock = GameClock()
        self.goals = GoalTracker(self.economy)
        self.citizens = CitizenManager(self.grid, self.economy)

        # --- Камера ---
        # Границы карты в мире (изометрический ромб) — камера не уедет за них
        self.camera = Camera(screen_width, screen_height, iso.map_bounds(self.grid.width, self.grid.height))
        # Старт — в центре карты
        self.camera.center_on(*iso.tile_to_world(self.grid.width / 2, self.grid.height / 2))

        # --- Ввод, режимы, интерфейс ---
        self.input = InputHandler(self.camera, self.grid)
        self.build = BuildMode(self.grid, self.economy)
        self.demolish = DemolishMode(self.grid, self.economy)
        self.ui = UIManager(self.screen.get_size(), self.catalog, self.build, self.demolish,
                            self.images, self.economy, self.clock, self.goals)

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
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F3:
            self.show_debug = not self.show_debug  # not — «наоборот»: True <-> False
            return
        consumed = (self.ui.handle_event(event)
                    or self.build.handle_event(event)
                    or self.demolish.handle_event(event))
        if not consumed:
            self.input.handle_event(event)
        # Выйти можно с клавиатуры/крестика окна (input) или кнопкой выхода (ui)
        if self.input.quit_requested or self.ui.quit_requested:
            self.running = False  # цикл в GameLoop завершится
        elif self.ui.new_game_requested:
            self.new_game()  # «Новая игра» на экране итогов

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
        # Режим сноса запоминает, какое здание под курсором. Здание ищем по картинке
        # (высокий дом закрывает клетки за собой), но только если курсор над картой
        picked = None
        if self.input.hovered_tile is not None or not self.ui.is_mouse_over(mouse_pos):
            picked = self.renderer.pick_building(mouse_pos)
        self.demolish.update_hover(self.input.hovered_tile, picked)
        # Подсказка о здании — только когда ничего не строим и не сносим
        idle = not (self.build.active or self.demolish.active or self.ui.blocks_world)
        self.ui.building_info.update(picked if idle else None, mouse_pos)

        self.camera.clamp()    # после всех движений не даём камере уехать с карты

        # --- Экономика ---
        # Пересчёт статистики (только если что-то построили/снесли)
        self.economy.refresh()
        if self.goals.finished:
            return  # игра окончена (экран итогов) — время стоит

        # Жители ходят в игровом времени: на паузе стоят, на ×3 бегут втрое быстрее
        self.citizens.update(dt * self.clock.speed)

        # Часы говорят, сколько тиков пора сделать (обычно 0, иногда 1)
        for _ in range(self.clock.update(dt)):  # _ — переменная, которая не нужна
            self.economy.tick()
            self.goals.on_tick()  # проверка победы и поражения
            if self.goals.finished:
                # Игра только что закончилась: выключаем строительство, снос и меню,
                # чтобы после «Продолжить» не оказаться в середине действия
                self.build.cancel()
                self.demolish.cancel()
                self.ui.menu.close()
                break

    def draw(self) -> None:
        """Шаг 3 кадра: отрисовка. Порядок важен — то, что рисуется позже, оказывается сверху."""
        self.renderer.draw(self.grid, self.camera, self.citizens)  # карта, здания, жители
        if self.build.active:
            self.renderer.draw_build_preview(self.build, self.camera)  # призрак здания
        elif self.demolish.active:
            self.renderer.draw_demolish_preview(self.demolish, self.camera)  # красная подсветка
        else:
            self.renderer.draw_hover(self.input.hovered_tile, self.camera)  # рамка клетки

        # Отладочная информация (F3) — под панелью ресурсов
        if self.show_debug:
            tile = self.input.hovered_tile
            tile_info = f"{tile.x}, {tile.y} ({tile.type.value})" if tile else "-"
            if tile and tile.building:
                state = "работает" if tile.building.working else "нет дороги"
                tile_info += f" — {tile.building.item.name} ({state})"
            self.renderer.draw_debug([
                f"FPS: {self.loop.current_fps:.0f}",
                f"Zoom: {self.camera.zoom:.2f}",
                f"Tile: {tile_info}",
            ], top=self.ui.city_panel.rect.bottom + 8)

        # Интерфейс рисуем последним — он всегда поверх карты
        self.ui.draw(self.screen)

    def run(self) -> None:
        """Запустить игру. Возвращается только после закрытия окна."""
        try:
            self.loop.run()
        finally:
            # finally выполнится даже при ошибке — окно корректно закроется
            pygame.quit()
