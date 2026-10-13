"""Генератор изометрических текстур: все здания, местность и категории магазина.

Рисует картинки средствами pygame (коробки, крыши, окна, деревья — см.
city_builder/render/iso_sprites.py) и сохраняет PNG в:
    assets/buildings/<id>.png    — здания (id из data/shop.json)
    assets/terrain/grass.png, water.png — клетки земли
    assets/categories/<id>.png   — картинки категорий магазина

Запуск из папки проекта:
    python tools/make_placeholder_images.py

Существующие файлы ПЕРЕЗАПИСЫВАЮТСЯ. Если вы нарисовали свои картинки
с теми же именами — не запускайте скрипт (или уберите их из DRAWINGS).

Это «программистская графика»: её задача — чтобы игра выглядела цельно,
пока нет картинок от художника. Формат картинок описан в README («Картинки»).
"""

import sys
from collections.abc import Callable
from pathlib import Path

# Скрипт лежит в tools/, а модули игры — в city_builder/ уровнем выше.
# Добавляем папку проекта в путь поиска модулей, чтобы import city_builder работал.
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import pygame  # noqa: E402  (импорт не в начале файла — из-за строки выше)

from city_builder.config import SHOP_DATA_FILE  # noqa: E402
from city_builder.data.catalog import load_catalog  # noqa: E402
from city_builder.render.iso_sprites import (  # noqa: E402
    FLOOR_HEIGHT as F,
    SHADE_LEFT,
    SHADE_RIGHT,
    SpriteCanvas,
    flat_tile,
    shade,
)

ASSETS = PROJECT_DIR / "assets"

WALL = (232, 222, 200)     # светлые стены домов
GLASS = (110, 160, 210)    # стекло
CONCRETE = (175, 175, 180)
DARK = (60, 60, 66)


# --- Маленькие помощники для деталей на стенах ---

def left_quad(c: SpriteCanvas, xa: float, xb: float, y: float, za: float, zb: float, color) -> None:
    """Прямоугольник на ЛЕВОЙ видимой стене (стена вдоль x на линии y): дверь, вывеска."""
    p = c.point
    pygame.draw.polygon(c.surface, color, [p(xa, y, za), p(xb, y, za), p(xb, y, zb), p(xa, y, zb)])


def right_quad(c: SpriteCanvas, ya: float, yb: float, x: float, za: float, zb: float, color) -> None:
    """Прямоугольник на ПРАВОЙ видимой стене (стена вдоль y на линии x)."""
    p = c.point
    pygame.draw.polygon(c.surface, color, [p(x, yb, za), p(x, ya, za), p(x, ya, zb), p(x, yb, zb)])


def awning(c: SpriteCanvas, x0: float, x1: float, y: float, z: float, stripes: int = 6) -> None:
    """Полосатый навес над витриной на левой стене."""
    for i in range(stripes):
        a = x0 + (x1 - x0) * i / stripes
        b = x0 + (x1 - x0) * (i + 1) / stripes
        color = (220, 60, 60) if i % 2 == 0 else (245, 245, 245)
        p = c.point
        pygame.draw.polygon(c.surface, color, [p(a, y, z), p(b, y, z), p(b, y + 0.12, z - 6), p(a, y + 0.12, z - 6)])


def smoke(c: SpriteCanvas, x: float, y: float, z: float) -> None:
    """Клубы дыма над трубой."""
    px, py = c.point(x, y, z)
    for i, r in enumerate((7, 9, 11)):
        pygame.draw.circle(c.surface, (210, 210, 215, 170 - i * 40), (px + i * 6, py - 8 - i * 12), r)


# --- Дороги (плоские) ---

def road(color, noise: float) -> Callable[[], pygame.Surface]:
    return lambda: flat_tile(color, noise=noise, seed=sum(color))


def bridge() -> pygame.Surface:
    c = SpriteCanvas(1, 1, 18)
    wood = (160, 120, 80)
    c.box(0, 0.12, 1, 0.88, 0, 6, wood, top=(185, 145, 100))
    for i in range(1, 8):  # доски настила
        x = i / 8
        pygame.draw.line(c.surface, shade(wood, 0.7), c.point(x, 0.12, 6), c.point(x, 0.88, 6), 1)
    for y in (0.14, 0.86):  # перила
        pygame.draw.line(c.surface, (90, 70, 50), c.point(0, y, 14), c.point(1, y, 14), 2)
        for x in (0.1, 0.5, 0.9):
            pygame.draw.line(c.surface, (90, 70, 50), c.point(x, y, 6), c.point(x, y, 14), 2)
    return c.surface


