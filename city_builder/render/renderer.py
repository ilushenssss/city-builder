"""Отрисовка мира через pygame.

Renderer только рисует: он читает данные (Grid, Camera), но ничего в них
не меняет. Вся игровая логика живёт в других модулях.

Как рисует pygame: есть «поверхность» (Surface) окна — по сути картинка
в памяти. Мы рисуем на ней прямоугольники и текст, а в конце кадра
GameLoop вызывает pygame.display.flip(), и картинка появляется на экране.
"""

import math

import pygame

from city_builder.config import (
    COLOR_BACKGROUND,
    COLOR_GRID_LINE,
    COLOR_HOVER,
    COLOR_TEXT,
    GRID_LINES_MIN_TILE_PX,
    TILE_COLORS,
    TILE_SIZE,
)
from city_builder.render.camera import Camera
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile


class Renderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen  # поверхность окна, на которой рисуем
        # Шрифт загружаем один раз здесь, а не каждый кадр — это медленно.
        self.font = pygame.font.SysFont("consolas", 16)

    def tile_rect(self, x: int, y: int, camera: Camera) -> pygame.Rect:
        """Прямоугольник клетки (x, y) на экране.

        Считаем экранные координаты левого верхнего и правого нижнего углов
        клетки и округляем каждый угол отдельно. Если бы округляли ширину,
        при дробном масштабе (например, 1.1) между клетками появлялись бы
        щели в 1 пиксель.
        """
        left, top = camera.world_to_screen(x * TILE_SIZE, y * TILE_SIZE)
        right, bottom = camera.world_to_screen((x + 1) * TILE_SIZE, (y + 1) * TILE_SIZE)
        left, top, right, bottom = round(left), round(top), round(right), round(bottom)
        # Rect(x, y, ширина, высота) — прямоугольник в pygame
        return pygame.Rect(left, top, right - left, bottom - top)

    def draw(self, grid: Grid, camera: Camera) -> None:
        """Нарисовать карту. Вызывается каждый кадр."""
        # Сначала заливаем всё фоном — стираем прошлый кадр
        self.screen.fill(COLOR_BACKGROUND)

        # --- Рисуем только видимые клетки ---
        # Узнаём, какой кусок мира сейчас виден: переводим углы экрана в мир
        width, height = self.screen.get_size()
        left, top = camera.screen_to_world(0, 0)
        right, bottom = camera.screen_to_world(width, height)
        # ...и переводим в номера клеток. max/min — чтобы не выйти за карту.
        x0 = max(0, math.floor(left / TILE_SIZE))
        y0 = max(0, math.floor(top / TILE_SIZE))
        x1 = min(grid.width, math.floor(right / TILE_SIZE) + 1)  # +1: range не включает конец
        y1 = min(grid.height, math.floor(bottom / TILE_SIZE) + 1)

        # При сильном отдалении линии сетки сливаются в кашу — не рисуем их
        draw_lines = TILE_SIZE * camera.zoom >= GRID_LINES_MIN_TILE_PX

        for y in range(y0, y1):
            for x in range(x0, x1):
                # Здесь координаты точно внутри карты, поэтому берём клетку напрямую
                tile = grid.tiles[y][x]
                rect = self.tile_rect(x, y, camera)
                # Заливка клетки цветом её типа
                pygame.draw.rect(self.screen, TILE_COLORS[tile.type.value], rect)
                if draw_lines:
                    # Последний аргумент 1 — толщина линии: рисуем только рамку
                    pygame.draw.rect(self.screen, COLOR_GRID_LINE, rect, 1)

    def draw_hover(self, tile: Tile | None, camera: Camera) -> None:
        """Белая рамка вокруг клетки под курсором."""
        if tile is None:  # курсор вне карты — рисовать нечего
            return
        pygame.draw.rect(self.screen, COLOR_HOVER, self.tile_rect(tile.x, tile.y, camera), 2)

    def draw_debug(self, lines: list[str]) -> None:
        """Отладочный текст в левом верхнем углу — по строке на элемент списка."""
        y = 8  # отступ сверху
        for line in lines:
            # render() превращает текст в картинку (Surface).
            # True — сглаживание краёв букв.
            surface = self.font.render(line, True, COLOR_TEXT)
            # blit — «наклеить» одну картинку на другую в точке (8, y)
            self.screen.blit(surface, (8, y))
            y += surface.get_height() + 2  # следующая строка ниже
