"""Генератор изометрических текстур: все здания, дороги, местность и категории магазина.

Рисует картинки средствами pygame (см. city_builder/render/iso_sprites.py:
стены с переходом света, окна с рамами, двускатные крыши, мягкие тени,
сглаженные края) и сохраняет PNG в:
    assets/buildings/<id>.png        — здания (id из data/shop.json)
    assets/roads/<id>/<0..15>.png    — 16 вариантов каждой дороги (по соседям)
    assets/terrain/grass_<0..3>.png  — варианты травы (вода рисуется в игре — она анимирована)
    assets/decor/<вид>_<0..2>.png    — природа: деревья, ёлки, кусты, цветы, камни
    assets/categories/<id>.png       — картинки категорий магазина

Запуск из папки проекта:
    python tools/make_placeholder_images.py

Существующие файлы ПЕРЕЗАПИСЫВАЮТСЯ. Если вы нарисовали свои картинки
с теми же именами — не запускайте скрипт (или уберите их из BUILDINGS).

Все размеры ниже — в «единицах чертежа»: клетка — ромб 128×64, этаж — F (18).
Координаты (cx, cy) — доли клеток внутри здания: (0, 0) — дальний угол,
(w, h) — ближний к зрителю.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

# Скрипт лежит в tools/, а модули игры — в city_builder/ уровнем выше.
# Добавляем папку проекта в путь поиска модулей, чтобы import city_builder работал.
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import pygame  # noqa: E402  (импорт не в начале файла — из-за строки выше)

from city_builder.config import SHOP_DATA_FILE, TILE_COLORS  # noqa: E402
from city_builder.data.catalog import load_catalog  # noqa: E402
from city_builder.render.iso_sprites import (  # noqa: E402
    CONCRETE,
    FLOOR_HEIGHT as F,
    GLASS,
    GLASS_DARK,
    NORTH,
    SOUTH,
    SpriteCanvas,
    road_tile,
    shade,
    decor_sprite,
    grass_tile,
)

ASSETS = PROJECT_DIR / "assets"

# Участки под зданиями
LAWN = (112, 172, 92)
PAVING = (198, 196, 188)
ASPHALT_LOT = (96, 98, 104)
GRAVEL = (168, 162, 150)
DIRT = (150, 126, 92)


# ===========================================================================
# Жилые здания
# ===========================================================================

def house_small() -> pygame.Surface:
    """Маленький дом: газон с дорожкой, светлые стены, двускатная черепичная крыша, труба."""
    wall, roof = (238, 226, 204), (196, 98, 62)
    c = SpriteCanvas(1, 1, F + 44)
    c.lot(0.02, 0.02, 0.98, 0.98, LAWN)
    c.quad(0.44, 0.78, 0.56, 0.98, 0, PAVING)                      # дорожка к двери
    c.tree(0.12, 0.88, 0.55)                                        # куст у угла
    c.soft_shadow(0.2, 0.22, 0.8, 0.78, F + 22)
    c.box(0.2, 0.22, 0.8, 0.78, 0, F + 4, wall)
    c.door("left", 0.44, 0.56, 0.78, 13)
    c.window("left", 0.26, 0.38, 0.78, 6, 15)
    c.window("left", 0.62, 0.74, 0.78, 6, 15, lit=True)
    c.window("right", 0.32, 0.46, 0.8, 6, 15)
    c.window("right", 0.56, 0.7, 0.8, 6, 15)
    c.box(0.6, 0.3, 0.68, 0.38, F + 10, F + 34, (150, 72, 52))      # труба (за коньком)
    c.gable_roof(0.2, 0.22, 0.8, 0.78, F + 4, 24, roof, wall, ridge="x")
    return c.result()


def cottage() -> pygame.Surface:
    """Коттедж: два этажа, крыша коньком поперёк, крыльцо, сад с деревьями."""
    wall, roof = (226, 206, 178), (150, 72, 56)
    c = SpriteCanvas(1, 1, 2 * F + 42)
    c.lot(0.02, 0.02, 0.98, 0.98, LAWN)
    c.tree(0.12, 0.14, 0.75, "pine")
    c.tree(0.88, 0.9, 0.6)
    c.soft_shadow(0.18, 0.18, 0.78, 0.74, 2 * F + 20)
    c.box(0.18, 0.18, 0.78, 0.74, 0, 2 * F + 4, wall)
    c.window_rows(0.18, 0.18, 0.78, 0.74, 2, 2, per_tile=2.6, lit=0.3, seed=3, width=0.55)
    c.box(0.4, 0.74, 0.58, 0.86, 0, 3, (180, 170, 160))            # крыльцо
    c.door("left", 0.43, 0.55, 0.74, 13, (120, 70, 45))
    c.gable_roof(0.18, 0.18, 0.78, 0.74, 2 * F + 4, 26, roof, wall, ridge="y")
    return c.result()


def apartment() -> pygame.Surface:
    """Многоэтажка: кирпичный дом в 6 этажей с балконами, козырёк над входом, техника на крыше."""
    wall = (196, 178, 160)
    z = 6 * F + 4
    c = SpriteCanvas(2, 2, z + 34)
    c.lot(0.03, 0.03, 1.97, 1.97, PAVING)
    c.tree(0.12, 1.85, 0.8)
    c.tree(1.86, 0.15, 0.8)
    c.soft_shadow(0.2, 0.2, 1.8, 1.8, z)
    c.box(0.2, 0.2, 1.8, 1.8, 0, z, wall)
    c.window_rows(0.2, 0.2, 1.8, 1.8, 4, 6, per_tile=2.5, lit=0.25, seed=6, width=0.5)
    # Балконы на левой стене: плита + перила на каждом этаже, кроме первого
    for floor in range(1, 6):
        zb = 4 + floor * F
        for a in (0.45, 1.25):
            c.box(a, 1.8, a + 0.32, 1.88, zb, zb + 1.5, (210, 205, 198), outline=False)
            c.face_rect("left", a, a + 0.32, 1.88, zb + 1.5, zb + 6, (*shade(wall, 0.6), 255), 0.6)
    c.box(0.85, 1.8, 1.15, 1.94, 13, 15, (120, 120, 125))           # козырёк над входом
    c.door("left", 0.9, 1.1, 1.8, 13, (80, 60, 45))
    c.flat_roof(0.2, 0.2, 1.8, 1.8, z, (150, 140, 132))
    c.box(0.45, 0.45, 0.85, 0.75, z, z + 12, CONCRETE)              # выход на крышу
    c.cylinder(1.3, 1.1, 9, z, z + 16, (160, 160, 165))             # бак для воды
    return c.result()


def skyscraper() -> pygame.Surface:
    """Небоскрёб: стеклянная башня на подиуме, сетка витражей, вертолётная площадка, антенна."""
    glass = (96, 140, 186)
    z = 14 * F + 6
    c = SpriteCanvas(2, 2, z + 44)
    c.lot(0.03, 0.03, 1.97, 1.97, PAVING)
    c.soft_shadow(0.15, 0.15, 1.85, 1.85, z)
    # Подиум — первый этаж шире башни
    c.box(0.15, 0.15, 1.85, 1.85, 0, F, (205, 205, 210))
    c.window_rows(0.15, 0.15, 1.85, 1.85, 0, 1, per_tile=3, lit=0.0, glass=GLASS, frame=(90, 95, 105),
                  width=0.85, height=0.7)
    c.flat_roof(0.15, 0.15, 1.85, 1.85, F, (170, 170, 175))
    # Башня: стекло с тонкими «рамами» — частая сетка окон
    c.box(0.35, 0.35, 1.65, 1.65, F, z, glass)
    c.window_rows(0.35, 0.35, 1.65, 1.65, F, 13, per_tile=4, lit=0.3, seed=14, glass=shade(glass, 0.9),
                  frame=(60, 75, 95), width=0.88, height=0.82)
    c.flat_roof(0.35, 0.35, 1.65, 1.65, z, (80, 85, 95))
    c.ground_ellipse(1.0, 1.0, 30, z, (60, 62, 70))                 # вертолётная площадка
    c.ground_ellipse(1.0, 1.0, 30, z, (240, 240, 240), 1.6)
    hx, hy = c.point(1.0, 1.0, z)
    for dx in (-6, 6):
        c.line((hx + dx * c.k, hy - 5 * c.k), (hx + dx * c.k, hy + 5 * c.k), (240, 240, 240), 2)
    c.line((hx - 6 * c.k, hy), (hx + 6 * c.k, hy), (240, 240, 240), 2)
    c.line(c.point(0.5, 0.5, z), c.point(0.5, 0.5, z + 36), (180, 180, 185), 1.2)  # антенна
    c.circle(c.point(0.5, 0.5, z + 36), 1.6, (240, 70, 60))
    return c.result()


# ===========================================================================
# Коммерция
# ===========================================================================

def awning(c: SpriteCanvas, a0: float, a1: float, fixed: float, z: float, stripes: int = 6,
           colors=((220, 60, 60), (245, 245, 245))) -> None:
    """Полосатый навес над витриной левой стены: наклонён наружу."""
    p = c.point
    for i in range(stripes):
        a = a0 + (a1 - a0) * i / stripes
        b = a0 + (a1 - a0) * (i + 1) / stripes
        c.poly([p(a, fixed, z), p(b, fixed, z), p(b, fixed + 0.12, z - 6), p(a, fixed + 0.12, z - 6)],
               colors[i % 2])
    c.line(p(a0, fixed + 0.12, z - 6), p(a1, fixed + 0.12, z - 6), shade(colors[0], 0.6), 0.6)


def kiosk() -> pygame.Surface:
    """Ларёк: будка с окошком-прилавком и полосатым навесом, рядом столик с зонтом."""
    c = SpriteCanvas(1, 1, 46)
    c.lot(0.02, 0.02, 0.98, 0.98, PAVING)
    c.soft_shadow(0.3, 0.32, 0.7, 0.64, 18)
    c.box(0.3, 0.32, 0.7, 0.64, 0, 18, (238, 206, 128))
    c.face_rect("left", 0.36, 0.64, 0.64, 6, 13, (250, 244, 220))   # окошко
    c.box(0.34, 0.64, 0.66, 0.7, 5, 6.5, (200, 170, 110), outline=False)  # прилавок
    awning(c, 0.28, 0.72, 0.64, 20, 4)
    c.flat_roof(0.3, 0.32, 0.7, 0.64, 18, (200, 170, 110))
    # Столик с зонтом
    x, y = c.point(0.82, 0.82, 0)
    c.line((x, y), (x, y - 16 * c.k), (120, 120, 120), 0.8)
    c.poly([(x - 9 * c.k, y - 13 * c.k), (x + 9 * c.k, y - 13 * c.k), (x, y - 20 * c.k)], (60, 140, 210))
    return c.result()


def shop() -> pygame.Surface:
    """Магазин: стеклянная витрина во всю стену, синяя вывеска, навес, кондиционеры на крыше."""
    wall = (234, 234, 240)
    z = F + 10
    c = SpriteCanvas(1, 1, z + 20)
    c.lot(0.02, 0.02, 0.98, 0.98, PAVING)
    c.soft_shadow(0.12, 0.12, 0.88, 0.84, z)
    c.box(0.12, 0.12, 0.88, 0.84, 0, z, wall)
    c.face_rect("left", 0.16, 0.84, 0.84, 1, 15, GLASS_DARK)         # витрина
    for a in (0.33, 0.5, 0.67):
        c.line(c.point(a, 0.84, 1), c.point(a, 0.84, 15), (220, 220, 225), 0.8)
    c.face_rect("left", 0.12, 0.88, 0.84, 17, 24, (60, 130, 215))    # вывеска
    c.face_rect("left", 0.3, 0.7, 0.84, 19, 22, (245, 245, 250))     # «буквы»
    awning(c, 0.14, 0.86, 0.84, 16.5)
    c.window("right", 0.25, 0.42, 0.88, 6, 15)
    c.window("right", 0.55, 0.72, 0.88, 6, 15)
    c.flat_roof(0.12, 0.12, 0.88, 0.84, z, (190, 190, 195))
    c.box(0.2, 0.2, 0.36, 0.32, z, z + 6, (160, 160, 165))           # кондиционеры
    c.box(0.45, 0.2, 0.6, 0.32, z, z + 6, (160, 160, 165))
    return c.result()


def office() -> pygame.Surface:
    """Офис: стеклянный бизнес-центр в 5 этажей с горизонтальными поясами и холлом."""
    glass = (140, 182, 210)
    z = 5 * F + 6
    c = SpriteCanvas(2, 2, z + 26)
    c.lot(0.03, 0.03, 1.97, 1.97, PAVING)
    c.tree(0.15, 1.85, 0.8)
    c.tree(1.85, 1.85, 0.8)
    c.soft_shadow(0.25, 0.25, 1.75, 1.75, z)
    c.box(0.25, 0.25, 1.75, 1.75, 0, z, (215, 220, 228))
    c.window_rows(0.25, 0.25, 1.75, 1.75, 6, 5, per_tile=3.5, lit=0.2, seed=5, glass=glass,
                  frame=(70, 80, 95), width=0.9, height=0.62)
    c.face_rect("left", 0.8, 1.2, 1.75, 0, 13, GLASS_DARK)           # стеклянный холл
    c.box(0.75, 1.75, 1.25, 1.9, 13, 15, (120, 125, 135))           # козырёк
    c.flat_roof(0.25, 0.25, 1.75, 1.75, z, (150, 155, 162))
    c.box(0.5, 0.5, 1.0, 0.8, z, z + 10, (175, 178, 185))           # техэтаж
    return c.result()


def mall() -> pygame.Surface:
    """Торговый центр: широкое здание, стеклянный вход, большая вывеска, парковка с машинами."""
    wall = (236, 236, 242)
    z = 2 * F + 8
    c = SpriteCanvas(2, 2, z + 24)
    c.lot(0.03, 0.03, 1.97, 1.97, ASPHALT_LOT)
    # Разметка парковки и машины — на передней полосе участка
    for i in range(7):
        x = 0.15 + i * 0.25
        c.line(c.point(x, 1.45), c.point(x, 1.9), (225, 225, 225), 0.7)
    for i, color in enumerate(((210, 60, 60), (60, 120, 210), (235, 235, 235), (60, 170, 90))):
        c.car(0.27 + i * 0.5, 1.68, color, along="y")
    c.soft_shadow(0.1, 0.1, 1.9, 1.35, z)
    c.box(0.1, 0.1, 1.9, 1.35, 0, z, wall)
    c.face_rect("left", 0.2, 1.8, 1.35, 1, F - 2, GLASS_DARK)        # витрины первого этажа
    c.face_rect("left", 0.75, 1.25, 1.35, 0, F + 4, (80, 120, 165))  # вход
    c.face_rect("left", 0.55, 1.45, 1.35, F + 6, z - 4, (190, 60, 110))  # вывеска
    c.face_rect("left", 0.7, 1.3, 1.35, F + 10, z - 8, (250, 235, 245))
    c.window_rows(0.1, 0.1, 1.9, 1.35, 2, 2, per_tile=2, lit=0.0, skip_floors=1, glass=GLASS)
    c.flat_roof(0.1, 0.1, 1.9, 1.35, z, (185, 185, 192))
    for x in (0.4, 0.8, 1.2):
        c.box(x, 0.35, x + 0.2, 0.5, z, z + 7, (160, 160, 168))
    return c.result()


# ===========================================================================
# Промышленность
# ===========================================================================

def farm() -> pygame.Surface:
    """Ферма: грядки разных культур, красный амбар с двускатной крышей, силосная башня."""
    c = SpriteCanvas(2, 2, 66)
    c.lot(0.03, 0.03, 1.97, 1.97, (128, 110, 80))
    crops = [(208, 186, 84), (122, 172, 72), (196, 170, 70), (146, 190, 88)]
    for i, color in enumerate(crops):  # 4 поля
        y0 = 0.08 + i * 0.3
        c.quad(0.08, y0, 1.15, y0 + 0.26, 0, color)
        for k in range(1, 14):  # борозды
            x = 0.08 + 1.07 * k / 14
            c.line(c.point(x, y0 + 0.02), c.point(x, y0 + 0.24), shade(color, 0.78), 0.6)
    c.soft_shadow(1.25, 0.3, 1.85, 1.1, 30)
    c.box(1.25, 0.3, 1.85, 1.1, 0, 24, (176, 48, 40))
    c.face_rect("left", 1.42, 1.68, 1.1, 0, 18, (110, 35, 28))       # ворота
    c.line(c.point(1.42, 1.1, 0), c.point(1.68, 1.1, 18), (230, 220, 210), 0.8)
    c.line(c.point(1.68, 1.1, 0), c.point(1.42, 1.1, 18), (230, 220, 210), 0.8)
    c.gable_roof(1.25, 0.3, 1.85, 1.1, 24, 18, (80, 70, 66), (176, 48, 40), ridge="y")
    c.cylinder(1.55, 1.55, 11, 0, 46, (200, 200, 205), top=(150, 150, 160))  # силос
    c.tree(0.3, 1.6, 0.9)
    c.tree(0.75, 1.75, 0.8)
    return c.result()


def sawmill() -> pygame.Surface:
    """Лесопилка: открытый навес с пилой, штабеля брёвен (видны торцы)."""
    c = SpriteCanvas(1, 1, 44)
    c.lot(0.02, 0.02, 0.98, 0.98, DIRT)
    c.soft_shadow(0.12, 0.12, 0.62, 0.6, 26)
    c.box(0.12, 0.12, 0.62, 0.6, 0, 18, (140, 100, 62))
    c.face_rect("left", 0.18, 0.56, 0.6, 0, 14, (70, 50, 32))         # открытая сторона
    c.circle(c.point(0.37, 0.6, 7), 4.5, (200, 200, 205))             # пила
    c.gable_roof(0.12, 0.12, 0.62, 0.6, 18, 12, (100, 85, 70), (140, 100, 62), ridge="x")
    # Штабель брёвен: торцы — кружки с годичными кольцами, пирамидкой
    for row, count in enumerate((4, 3, 2)):
        for i in range(count):
            a = 0.68 + 0.06 * row / 2 + i * 0.065
            x, y = c.point(a, 0.82, 3 + row * 5.5)
            c.circle((x, y), 3.2, (178, 128, 76))
            c.circle((x, y), 3.2, (120, 82, 48), 0.6)
            c.circle((x, y), 1.4, (205, 160, 105))
    c.line(c.point(0.66, 0.2, 2), c.point(0.95, 0.4, 2), (120, 85, 50), 3)  # бревно на земле
    return c.result()


def warehouse() -> pygame.Surface:
    """Склад: стены из профнастила, большие ворота, паллеты с грузом."""
    wall = (176, 160, 130)
    z = 2 * F
    c = SpriteCanvas(1, 1, z + 16)
    c.lot(0.02, 0.02, 0.98, 0.98, ASPHALT_LOT)
    c.soft_shadow(0.1, 0.1, 0.9, 0.78, z)
    c.box(0.1, 0.1, 0.9, 0.78, 0, z, wall)
    for i in range(1, 16):  # рёбра профнастила
        a = 0.1 + 0.8 * i / 16
        c.line(c.point(a, 0.78, 0), c.point(a, 0.78, z), shade(wall, 0.75), 0.5)
        b = 0.1 + 0.68 * i / 16
        c.line(c.point(0.9, b, 0), c.point(0.9, b, z), shade(wall, 0.55), 0.5)
    c.face_rect("left", 0.3, 0.7, 0.78, 0, 22, (120, 112, 100))       # рулонные ворота
    for k in range(1, 8):
        c.line(c.point(0.3, 0.78, k * 3), c.point(0.7, 0.78, k * 3), (95, 90, 80), 0.5)
    c.gable_roof(0.1, 0.1, 0.9, 0.78, z, 8, (150, 140, 120), wall, ridge="x", overhang=0.02)
    c.box(0.2, 0.84, 0.32, 0.94, 0, 5, (186, 150, 100))               # паллеты
    c.box(0.7, 0.84, 0.82, 0.94, 0, 8, (186, 150, 100))
    return c.result()


def factory() -> pygame.Surface:
    """Завод: кирпичный цех с крышей-«пилой» (стеклянные фонари), полосатая труба с дымом."""
    brick = (164, 88, 72)
    z = 3 * F
    c = SpriteCanvas(2, 2, z + 120)
    c.lot(0.03, 0.03, 1.97, 1.97, GRAVEL)
    c.soft_shadow(0.1, 0.4, 1.55, 1.9, z + 12)
    c.box(0.1, 0.4, 1.55, 1.9, 0, z, brick)
    c.window_rows(0.1, 0.4, 1.55, 1.9, 0, 3, per_tile=2.5, lit=0.15, seed=3,
                  glass=(90, 110, 125), frame=(200, 195, 185), width=0.6, height=0.55)
    c.face_rect("left", 0.55, 1.05, 1.9, 0, 24, (100, 96, 92))        # ворота цеха
    # Крыша-«пила»: наклонные скаты и вертикальное остекление, от дальних к ближним
    p = c.point
    teeth = 5
    for i in range(teeth):
        a = 0.4 + 1.5 * i / teeth
        b = 0.4 + 1.5 * (i + 1) / teeth
        h = 12
        c.poly([p(0.1, a, z), p(1.55, a, z), p(1.55, b, z + h), p(0.1, b, z + h)], (128, 122, 118))
        c.poly([p(1.55, a, z), p(1.55, b, z), p(1.55, b, z + h)], shade(brick, 0.66))  # торец
        c.poly([p(0.1, b, z), p(1.55, b, z), p(1.55, b, z + h), p(0.1, b, z + h)], (150, 190, 215))  # стекло
        c.line(p(0.1, b, z + h), p(1.55, b, z + h), (90, 90, 95), 0.6)
    # Труба с красно-белыми полосами и дымом
    cx, cy = 1.75, 0.45
    for i in range(6):
        color = (200, 60, 50) if i % 2 == 0 else (235, 235, 235)
        c.cylinder(cx, cy, 8 - i * 0.4, i * 18, (i + 1) * 18, color)
    # Дым из трубы — живой, рисуется в игре (render/effects.py, config.SMOKE_EMITTERS)
    c.cylinder(1.75, 1.3, 13, 0, 22, (175, 178, 185))                 # резервуар
    return c.result()


# ===========================================================================
# Коммунальные службы
# ===========================================================================

def power_plant() -> pygame.Surface:
    """Электростанция: две градирни с паром, машинный зал, трансформаторы."""
    c = SpriteCanvas(2, 2, 150)
    c.lot(0.03, 0.03, 1.97, 1.97, GRAVEL)
    # Порядок — от дальнего к ближнему: градирни (слева, дальше), потом машинный зал (ближе)
    c.soft_shadow(1.0, 0.95, 1.85, 1.85, 2 * F)
    for cx, cy in ((0.5, 0.5), (0.55, 1.2)):
        c.cooling_tower(cx, cy, 30, 19, 22, 86, (214, 214, 218))
    for x in (0.2, 0.4):  # трансформаторы
        c.box(x, 1.55, x + 0.14, 1.75, 0, 12, (120, 125, 130))
    c.box(1.0, 0.95, 1.85, 1.85, 0, 2 * F + 4, (196, 112, 72))
    c.window_rows(1.0, 0.95, 1.85, 1.85, 2, 2, per_tile=2.5, lit=0.3, seed=7,
                  glass=(80, 95, 110), frame=(225, 220, 210), width=0.55)
    c.flat_roof(1.0, 0.95, 1.85, 1.85, 2 * F + 4, (140, 100, 80))
    # Пар над градирнями — живой, рисуется в игре (render/effects.py)
    return c.result()


def solar_panel() -> pygame.Surface:
    """Солнечная станция: ряды наклонённых панелей с сеткой ячеек на гравии."""
    c = SpriteCanvas(1, 1, 18)
    c.lot(0.02, 0.02, 0.98, 0.98, GRAVEL)
    p = c.point
    for row in range(3):  # ряды: панели наклонены к зрителю (низ — ближе, верх — дальше)
        y0 = 0.1 + row * 0.28
        y1 = y0 + 0.2
        low, high = 3, 10
        frame = [p(0.08, y0, high), p(0.92, y0, high), p(0.92, y1, low), p(0.08, y1, low)]
        c.line(p(0.15, y1, 0), p(0.15, y1, low), (110, 110, 115), 0.8)  # ножки
        c.line(p(0.85, y1, 0), p(0.85, y1, low), (110, 110, 115), 0.8)
        c.poly(frame, (40, 62, 128))
        for k in range(1, 6):  # ячейки
            t = k / 6
            c.line(p(0.08 + 0.84 * t, y0, high), p(0.08 + 0.84 * t, y1, low), (95, 125, 190), 0.5)
        c.line(p(0.08, (y0 + y1) / 2, (low + high) / 2), p(0.92, (y0 + y1) / 2, (low + high) / 2),
               (95, 125, 190), 0.5)
        c.poly(frame, (190, 195, 200), 0.6)
    return c.result()


def water_tower() -> pygame.Surface:
    """Водонапорная башня: решётчатые опоры со связями, бак с конусной крышей, лестница."""
    c = SpriteCanvas(1, 1, 112)
    c.lot(0.02, 0.02, 0.98, 0.98, LAWN)
    p = c.point
    legs = [(0.28, 0.28), (0.72, 0.28), (0.72, 0.72), (0.28, 0.72)]
    top = [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]
    steel = (100, 105, 112)
    for (lx, ly), (tx, ty) in zip(legs, top):  # опоры
        c.line(p(lx, ly, 0), p(tx, ty, 58), steel, 1.6)
    for z0, z1 in ((0, 29), (29, 58)):  # диагональные связи
        for i in range(4):
            (ax, ay), (bx, by) = legs[i], legs[(i + 1) % 4]
            t0, t1 = z0 / 58, z1 / 58
            a0 = (ax + (top[i][0] - ax) * t0, ay + (top[i][1] - ay) * t0)
            b1 = (bx + (top[(i + 1) % 4][0] - bx) * t1, by + (top[(i + 1) % 4][1] - by) * t1)
            c.line(p(*a0, z0), p(*b1, z1), shade(steel, 1.2), 0.6)
    c.cylinder(0.5, 0.5, 24, 56, 84, (92, 172, 206))
    c.cone(0.5, 0.5, 25, 84, 14, (70, 140, 175))
    c.line(p(0.62, 0.62, 0), p(0.62, 0.62, 60), (60, 60, 65), 0.6)    # лестница
    return c.result()


def water_treatment() -> pygame.Surface:
    """Водоочистная: круглые отстойники с водой и мостиками, корпус управления, трубы."""
    c = SpriteCanvas(2, 2, 48)
    c.lot(0.03, 0.03, 1.97, 1.97, CONCRETE)
    for cx, cy in ((0.5, 0.5), (1.35, 0.5), (0.5, 1.35)):
        c.cylinder(cx, cy, 34, 0, 6, (170, 170, 175), top=(150, 150, 155))
        c.ground_ellipse(cx, cy, 29, 6, (64, 140, 180))
        c.ground_ellipse(cx, cy, 6, 6, (170, 170, 175))
        x, y = c.point(cx, cy, 8)
        c.line((x - 28 * c.k, y), (x + 28 * c.k, y), (230, 230, 235), 1.2)  # мостик-скребок
    c.line(c.point(0.85, 0.5, 2), c.point(1.0, 0.5, 2), (90, 95, 100), 2)  # трубы
    c.line(c.point(0.5, 0.85, 2), c.point(0.5, 1.0, 2), (90, 95, 100), 2)
    c.soft_shadow(1.15, 1.15, 1.85, 1.85, F + 8)
    c.box(1.15, 1.15, 1.85, 1.85, 0, F + 8, (70, 140, 160))
    c.window_rows(1.15, 1.15, 1.85, 1.85, 4, 1, per_tile=3, lit=0.2, seed=2, width=0.6)
    c.flat_roof(1.15, 1.15, 1.85, 1.85, F + 8, (90, 120, 130))
    return c.result()


# ===========================================================================
# Общественные здания
# ===========================================================================

def park() -> pygame.Surface:
    """Парк: газон, изогнутые дорожки, пруд, клумба, скамейка, лиственные деревья и ёлки."""
    c = SpriteCanvas(1, 1, 44)
    c.lot(0.02, 0.02, 0.98, 0.98, (118, 182, 96), (90, 150, 75))
    path = [c.point(0.02, 0.6), c.point(0.3, 0.52), c.point(0.55, 0.62), c.point(0.75, 0.5), c.point(0.98, 0.55)]
    pygame.draw.lines(c.surface, (222, 205, 160), False, path, c.px(5))
    c.ground_ellipse(0.72, 0.8, 16, 0, (80, 150, 200))               # пруд
    c.ground_ellipse(0.72, 0.8, 16, 0, (200, 190, 150), 1)
    c.ground_ellipse(0.3, 0.8, 9, 0, (220, 90, 120))                 # клумба
    c.ground_ellipse(0.3, 0.8, 5, 0, (245, 210, 80))
    c.bench(0.5, 0.45)
    for x, y, s, kind in ((0.2, 0.2, 1.0, "round"), (0.65, 0.18, 0.9, "pine"),
                          (0.42, 0.3, 0.7, "round"), (0.88, 0.3, 0.8, "pine")):
        c.tree(x, y, s, kind)
    return c.result()


def school() -> pygame.Surface:
    """Школа: кирпичное здание буквой «Г», флаг на крыше, спортплощадка с разметкой."""
    brick = (212, 132, 88)
    z = 2 * F + 6
    c = SpriteCanvas(2, 2, z + 50)
    c.lot(0.03, 0.03, 1.97, 1.97, PAVING)
    # Спортплощадка в ближнем углу
    c.quad(1.2, 1.0, 1.9, 1.9, 0, (90, 150, 95))
    c.quad(1.25, 1.05, 1.85, 1.85, 0, (240, 240, 240), 0.8)
    c.line(c.point(1.25, 1.45), c.point(1.85, 1.45), (240, 240, 240), 0.8)
    c.ground_ellipse(1.55, 1.45, 8, 0, (240, 240, 240), 0.8)
    # Крыло вдоль x (дальнее) и основной корпус вдоль y
    c.soft_shadow(0.15, 0.15, 1.85, 0.75, z)
    c.box(0.15, 0.15, 1.85, 0.75, 0, z, brick)
    c.window_rows(0.15, 0.15, 1.85, 0.75, 4, 2, per_tile=2.5, lit=0.2, seed=4, width=0.6)
    c.flat_roof(0.15, 0.15, 1.85, 0.75, z, (150, 110, 90))
    c.soft_shadow(0.15, 0.75, 0.95, 1.85, z)
    c.box(0.15, 0.75, 0.95, 1.85, 0, z, brick)
    c.window_rows(0.15, 0.75, 0.95, 1.85, 4, 2, per_tile=2.5, lit=0.2, seed=5, width=0.6)
    c.door("left", 0.42, 0.68, 1.85, 14, (90, 60, 40))
    c.flat_roof(0.15, 0.75, 0.95, 1.85, z, (150, 110, 90))
    # Флаг
    fx, fy = c.point(0.55, 0.45, z)
    c.line((fx, fy), (fx, fy - 40 * c.k), (225, 225, 225), 0.8)
    c.poly([(fx, fy - 40 * c.k), (fx + 16 * c.k, fy - 35 * c.k), (fx, fy - 30 * c.k)], (220, 60, 60))
    return c.result()


def hospital() -> pygame.Surface:
    """Больница: белый корпус, красный крест на стене и на крыше, площадка для скорой."""
    wall = (238, 240, 244)
    z = 4 * F + 6
    c = SpriteCanvas(2, 2, z + 26)
    c.lot(0.03, 0.03, 1.97, 1.97, PAVING)
    c.soft_shadow(0.15, 0.15, 1.85, 1.45, z)
    c.box(0.15, 0.15, 1.85, 1.45, 0, z, wall)
    c.window_rows(0.15, 0.15, 1.85, 1.45, 4, 4, per_tile=2.8, lit=0.15, seed=9,
                  glass=(130, 180, 220), frame=(205, 210, 220), width=0.6)
    # Крест на стене (над входом)
    c.face_rect("left", 0.92, 1.08, 1.45, z - 26, z - 6, (220, 40, 40))
    c.face_rect("left", 0.82, 1.18, 1.45, z - 19, z - 13, (220, 40, 40))
    # Козырёк приёмного отделения и машина скорой помощи
    c.box(0.7, 1.45, 1.3, 1.7, 13, 15, (200, 205, 215))
    c.door("left", 0.85, 1.15, 1.45, 13, (110, 160, 200))
    c.car(1.55, 1.7, (245, 245, 245), along="y")
    c.flat_roof(0.15, 0.15, 1.85, 1.45, z, (200, 202, 208))
    c.quad(0.9, 0.5, 1.1, 1.1, z, (220, 40, 40))                      # крест на крыше
    c.quad(0.7, 0.7, 1.3, 0.9, z, (220, 40, 40))
    return c.result()


def police() -> pygame.Surface:
    """Полиция: синее здание с белым поясом, вывеска, мигалка на крыше, патрульная машина."""
    blue = (66, 92, 168)
    z = 2 * F + 4
    c = SpriteCanvas(1, 1, z + 18)
    c.lot(0.02, 0.02, 0.98, 0.98, PAVING)
    c.soft_shadow(0.12, 0.12, 0.84, 0.68, z)
    c.box(0.12, 0.12, 0.84, 0.68, 0, z, blue)
    c.face_rect("left", 0.12, 0.84, 0.68, F + 1, F + 4, (240, 240, 245))   # белый пояс
    c.window_rows(0.12, 0.12, 0.84, 0.68, 2, 2, per_tile=2.6, lit=0.3, seed=1, width=0.55, skip_floors=1)
    c.door("left", 0.4, 0.56, 0.68, 13, (40, 50, 90))
    c.face_rect("left", 0.22, 0.36, 0.68, 6, 13, (240, 240, 245))     # табличка
    c.flat_roof(0.12, 0.12, 0.84, 0.68, z, (90, 100, 130))
    c.box(0.38, 0.36, 0.48, 0.44, z, z + 4, (235, 50, 50), outline=False)   # мигалка
    c.box(0.48, 0.36, 0.58, 0.44, z, z + 4, (60, 110, 240), outline=False)
    c.car(0.62, 0.84, (240, 240, 245), along="x")
    return c.result()


def fire_station() -> pygame.Surface:
    """Пожарная часть: красное здание, двое ворот гаража, башня для сушки рукавов."""
    red = (198, 56, 50)
    z = 2 * F + 4
    c = SpriteCanvas(1, 1, 4 * F + 18)
    c.lot(0.02, 0.02, 0.98, 0.98, ASPHALT_LOT)
    c.soft_shadow(0.1, 0.1, 0.9, 0.74, 4 * F)
    c.box(0.1, 0.1, 0.3, 0.3, 0, 4 * F + 4, shade(red, 0.9))          # башня (дальний угол)
    c.window("right", 0.15, 0.25, 0.3, 3 * F, 3 * F + 10)
    c.flat_roof(0.1, 0.1, 0.3, 0.3, 4 * F + 4, (120, 50, 45))
    c.box(0.1, 0.3, 0.9, 0.74, 0, z, red)
    c.box(0.3, 0.1, 0.9, 0.3, 0, z, red)
    for a0, a1 in ((0.16, 0.46), (0.54, 0.84)):  # ворота гаража с окошками
        c.face_rect("left", a0, a1, 0.74, 0, 17, (238, 238, 232))
        c.face_rect("left", a0 + 0.02, a1 - 0.02, 0.74, 1, 16, (110, 40, 38))
        for k in range(1, 5):
            c.line(c.point(a0 + 0.02, 0.74, k * 3.5), c.point(a1 - 0.02, 0.74, k * 3.5), (150, 60, 55), 0.5)
        c.face_rect("left", a0 + 0.04, a1 - 0.04, 0.74, 11, 14.5, (160, 200, 230))
    c.window_rows(0.1, 0.3, 0.9, 0.74, 2, 2, per_tile=2.5, lit=0.25, seed=8, width=0.55, skip_floors=1)
    c.flat_roof(0.1, 0.3, 0.9, 0.74, z, (120, 50, 45))
    c.flat_roof(0.3, 0.1, 0.9, 0.3, z, (120, 50, 45))
    return c.result()


# ===========================================================================
# Сети (картинки для магазина и «призрака» при строительстве)
# ===========================================================================

def power_line() -> pygame.Surface:
    """Линия электропередач: два деревянных столба с перекладинами и провисающие провода."""
    c = SpriteCanvas(1, 1, 52)
    c.lot(0.05, 0.05, 0.95, 0.95, LAWN)
    p = c.point
    poles = [(0.2, 0.5), (0.8, 0.5)]
    for x, y in poles:
        c.line(p(x, y, 0), p(x, y, 40), (110, 80, 50), 2.2)
        a, b = p(x, y - 0.12, 37), p(x, y + 0.12, 37)
        c.line(a, b, (90, 65, 40), 1.6)  # перекладина
    for dy in (-0.1, 0.1):  # два провода с провисанием
        points = []
        for i in range(9):
            t = i / 8
            x = 0.2 + 0.6 * t
            sag = 4 * t * (1 - t) * 6
            points.append(p(x, 0.5 + dy, 37 - sag))
        pygame.draw.lines(c.surface, (40, 40, 46), False, points, c.px(0.9))
    return c.result()


def water_pipe() -> pygame.Surface:
    """Водопровод: раскопанный участок с синей трубой и люком."""
    c = SpriteCanvas(1, 1, 14)
    c.lot(0.05, 0.05, 0.95, 0.95, (140, 112, 80))  # раскопанная земля
    p = c.point
    pygame.draw.line(c.surface, (30, 70, 120), p(0.05, 0.5, 4), p(0.95, 0.5, 4), c.px(9))
    pygame.draw.line(c.surface, (70, 150, 230), p(0.05, 0.5, 5), p(0.95, 0.5, 5), c.px(6))
    pygame.draw.line(c.surface, (150, 205, 255), p(0.05, 0.5, 7), p(0.95, 0.5, 7), c.px(1.6))
    for x in (0.3, 0.7):  # стыки
        c.ground_ellipse(x, 0.5, 6, 5, (40, 90, 150))
    c.ground_ellipse(0.75, 0.2, 9, 0, (90, 92, 100))  # люк
    c.ground_ellipse(0.75, 0.2, 9, 0, (60, 62, 70), 1.2)
    return c.result()


def traffic_light() -> pygame.Surface:
    """Светофор на перекрёстке: асфальт с «зебрами», столб и три огня."""
    c = road_tile("asphalt", 15)  # перекрёсток
    canvas = SpriteCanvas(1, 1, 50)
    canvas.surface.blit(pygame.transform.smoothscale(c, (canvas.surface.get_width(),
                                                         round(c.get_height() * canvas.k / canvas.out_scale))),
                        (0, canvas.surface.get_height() - round(c.get_height() * canvas.k / canvas.out_scale)))
    p = canvas.point
    canvas.line(p(0.8, 0.2, 0), p(0.8, 0.2, 36), (70, 70, 76), 1.8)
    x, y = p(0.8, 0.2, 36)
    box = pygame.Rect(0, 0, round(10 * canvas.k), round(26 * canvas.k))
    box.midbottom = (round(x), round(y + 2 * canvas.k))
    pygame.draw.rect(canvas.surface, (35, 35, 40), box, border_radius=canvas.px(2))
    for i, color in enumerate(((235, 55, 45), (250, 200, 50), (70, 225, 95))):
        pygame.draw.circle(canvas.surface, color, (box.centerx, box.top + box.height * (0.2 + 0.3 * i)), 3.2 * canvas.k)
    return canvas.result()


# ===========================================================================
# Таблицы: что чем рисовать
# ===========================================================================

BUILDINGS: dict[str, Callable[[], pygame.Surface]] = {
    "house_small": house_small,
    "cottage": cottage,
    "apartment": apartment,
    "skyscraper": skyscraper,
    "kiosk": kiosk,
    "shop": shop,
    "office": office,
    "mall": mall,
    "farm": farm,
    "sawmill": sawmill,
    "warehouse": warehouse,
    "factory": factory,
    "power_plant": power_plant,
    "solar_panel": solar_panel,
    "water_tower": water_tower,
    "water_treatment": water_treatment,
    "park": park,
    "school": school,
    "hospital": hospital,
    "police": police,
    "fire_station": fire_station,
    "power_line": power_line,
    "water_pipe": water_pipe,
    "traffic_light": traffic_light,
}

# Дороги: id товара -> стиль (см. iso_sprites.road_tile)
ROADS = {"road_dirt": "dirt", "road_asphalt": "asphalt", "avenue": "avenue", "bridge": "bridge"}

GRASS_VARIANTS = 4
DECOR = ("tree", "pine", "bush", "flowers", "rock")


def category_image(sprites: list[pygame.Surface]) -> pygame.Surface:
    """Картинка категории: до трёх зданий категории рядом, одинаковой высоты."""
    height = 150
    scaled = [pygame.transform.smoothscale(s, (round(s.get_width() * height / s.get_height()), height))
              for s in sprites[:3]]
    overlap = 26
    width = sum(s.get_width() for s in scaled) - overlap * (len(scaled) - 1)
    surface = pygame.Surface((max(1, width), height), pygame.SRCALPHA)
    x = 0
    for s in scaled:
        surface.blit(s, (x, 0))
        x += s.get_width() - overlap
    return surface


def main() -> int:
    pygame.init()  # окно не нужно: рисуем на поверхностях в памяти и сохраняем в файлы
    catalog = load_catalog(SHOP_DATA_FILE)
    for folder in ("buildings", "terrain", "categories", "roads"):
        (ASSETS / folder).mkdir(parents=True, exist_ok=True)

    sprites: dict[str, pygame.Surface] = {}
    for item in catalog.items:
        if item.id in ROADS:
            style = ROADS[item.id]
            folder = ASSETS / "roads" / item.id
            folder.mkdir(parents=True, exist_ok=True)
            for mask in range(16):  # 16 вариантов по соседям
                pygame.image.save(road_tile(style, mask), str(folder / f"{mask}.png"))
            # Картинка для магазина и запасная — прямой участок
            sprites[item.id] = road_tile(style, NORTH | SOUTH)
        elif item.id in BUILDINGS:
            sprites[item.id] = BUILDINGS[item.id]()
        else:
            print(f"  нет рисунка для «{item.id}» — в игре будет простая коробка")
            continue
        pygame.image.save(sprites[item.id], str(ASSETS / "buildings" / f"{item.id}.png"))
        print(f"  {item.id}")

    for variant in range(GRASS_VARIANTS):
        pygame.image.save(grass_tile(TILE_COLORS["grass"], variant), str(ASSETS / "terrain" / f"grass_{variant}.png"))
    (ASSETS / "decor").mkdir(parents=True, exist_ok=True)
    for kind in DECOR:
        for variant in range(3):
            pygame.image.save(decor_sprite(kind, variant), str(ASSETS / "decor" / f"{kind}_{variant}.png"))

    for category in catalog.categories:
        items = [sprites[i.id] for i in catalog.items_in(category.id) if i.id in sprites]
        if items:
            pygame.image.save(category_image(items), str(ASSETS / "categories" / f"{category.id}.png"))

    print(f"Готово: зданий {len(sprites)}, дорог {len(ROADS)} × 16, трава {GRASS_VARIANTS}, природа {len(DECOR)} × 3, "
          f"категорий {len(catalog.categories)}")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