# --- Жилые здания ---

def house(roof, floors: int, wall=WALL, tree: bool = False) -> Callable[[], pygame.Surface]:
    def draw() -> pygame.Surface:
        z = floors * F + 4
        c = SpriteCanvas(1, 1, z + 34)
        c.shadow(0.2, 0.2, 0.8, 0.8)
        if tree:
            c.tree(0.12, 0.15, 0.8)
        c.box(0.2, 0.2, 0.8, 0.8, 0, z, wall)
        c.windows(0.2, 0.2, 0.8, 0.8, 0, floors, GLASS, per_tile=2, lit=0.3, seed=floors)
        left_quad(c, 0.45, 0.6, 0.8, 0, 13, (120, 80, 50))  # дверь
        c.pyramid_roof(0.15, 0.15, 0.85, 0.85, z, 26, roof)
        return c.surface
    return draw


def tower(color, floors: int, helipad: bool = False, per_tile: int = 3) -> Callable[[], pygame.Surface]:
    def draw() -> pygame.Surface:
        z = floors * F + 6
        c = SpriteCanvas(2, 2, z + 20)
        c.shadow(0.15, 0.15, 1.85, 1.85, 0.4)
        c.box(0.15, 0.15, 1.85, 1.85, 0, z, color)
        c.windows(0.15, 0.15, 1.85, 1.85, 0, floors, shade(color, 0.7), per_tile=per_tile,
                  lit=0.3, seed=floors)
        if helipad:
            c.ellipse(1, 1, 34, z, (70, 70, 80))
            c.ellipse(1, 1, 34, z, (240, 240, 240), 3)
            hx, hy = c.point(1, 1, z)
            for dx in (-7, 7):
                pygame.draw.line(c.surface, (240, 240, 240), (hx + dx, hy - 7), (hx + dx, hy + 7), 3)
            pygame.draw.line(c.surface, (240, 240, 240), (hx - 7, hy), (hx + 7, hy), 3)
        else:
            c.box(0.4, 0.4, 0.8, 0.7, z, z + 12, CONCRETE)     # выход на крышу
            c.box(1.2, 1.1, 1.5, 1.4, z, z + 8, (150, 150, 155))  # кондиционер
        return c.surface
    return draw


# --- Коммерция ---

def kiosk() -> pygame.Surface:
    c = SpriteCanvas(1, 1, 40)
    c.shadow(0.3, 0.3, 0.7, 0.7)
    c.box(0.3, 0.3, 0.7, 0.7, 0, 16, (230, 200, 120))
    left_quad(c, 0.35, 0.65, 0.7, 4, 12, (250, 240, 200))  # окошко
    awning(c, 0.28, 0.72, 0.7, 18, 4)
    return c.surface


def shop() -> pygame.Surface:
    c = SpriteCanvas(1, 1, 46)
    c.shadow(0.1, 0.1, 0.9, 0.9)
    c.box(0.1, 0.1, 0.9, 0.9, 0, F + 8, (225, 225, 235))
    left_quad(c, 0.15, 0.85, 0.9, 2, 16, shade(GLASS, 1.1))   # витрина
    right_quad(c, 0.2, 0.8, 0.9, 6, 16, shade(GLASS, 0.75))
    awning(c, 0.1, 0.9, 0.9, F + 6)
    c.box(0.15, 0.15, 0.4, 0.35, F + 8, F + 14, (150, 150, 155))  # кондиционер на крыше
    return c.surface


def mall() -> pygame.Surface:
    z = 2 * F + 6
    c = SpriteCanvas(2, 2, z + 24)
    c.shadow(0.1, 0.1, 1.9, 1.9, 0.4)
    c.box(0.1, 0.1, 1.9, 1.9, 0, z, (230, 230, 240))
    left_quad(c, 0.2, 1.8, 1.9, 2, F, shade(GLASS, 1.1))
    right_quad(c, 0.2, 1.8, 1.9, 2, F, shade(GLASS, 0.75))
    left_quad(c, 0.7, 1.3, 1.9, F + 6, z - 4, (70, 110, 190))  # вывеска
    for x, y in ((0.4, 0.4), (0.8, 0.4), (1.2, 0.4)):
        c.box(x, y, x + 0.25, y + 0.2, z, z + 8, (150, 150, 155))
    return c.surface


