"""Рисование изометрических спрайтов средствами pygame: «коробки», окна, крыши, деревья.

Используется в двух местах:
  * в игре — запасной спрайт, если для здания нет PNG (simple_building_sprite);
  * в tools/make_placeholder_images.py — подробные текстуры всех зданий.

Как устроен спрайт здания размером w × h клеток
-----------------------------------------------
Картинка шириной (w + h) × TW/2. Внизу — «основание»: ромб, который ровно
ложится на клетки здания. Над ним — свободное место под высоту здания.

            ┌──────────────┐
            │    ▄▀▀▄      │  ← высота здания (top_space)
            │   █    █     │
            │  ◇──────◇    │  ← ромб основания (w × h клеток)
            │   ◇────◇     │
            └──────────────┘

Точки внутри спрайта задаются в «координатах основания» (cx, cy, z):
  cx — от 0 до w (вдоль оси x карты), cy — от 0 до h (вдоль оси y),
  z  — высота над землёй в пикселях текстуры.
SpriteCanvas.point() переводит их в пиксели картинки — по тем же формулам, что iso.py.

Освещение: свет падает слева-сверху, поэтому
  верх — самый светлый, левая стена — средняя, правая — самая тёмная.
"""

import random

import pygame

from city_builder.config import FLOOR_HEIGHT, TEXTURE_TILE_HEIGHT, TEXTURE_TILE_WIDTH

TW = TEXTURE_TILE_WIDTH
TH = TEXTURE_TILE_HEIGHT

Color = tuple[int, int, int]
Point = tuple[float, float]

# Яркость граней коробки (множитель цвета)
SHADE_TOP = 1.12
SHADE_LEFT = 0.86
SHADE_RIGHT = 0.64


def shade(color: Color, factor: float) -> Color:
    """Светлее (factor > 1) или темнее (factor < 1), с ограничением 0..255."""
    return tuple(max(0, min(255, int(c * factor))) for c in color)  # type: ignore[return-value]


def mix(a: Color, b: Color, t: float) -> Color:
    """Смесь двух цветов: t = 0 — первый, t = 1 — второй."""
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


