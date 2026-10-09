"""Главный объект игры: связывает мир, камеру, ввод и отрисовку.

Game — «дирижёр». Сам почти ничего не делает, а создаёт все части
и вызывает их в нужном порядке. Схема зависимостей:

    Game
     ├── Grid          — данные карты (что где лежит)
     ├── Camera        — откуда мы смотрим на карту
     ├── InputHandler  — читает ввод, двигает Camera, ищет клетку в Grid
     ├── Renderer      — рисует Grid через Camera
     └── GameLoop      — крутит цикл и вызывает методы Game каждый кадр
"""

import pygame

from city_builder.config import (
    FPS,
    GRID_HEIGHT,
    GRID_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TILE_SIZE,
    WINDOW_TITLE,
)
from city_builder.core.game_loop import GameLoop
from city_builder.input.input_handler import InputHandler
from city_builder.render.camera import Camera
from city_builder.render.renderer import Renderer
from city_builder.world.grid import Grid


class Game:
    def __init__(self) -> None:
        # --- Запуск pygame и создание окна ---
        pygame.init()  # инициализирует все модули pygame (графика, шрифты, звук...)
        pygame.display.set_caption(WINDOW_TITLE)
        # set_mode создаёт окно и возвращает его поверхность для рисования
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.running = True  # пока True — игровой цикл крутится

        # --- Мир ---
        self.grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self.grid.generate()  # озеро и река; generate(seed=42) — всегда одна и та же карта

        # --- Камера ---
        # Размер мира в пикселях (при zoom = 1): 30 клеток * 32 px = 960
        world_width = self.grid.width * TILE_SIZE
        world_height = self.grid.height * TILE_SIZE
        self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT, world_width, world_height)
        self.camera.center_on(world_width / 2, world_height / 2)  # старт — в центре карты

        # --- Ввод, отрисовка, цикл ---
        self.input = InputHandler(self.camera, self.grid)
        self.renderer = Renderer(self.screen)
        self.loop = GameLoop(self, FPS)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Шаг 1 кадра: GameLoop передаёт сюда каждое событие pygame."""
        self.input.handle_event(event)
        if self.input.quit_requested:
            self.running = False  # цикл в GameLoop завершится

    def update(self, dt: float) -> None:
        """Шаг 2 кадра: обновление состояния. dt — секунды с прошлого кадра."""
        self.input.update(dt)  # движение камеры с клавиатуры + клетка под курсором
        self.camera.clamp()    # после всех движений не даём камере уехать с карты
        # На этапе 2 здесь появится тик экономики

    def draw(self) -> None:
        """Шаг 3 кадра: отрисовка. Порядок важен — то, что рисуется позже, оказывается сверху."""
        self.renderer.draw(self.grid, self.camera)                  # карта
        self.renderer.draw_hover(self.input.hovered_tile, self.camera)  # рамка поверх карты

        # Отладочная информация поверх всего
        tile = self.input.hovered_tile
        tile_info = f"{tile.x}, {tile.y} ({tile.type.value})" if tile else "-"
        self.renderer.draw_debug([
            f"FPS: {self.loop.current_fps:.0f}",
            f"Zoom: {self.camera.zoom:.2f}",
            f"Tile: {tile_info}",
        ])

    def run(self) -> None:
        """Запустить игру. Возвращается только после закрытия окна."""
        try:
            self.loop.run()
        finally:
            # finally выполнится даже при ошибке — окно корректно закроется
            pygame.quit()