# --- Промышленность ---

def farm() -> pygame.Surface:
    c = SpriteCanvas(2, 2, 60)
    colors = [(200, 180, 80), (120, 170, 70), (200, 180, 80), (150, 190, 90)]
    for i, color in enumerate(colors):
        c.diamond(0.05, 0.05 + i * 0.47, 1.95, 0.45 + i * 0.47, 0, color)
        for k in range(1, 12):  # борозды
            x = 0.05 + 1.9 * k / 12
            pygame.draw.line(c.surface, shade(color, 0.8), c.point(x, 0.08 + i * 0.47), c.point(x, 0.42 + i * 0.47), 1)
    c.shadow(1.3, 1.3, 1.85, 1.85)
    c.box(1.3, 1.3, 1.85, 1.85, 0, 22, (180, 50, 40))
    left_quad(c, 1.45, 1.7, 1.85, 0, 16, (120, 40, 30))  # ворота амбара
    c.pyramid_roof(1.25, 1.25, 1.9, 1.9, 22, 20, (90, 60, 50))
    return c.surface


def sawmill() -> pygame.Surface:
    c = SpriteCanvas(1, 1, 44)
    c.shadow(0.1, 0.15, 0.6, 0.85)
    c.box(0.1, 0.15, 0.6, 0.85, 0, F + 4, (140, 100, 60))
    c.pyramid_roof(0.05, 0.1, 0.65, 0.9, F + 4, 14, (100, 80, 60))
    for i in range(3):  # штабель брёвен
        c.cylinder(0.78, 0.25 + i * 0.22, 7, 0, 10, (170, 120, 70))
    return c.surface


def warehouse() -> pygame.Surface:
    z = 2 * F
    c = SpriteCanvas(1, 1, z + 14)
    c.shadow(0.1, 0.1, 0.9, 0.9)
    c.box(0.1, 0.1, 0.9, 0.9, 0, z, (160, 140, 110))
    left_quad(c, 0.3, 0.7, 0.9, 0, 22, (110, 95, 80))  # ворота
    for i in range(1, 5):  # рёбра крыши
        y = 0.1 + 0.8 * i / 5
        pygame.draw.line(c.surface, shade((160, 140, 110), 0.8), c.point(0.1, y, z), c.point(0.9, y, z), 1)
    return c.surface


def factory() -> pygame.Surface:
    z = 3 * F
    c = SpriteCanvas(2, 2, z + 110)
    c.shadow(0.1, 0.3, 1.6, 1.9, 0.4)
    c.box(0.1, 0.3, 1.6, 1.9, 0, z, (150, 90, 80))
    c.windows(0.1, 0.3, 1.6, 1.9, 0, 3, (90, 60, 55), per_tile=3, lit=0.15, seed=3)
    for i in range(4):  # пилообразная крыша цеха
        y = 0.3 + i * 0.4
        c.box(0.15, y, 1.55, y + 0.2, z, z + 10, (120, 110, 105))
    c.cylinder(1.75, 0.35, 12, 0, z + 60, (110, 100, 100))  # дымовая труба
    smoke(c, 1.75, 0.35, z + 60)
    return c.surface


# --- Коммунальные службы ---

def power_plant() -> pygame.Surface:
    c = SpriteCanvas(2, 2, 140)
    c.shadow(0.1, 0.1, 1.9, 1.9, 0.3)
    c.box(1.0, 0.9, 1.9, 1.9, 0, 2 * F, (190, 100, 60))
    c.windows(1.0, 0.9, 1.9, 1.9, 0, 2, (110, 70, 50), per_tile=3, lit=0.2, seed=7)
    for cx, cy in ((0.5, 0.55), (0.55, 1.35)):  # градирни
        c.cylinder(cx, cy, 26, 0, 80, (205, 205, 210))
        smoke(c, cx, cy, 80)
    return c.surface