class SpriteCanvas:
    """Прозрачная картинка под спрайт здания w × h клеток с запасом высоты top_space."""

    def __init__(self, width: int, height: int, top_space: int) -> None:
        self.w = width
        self.h = height
        self.top_space = top_space
        size = ((width + height) * TW // 2, (width + height) * TH // 2 + top_space)
        self.surface = pygame.Surface(size, pygame.SRCALPHA)

    def point(self, cx: float, cy: float, z: float = 0) -> Point:
        """Точка основания (cx, cy) на высоте z -> пиксель картинки."""
        x = self.h * TW / 2 + (cx - cy) * TW / 2
        y = self.top_space + (cx + cy) * TH / 2 - z
        return x, y

    # --- Плоские фигуры ---

    def diamond(self, x0: float, y0: float, x1: float, y1: float, z: float,
                color: Color | tuple[int, int, int, int], outline: Color | None = None) -> None:
        """Горизонтальный «ромб» (прямоугольник карты [x0..x1] × [y0..y1]) на высоте z."""
        pts = [self.point(x0, y0, z), self.point(x1, y0, z), self.point(x1, y1, z), self.point(x0, y1, z)]
        pygame.draw.polygon(self.surface, color, pts)
        if outline:
            pygame.draw.polygon(self.surface, outline, pts, 1)

    def ellipse(self, cx: float, cy: float, radius: float, z: float, color, width: int = 0) -> None:
        """Круг на земле (в изометрии — эллипс вдвое ниже ширины). radius — в пикселях текстуры."""
        x, y = self.point(cx, cy, z)
        pygame.draw.ellipse(self.surface, color,
                            (x - radius, y - radius / 2, radius * 2, radius), width)

    # --- Объёмные фигуры ---

    def box(self, x0: float, y0: float, x1: float, y1: float, z0: float, z1: float,
            color: Color, top: Color | None = None) -> None:
        """Коробка: видны левая стена (вдоль y = y1), правая (вдоль x = x1) и крыша."""
        p = self.point
        left = [p(x0, y1, z0), p(x1, y1, z0), p(x1, y1, z1), p(x0, y1, z1)]
        right = [p(x1, y1, z0), p(x1, y0, z0), p(x1, y0, z1), p(x1, y1, z1)]
        roof = [p(x0, y0, z1), p(x1, y0, z1), p(x1, y1, z1), p(x0, y1, z1)]
        edge = shade(color, 0.45)
        pygame.draw.polygon(self.surface, shade(color, SHADE_LEFT), left)
        pygame.draw.polygon(self.surface, shade(color, SHADE_RIGHT), right)
        pygame.draw.polygon(self.surface, top or shade(color, SHADE_TOP), roof)
        for poly in (left, right, roof):
            pygame.draw.polygon(self.surface, edge, poly, 1)

    def windows(self, x0: float, y0: float, x1: float, y1: float, z0: float, floors: int,
                color: Color, per_tile: int = 3, lit: float = 0.25, seed: int = 0) -> None:
        """Ряды окон на двух видимых стенах коробки. Часть окон «горит» (жёлтые)."""
        rng = random.Random(seed)
        glass = shade(color, 1.0)
        light = (255, 225, 140)
        p = self.point
        for floor in range(floors):
            za = z0 + floor * FLOOR_HEIGHT + 5
            zb = za + FLOOR_HEIGHT - 9
            # Левая стена: окна вдоль x на линии y1
            count = max(1, round((x1 - x0) * per_tile))
            for i in range(count):
                a = x0 + (x1 - x0) * (i + 0.25) / count
                b = x0 + (x1 - x0) * (i + 0.75) / count
                c = light if rng.random() < lit else shade(glass, SHADE_LEFT)
                pygame.draw.polygon(self.surface, c, [p(a, y1, za), p(b, y1, za), p(b, y1, zb), p(a, y1, zb)])
            # Правая стена: окна вдоль y на линии x1
            count = max(1, round((y1 - y0) * per_tile))
            for i in range(count):
                a = y0 + (y1 - y0) * (i + 0.25) / count
                b = y0 + (y1 - y0) * (i + 0.75) / count
                c = light if rng.random() < lit else shade(glass, SHADE_RIGHT)
                pygame.draw.polygon(self.surface, c, [p(x1, b, za), p(x1, a, za), p(x1, a, zb), p(x1, b, zb)])

    def pyramid_roof(self, x0: float, y0: float, x1: float, y1: float, z: float,
                     roof_height: float, color: Color) -> None:
        """Четырёхскатная крыша: вершина над центром. Сначала дальние скаты, потом ближние."""
        p = self.point
        apex = p((x0 + x1) / 2, (y0 + y1) / 2, z + roof_height)
        t, r, b, l = p(x0, y0, z), p(x1, y0, z), p(x1, y1, z), p(x0, y1, z)
        edge = shade(color, 0.45)
        for poly, factor in (([l, t, apex], 1.05), ([t, r, apex], 0.75),
                             ([l, b, apex], SHADE_LEFT + 0.08), ([b, r, apex], SHADE_RIGHT)):
            pygame.draw.polygon(self.surface, shade(color, factor), poly)
            pygame.draw.polygon(self.surface, edge, poly, 1)

    def cylinder(self, cx: float, cy: float, radius: float, z0: float, z1: float, color: Color) -> None:
        """Вертикальный цилиндр (труба, бак, градирня)."""
        x, y0 = self.point(cx, cy, z0)
        _, y1 = self.point(cx, cy, z1)
        body = pygame.Rect(x - radius, y1, radius * 2, y0 - y1)
        pygame.draw.ellipse(self.surface, shade(color, SHADE_RIGHT), (x - radius, y0 - radius / 2, radius * 2, radius))
        pygame.draw.rect(self.surface, shade(color, SHADE_LEFT), body)
        # Правая половина темнее — объём
        pygame.draw.rect(self.surface, shade(color, SHADE_RIGHT), (x, y1, radius, y0 - y1))
        pygame.draw.ellipse(self.surface, shade(color, SHADE_TOP), (x - radius, y1 - radius / 2, radius * 2, radius))
        pygame.draw.ellipse(self.surface, shade(color, 0.5), (x - radius, y1 - radius / 2, radius * 2, radius), 1)

    def tree(self, cx: float, cy: float, size: float = 1.0, color: Color = (60, 140, 60)) -> None:
        """Дерево: тень, ствол и круглая крона с бликом."""
        s = 9 * size
        x, y = self.point(cx, cy)
        pygame.draw.ellipse(self.surface, (0, 0, 0, 60), (x - s, y - s / 3, s * 2, s * 0.8))
        pygame.draw.line(self.surface, (100, 70, 40), (x, y), (x, y - s * 1.4), max(2, int(s / 4)))
        pygame.draw.circle(self.surface, shade(color, 0.8), (x, y - s * 1.9), s)
        pygame.draw.circle(self.surface, shade(color, 1.15), (x - s / 3, y - s * 2.2), s / 2)

    def shadow(self, x0: float, y0: float, x1: float, y1: float, length: float = 0.25) -> None:
        """Тень от здания на землю (вправо-вниз от основания)."""
        self.diamond(x0 + length, y0, x1 + length, y1 + length, 0, (0, 0, 0, 55))


# ---------------------------------------------------------------------------
# Плоские клетки (земля, вода, дороги)
# ---------------------------------------------------------------------------

def flat_tile(color: Color, noise: float = 0.0, seed: int = 0,
              edge: tuple[int, int, int, int] | None = None) -> pygame.Surface:
    """Ромб одной клетки, залитый цветом, с «шумом» (текстура травы, асфальта).
    edge — полупрозрачная обводка ромба (тонкая сетка клеток)."""
    canvas = SpriteCanvas(1, 1, 0)
    canvas.diamond(0, 0, 1, 1, 0, color)
    if noise:
        rng = random.Random(seed)
        surf = canvas.surface
        for _ in range(int(900 * noise)):
            # Случайная точка внутри ромба: берём случайные (cx, cy) в основании
            x, y = canvas.point(rng.random(), rng.random())
            surf.set_at((int(x), int(y)), shade(color, rng.choice((0.85, 0.92, 1.08, 1.15))))
    if edge:
        pts = [canvas.point(0, 0), canvas.point(1, 0), canvas.point(1, 1), canvas.point(0, 1)]
        pygame.draw.polygon(canvas.surface, edge, pts, 1)
    return canvas.surface


# ---------------------------------------------------------------------------
# Простой спрайт здания — запасной вариант, если нет PNG
# ---------------------------------------------------------------------------

def simple_building_sprite(width: int, height: int, floors: int, color: Color, flat: bool) -> pygame.Surface:
    """Коробка нужной высоты цвета товара (или плоский ромб для дорог)."""
    if flat:
        return flat_tile(color, noise=0.4)
    z = max(1, floors) * FLOOR_HEIGHT + 4
    canvas = SpriteCanvas(width, height, int(z) + 4)
    m = 0.12  # отступ от края клеток
    canvas.shadow(m, m, width - m, height - m)
    canvas.box(m, m, width - m, height - m, 0, z, color)
    return canvas.surface
