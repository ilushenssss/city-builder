"""Отрисовка мира через pygame.

Renderer только рисует: он читает данные (Grid, Camera, BuildMode), но ничего
в них не меняет. Вся игровая логика живёт в других модулях.

Слои (снизу вверх): клетки -> линии сетки -> здания -> призрак/подсветка.

Как рисует pygame: есть «поверхность» (Surface) окна — по сути картинка
в памяти. Мы рисуем на ней прямоугольники и текст, а в конце кадра
GameLoop вызывает pygame.display.flip(), и картинка появляется на экране.
"""

import math

import pygame

from city_builder.config import (
    COLOR_BACKGROUND,
    COLOR_DEMOLISH,
    COLOR_GHOST_BAD,
    COLOR_GHOST_OK,
    COLOR_GHOST_PENDING,
    COLOR_GRID_LINE,
    COLOR_HOVER,
    COLOR_TEXT,
    DEMOLISH_HOVER_ALPHA,
    DEMOLISH_TARGET_ALPHA,
    FLAT_CATEGORIES,
    GHOST_ALPHA,
    GRID_LINES_MIN_TILE_PX,
    TILE_COLORS,
    TILE_SIZE,
)
from city_builder.construction.build_mode import BuildMode, BuildState
from city_builder.construction.demolish_mode import DemolishMode, DemolishState
from city_builder.render.camera import Camera
from city_builder.world.building import Building
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile


def darker(color: tuple[int, int, int], factor: float = 0.6) -> tuple[int, int, int]:
    """Тот же цвет, но темнее (для рамки здания)."""
    r, g, b = color
    return int(r * factor), int(g * factor), int(b * factor)


class Renderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen  # поверхность окна, на которой рисуем
        # Шрифт загружаем один раз здесь, а не каждый кадр — это медленно.
        self.font = pygame.font.SysFont("consolas", 16)

    def tile_rect(self, x: int, y: int, camera: Camera) -> pygame.Rect:
        """Прямоугольник клетки (x, y) на экране."""
        return self.area_rect(x, y, 1, 1, camera)

    def area_rect(self, x: int, y: int, width: int, height: int, camera: Camera) -> pygame.Rect:
        """Прямоугольник на экране для области клеток: от (x, y), размером width × height.

        Считаем экранные координаты левого верхнего и правого нижнего углов
        и округляем каждый угол отдельно. Если бы округляли ширину,
        при дробном масштабе (например, 1.1) между клетками появлялись бы
        щели в 1 пиксель.
        """
        left, top = camera.world_to_screen(x * TILE_SIZE, y * TILE_SIZE)
        right, bottom = camera.world_to_screen((x + width) * TILE_SIZE, (y + height) * TILE_SIZE)
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

        # --- Здания поверх клеток ---
        screen_rect = self.screen.get_rect()
        for building in grid.buildings:
            rect = self.area_rect(building.x, building.y, building.width, building.height, camera)
            if rect.colliderect(screen_rect):  # здание за краем экрана не рисуем
                self._draw_building(building, rect, camera)

    def _draw_building(self, building: Building, rect: pygame.Rect, camera: Camera) -> None:
        """Пока здание — цветной прямоугольник. Позже здесь будет картинка из assets/."""
        color = building.item.color
        if building.item.category in FLAT_CATEGORIES:
            # Дорога — во всю клетку, без рамки: соседние клетки сливаются
            pygame.draw.rect(self.screen, color, rect)
            return
        # Остальные здания — с отступом от края клетки и тёмной рамкой,
        # чтобы соседние здания не сливались в одно пятно.
        # Отступ растёт вместе с масштабом (при zoom 1 — 3 px).
        inset = max(1, round(3 * camera.zoom))
        body = rect.inflate(-2 * inset, -2 * inset)
        radius = max(2, round(4 * camera.zoom))
        pygame.draw.rect(self.screen, color, body, border_radius=radius)
        pygame.draw.rect(self.screen, darker(color), body, 2, border_radius=radius)

    def draw_build_preview(self, build: BuildMode, camera: Camera) -> None:
        """«Призрак» здания: где оно встанет и можно ли его там построить.

        PLACING    — у курсора; зелёная рамка — можно, красная — нельзя.
        CONFIRMING — на выбранном месте; жёлтая рамка — ждём подтверждения.
        """
        if build.item is None:
            return
        if build.state == BuildState.CONFIRMING:
            pos, frame_color = build.target, COLOR_GHOST_PENDING
        else:
            pos = build.cursor_pos
            frame_color = COLOR_GHOST_BAD if build.cursor_error else COLOR_GHOST_OK
        if pos is None:  # курсор вне карты
            return

        width, height = build.item.size
        rect = self.area_rect(pos[0], pos[1], width, height, camera)
        # Полупрозрачная заливка цветом здания + цветная рамка
        self._draw_tinted(rect, build.item.color, GHOST_ALPHA)
        pygame.draw.rect(self.screen, frame_color, rect, 3)

    def draw_demolish_preview(self, demolish: DemolishMode, camera: Camera) -> None:
        """Подсветка при сносе.

        SELECTING  — здание под курсором слегка закрашено красным;
                     если под курсором пусто — обычная белая рамка клетки.
        CONFIRMING — выбранное здание закрашено ярко-красным, ждём подтверждения.
        """
        if demolish.state == DemolishState.CONFIRMING and demolish.target:
            building, alpha = demolish.target, DEMOLISH_TARGET_ALPHA
        elif demolish.hovered:
            building, alpha = demolish.hovered, DEMOLISH_HOVER_ALPHA
        else:
            self.draw_hover(demolish.hovered_tile, camera)
            return
        rect = self.area_rect(building.x, building.y, building.width, building.height, camera)
        self._draw_tinted(rect, COLOR_DEMOLISH, alpha)
        pygame.draw.rect(self.screen, COLOR_DEMOLISH, rect, 3)

    def _draw_tinted(self, rect: pygame.Rect, color: tuple[int, int, int], alpha: int) -> None:
        """Полупрозрачная заливка прямоугольника.

        Обычный pygame.draw.rect не умеет прозрачность, поэтому рисуем на отдельной
        поверхности с поддержкой прозрачности (SRCALPHA) и накладываем её на экран.
        """
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((*color, alpha))  # (*цвет, альфа) -> (r, g, b, a)
        self.screen.blit(overlay, rect.topleft)

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