def solar_panel() -> pygame.Surface:
    c = SpriteCanvas(1, 1, 16)
    c.diamond(0.05, 0.05, 0.95, 0.95, 0, (150, 150, 150))
    for x0 in (0.1, 0.52):
        for y0 in (0.1, 0.52):
            c.box(x0, y0, x0 + 0.38, y0 + 0.38, 0, 6, (40, 60, 130), top=(60, 90, 170))
            pygame.draw.line(c.surface, (140, 170, 230), c.point(x0 + 0.19, y0, 6), c.point(x0 + 0.19, y0 + 0.38, 6), 1)
    return c.surface


def water_tower() -> pygame.Surface:
    c = SpriteCanvas(1, 1, 110)
    c.shadow(0.3, 0.3, 0.7, 0.7)
    for x, y in ((0.35, 0.35), (0.65, 0.35), (0.35, 0.65), (0.65, 0.65)):  # опоры
        pygame.draw.line(c.surface, (90, 90, 95), c.point(x, y, 0), c.point(0.5, 0.5, 60), 3)
    c.cylinder(0.5, 0.5, 22, 55, 95, (90, 170, 200))
    return c.surface


def water_treatment() -> pygame.Surface:
    c = SpriteCanvas(2, 2, 50)
    c.diamond(0.05, 0.05, 1.95, 1.95, 0, CONCRETE)
    for cx, cy in ((0.55, 0.55), (1.4, 0.55), (0.55, 1.4)):  # отстойники
        c.ellipse(cx, cy, 30, 0, (120, 120, 125))
        c.ellipse(cx, cy, 25, 0, (70, 150, 180))
    c.shadow(1.15, 1.15, 1.85, 1.85)
    c.box(1.15, 1.15, 1.85, 1.85, 0, F + 6, (60, 140, 160))
    c.windows(1.15, 1.15, 1.85, 1.85, 0, 1, (40, 90, 110), per_tile=3, seed=2)
    return c.surface


# --- Общественные здания ---

def park() -> pygame.Surface:
    c = SpriteCanvas(1, 1, 40)
    c.diamond(0.03, 0.03, 0.97, 0.97, 0, (110, 180, 90))
    pygame.draw.line(c.surface, (220, 200, 150), c.point(0.05, 0.5), c.point(0.95, 0.5), 5)  # дорожка
    for x, y, s in ((0.25, 0.22, 1.0), (0.72, 0.25, 0.8), (0.3, 0.78, 0.9), (0.78, 0.75, 1.1)):
        c.tree(x, y, s)
    return c.surface


def public_building(wall, floors: int, extra=None) -> Callable[[], pygame.Surface]:
    """Общественное здание 2×2 (школа, больница) с деталями на крыше."""
    def draw() -> pygame.Surface:
        z = floors * F + 6
        c = SpriteCanvas(2, 2, z + 50)
        c.shadow(0.15, 0.15, 1.85, 1.85, 0.4)
        c.box(0.15, 0.15, 1.85, 1.85, 0, z, wall)
        c.windows(0.15, 0.15, 1.85, 1.85, 0, floors, GLASS, per_tile=3, lit=0.2, seed=floors)
        left_quad(c, 0.85, 1.15, 1.85, 0, 16, (110, 80, 60))  # вход
        if extra:
            extra(c, z)
        return c.surface
    return draw


def school_extra(c: SpriteCanvas, z: float) -> None:
    fx, fy = c.point(0.5, 0.5, z)
    pygame.draw.line(c.surface, (220, 220, 220), (fx, fy), (fx, fy - 40), 2)  # флагшток
    pygame.draw.polygon(c.surface, (220, 60, 60), [(fx, fy - 40), (fx + 18, fy - 34), (fx, fy - 28)])


def hospital_extra(c: SpriteCanvas, z: float) -> None:
    c.diamond(0.85, 0.5, 1.15, 1.5, z, (220, 40, 40))  # красный крест на крыше
    c.diamond(0.5, 0.85, 1.5, 1.15, z, (220, 40, 40))


def small_service(wall, floors: int, extra=None) -> Callable[[], pygame.Surface]:
    """Здание 1×1 (полиция, пожарная часть)."""
    def draw() -> pygame.Surface:
        z = floors * F + 4
        c = SpriteCanvas(1, 1, z + 20)
        c.shadow(0.1, 0.1, 0.9, 0.9)
        c.box(0.1, 0.1, 0.9, 0.9, 0, z, wall)
        c.windows(0.1, 0.1, 0.9, 0.9, F, floors - 1, GLASS, per_tile=3, lit=0.3, seed=floors)
        if extra:
            extra(c, z)
        return c.surface
    return draw


