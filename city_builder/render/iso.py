"""Изометрическая проекция: перевод «клетка карты ↔ точка мира».

Карта хранится как обычная сетка (x — столбец, y — строка), а на экране
рисуется «под углом»: каждая клетка — ромб, ось x уходит вправо-вниз,
ось y — влево-вниз.

           (0,0)
          /     \\
     (0,1)       (1,0)          ← клетки-ромбы
          \\     /
           (1,1)

Формулы (TW, TH — ширина и высота ромба):
    мир_x = (x − y) × TW/2
    мир_y = (x + y) × TH/2
Это координаты ВЕРХНЕГО угла ромба клетки (x, y). Обратные формулы — в world_to_tile.

«Мир» здесь — плоскость картинки при zoom = 1. Камера переводит мир в экран
(сдвиг + масштаб) так же, как раньше, — она про изометрию ничего не знает.
"""

from __future__ import annotations

from typing import Tuple

import math

from city_builder.config import ISO_TILE_HEIGHT, ISO_TILE_WIDTH

HALF_W = ISO_TILE_WIDTH / 2
HALF_H = ISO_TILE_HEIGHT / 2

Point = Tuple[float, float]


def tile_to_world(tx: float, ty: float) -> Point:
    """Клетка (может быть дробной) -> точка мира. Для целых — верхний угол ромба."""
    return (tx - ty) * HALF_W, (tx + ty) * HALF_H


def world_to_tile(wx: float, wy: float) -> Point:
    """Точка мира -> дробные координаты клетки (обратная формула).

    Из  a = мир_x / (TW/2) = x − y   и   b = мир_y / (TH/2) = x + y
    получаем  x = (a + b) / 2,  y = (b − a) / 2.
    """
    a = wx / HALF_W
    b = wy / HALF_H
    return (a + b) / 2, (b - a) / 2


def world_to_tile_index(wx: float, wy: float) -> tuple[int, int]:
    """Точка мира -> номер клетки, на которую она попадает."""
    fx, fy = world_to_tile(wx, wy)
    return math.floor(fx), math.floor(fy)


def footprint_corners(x: float, y: float, width: float, height: float) -> list[Point]:
    """Четыре угла ромба области клеток в мире: верх, право, низ, лево.

    Для здания 2×2 в (5, 5) это ромб, покрывающий все его четыре клетки.
    """
    return [
        tile_to_world(x, y),                    # верх
        tile_to_world(x + width, y),            # право
        tile_to_world(x + width, y + height),   # низ
        tile_to_world(x, y + height),           # лево
    ]


def footprint_box(x: float, y: float, width: float, height: float) -> tuple[float, float, float, float]:
    """Прямоугольник, описанный вокруг ромба области: (левый край, верх, ширина, высота) в мире."""
    left = tile_to_world(x, y + height)[0]
    top = tile_to_world(x, y)[1]
    return left, top, (width + height) * HALF_W, (width + height) * HALF_H


def map_bounds(grid_width: int, grid_height: int) -> tuple[float, float, float, float]:
    """Границы всей карты в мире: (лево, верх, право, низ) — для ограничения камеры."""
    left = tile_to_world(0, grid_height)[0]
    right = tile_to_world(grid_width, 0)[0]
    bottom = tile_to_world(grid_width, grid_height)[1]
    return left, 0.0, right, bottom


def depth(x: float, y: float) -> float:
    """«Глубина» точки: чем больше x + y, тем ближе к зрителю (ниже на экране).
    По ней сортируем здания и жителей: дальние рисуем первыми, ближние — поверх."""
    return x + y