def police_extra(c: SpriteCanvas, z: float) -> None:
    left_quad(c, 0.4, 0.6, 0.9, 0, 14, (40, 50, 90))  # дверь
    c.box(0.4, 0.45, 0.5, 0.55, z, z + 5, (230, 50, 50))   # мигалка
    c.box(0.5, 0.45, 0.6, 0.55, z, z + 5, (60, 110, 240))


def fire_extra(c: SpriteCanvas, z: float) -> None:
    for a, b in ((0.15, 0.45), (0.55, 0.85)):  # ворота гаража
        left_quad(c, a, b, 0.9, 0, 15, (90, 30, 30))
        for k in range(1, 4):
            zz = k * 4
            pygame.draw.line(c.surface, (140, 50, 50), c.point(a, 0.9, zz), c.point(b, 0.9, zz), 1)


# --- Местность ---

def grass() -> pygame.Surface:
    return flat_tile((86, 152, 74), noise=1.0, seed=1, edge=(0, 0, 0, 22))


def water() -> pygame.Surface:
    surf = flat_tile((52, 108, 186), noise=0.4, seed=2, edge=(0, 0, 0, 18))
    for (x, y) in ((40, 26), (70, 36), (56, 18)):  # блики волн
        pygame.draw.line(surf, (120, 170, 230), (x, y), (x + 12, y), 2)
    return surf


# Что рисовать: id товара из shop.json -> функция рисования
BUILDINGS: dict[str, Callable[[], pygame.Surface]] = {
    "road_dirt": road((150, 120, 80), 0.9),
    "road_asphalt": road((78, 78, 84), 0.6),
    "avenue": road((58, 58, 64), 0.5),
    "bridge": bridge,
    "house_small": house((200, 120, 70), 1),
    "cottage": house((170, 80, 60), 2, wall=(235, 215, 190), tree=True),
    "apartment": tower((175, 165, 160), 6),
    "skyscraper": tower((120, 165, 205), 14, helipad=True, per_tile=4),
    "kiosk": kiosk,
    "shop": shop,
    "office": tower((140, 180, 200), 5, per_tile=4),
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
    "school": public_building((215, 140, 90), 2, school_extra),
    "hospital": public_building((235, 235, 240), 4, hospital_extra),
    "police": small_service((70, 90, 170), 2, police_extra),
    "fire_station": small_service((200, 60, 55), 2, fire_extra),
}

TERRAIN = {"grass": grass, "water": water}


def category_image(sprites: list[pygame.Surface]) -> pygame.Surface:
    """Картинка категории: до трёх зданий категории рядом, одинаковой высоты."""
    height = 120
    scaled = [pygame.transform.smoothscale(s, (round(s.get_width() * height / s.get_height()), height))
              for s in sprites[:3]]
    width = sum(s.get_width() for s in scaled) - 20 * (len(scaled) - 1)  # с небольшим нахлёстом
    surface = pygame.Surface((max(1, width), height), pygame.SRCALPHA)
    x = 0
    for s in scaled:
        surface.blit(s, (x, 0))
        x += s.get_width() - 20
    return surface


def main() -> int:
    pygame.init()  # окно не нужно: рисуем на поверхностях в памяти и сохраняем в файлы
    catalog = load_catalog(SHOP_DATA_FILE)
    for folder in ("buildings", "terrain", "categories"):
        (ASSETS / folder).mkdir(parents=True, exist_ok=True)

    sprites: dict[str, pygame.Surface] = {}
    for item in catalog.items:
        draw = BUILDINGS.get(item.id)
        if draw is None:
            print(f"  нет рисунка для «{item.id}» — в игре будет простая коробка")
            continue
        sprites[item.id] = draw()
        pygame.image.save(sprites[item.id], str(ASSETS / "buildings" / f"{item.id}.png"))

    for name, draw in TERRAIN.items():
        pygame.image.save(draw(), str(ASSETS / "terrain" / f"{name}.png"))

    for category in catalog.categories:
        items = [sprites[i.id] for i in catalog.items_in(category.id) if i.id in sprites]
        if items:
            pygame.image.save(category_image(items), str(ASSETS / "categories" / f"{category.id}.png"))

    print(f"Готово: зданий {len(sprites)}, местность {len(TERRAIN)}, категорий {len(catalog.categories)}")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
