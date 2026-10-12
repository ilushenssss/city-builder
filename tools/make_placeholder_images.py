"""Генератор тестовых картинок-заглушек для зданий.

Рисует простые картинки (вид сверху) средствами pygame и сохраняет их
в assets/buildings/ и assets/categories/. Нужен, чтобы проверить загрузку
картинок, пока нет настоящих.

Запуск из папки проекта:
    python tools/make_placeholder_images.py

Существующие файлы ПЕРЕЗАПИСЫВАЮТСЯ. Если вы уже положили свои картинки
с теми же именами — не запускайте скрипт или удалите их имена из DRAWINGS.

Картинки рисуются только для части товаров — остальные специально
остаются без картинок, чтобы было видно запасной вариант (цвет).
"""

import random
import sys
from pathlib import Path

import pygame

# Скрипт лежит в tools/, проект — на уровень выше
PROJECT_DIR = Path(__file__).resolve().parent.parent
BUILDINGS_DIR = PROJECT_DIR / "assets" / "buildings"
CATEGORIES_DIR = PROJECT_DIR / "assets" / "categories"

T = 64  # пикселей на одну клетку. 64, а не 32, — чтобы при приближении не было размыто

SHADOW = (0, 0, 0, 70)  # полупрозрачная тень под зданиями


def new_surface(tiles_w: int, tiles_h: int) -> pygame.Surface:
    """Прозрачная картинка размером в tiles_w × tiles_h клеток."""
    return pygame.Surface((tiles_w * T, tiles_h * T), pygame.SRCALPHA)


def shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Светлее (factor > 1) или темнее (factor < 1)."""
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def add_noise(surface: pygame.Surface, rect: pygame.Rect, color, amount: int, seed: int) -> None:
    """Случайные точки чуть светлее/темнее — имитация текстуры (асфальт, земля)."""
    rng = random.Random(seed)  # фиксированный seed — картинка каждый раз одинаковая
    for _ in range(amount):
        x = rng.randrange(rect.left, rect.right)
        y = rng.randrange(rect.top, rect.bottom)
        surface.set_at((x, y), shade(color, rng.choice((0.85, 0.9, 1.1, 1.15))))


# --- Рисунки зданий ---

def draw_house(roof: tuple[int, int, int]) -> pygame.Surface:
    """Дом 1×1: двускатная крыша (две половины разного оттенка) и труба."""
    s = new_surface(1, 1)
    pygame.draw.rect(s, SHADOW, (12, 14, 46, 44), border_radius=3)        # тень
    pygame.draw.rect(s, roof, (8, 10, 24, 44))                            # левый скат
    pygame.draw.rect(s, shade(roof, 0.75), (32, 10, 24, 44))              # правый скат, в тени
    pygame.draw.line(s, shade(roof, 1.25), (32, 10), (32, 53), 2)         # конёк крыши
    pygame.draw.rect(s, shade(roof, 0.5), (8, 10, 48, 44), 2)             # контур
    pygame.draw.rect(s, (150, 70, 50), (40, 16, 8, 8))                    # труба
    pygame.draw.rect(s, (90, 40, 30), (40, 16, 8, 8), 1)
    return s


def draw_apartment(roof: tuple[int, int, int], helipad: bool = False) -> pygame.Surface:
    """Многоэтажка 2×2: плоская крыша с бортиком и техническими блоками."""
    s = new_surface(2, 2)
    pygame.draw.rect(s, SHADOW, (16, 16, 106, 106), border_radius=4)
    body = pygame.Rect(10, 10, 108, 108)
    pygame.draw.rect(s, roof, body)
    pygame.draw.rect(s, shade(roof, 0.65), body, 5)                       # бортик
    if helipad:
        center = body.center
        pygame.draw.circle(s, shade(roof, 0.8), center, 30)
        pygame.draw.circle(s, (240, 240, 240), center, 30, 3)
        # Буква H
        cx, cy = center
        for dx in (-9, 9):
            pygame.draw.line(s, (240, 240, 240), (cx + dx, cy - 12), (cx + dx, cy + 12), 4)
        pygame.draw.line(s, (240, 240, 240), (cx - 9, cy), (cx + 9, cy), 4)
    else:
        # Вентиляционные блоки и выход на крышу
        for x, y in ((26, 26), (26, 50), (80, 80)):
            pygame.draw.rect(s, shade(roof, 1.2), (x, y, 18, 14))
            pygame.draw.rect(s, shade(roof, 0.6), (x, y, 18, 14), 1)
        pygame.draw.rect(s, shade(roof, 0.8), (70, 24, 30, 24))
        for x, y in ((90, 60), (40, 92)):
            pygame.draw.circle(s, shade(roof, 0.55), (x, y), 6)
    return s


def draw_road(color: tuple[int, int, int], seed: int) -> pygame.Surface:
    """Дорога 1×1: заливка во всю клетку + текстура. Без разметки —
    иначе на поворотах и перекрёстках она будет обрываться."""
    s = new_surface(1, 1)
    rect = s.get_rect()
    s.fill(color)
    add_noise(s, rect, color, 260, seed)
    return s


def draw_park() -> pygame.Surface:
    """Парк 1×1: газон, дорожка и деревья."""
    s = new_surface(1, 1)
    pygame.draw.rect(s, (110, 180, 90), (3, 3, 58, 58), border_radius=6)
    pygame.draw.line(s, (220, 200, 150), (3, 50), (61, 14), 6)             # дорожка
    for x, y, r in ((18, 18, 10), (44, 44, 11), (48, 16, 7), (16, 46, 7)):
        pygame.draw.circle(s, SHADOW, (x + 3, y + 3), r)                  # тень дерева
        pygame.draw.circle(s, (40, 110, 50), (x, y), r)                   # крона
        pygame.draw.circle(s, (70, 150, 70), (x - r // 3, y - r // 3), r // 2)  # блик
    return s


def draw_shop() -> pygame.Surface:
    """Магазин 1×1: плоская крыша и полосатый навес над входом."""
    s = new_surface(1, 1)
    pygame.draw.rect(s, SHADOW, (10, 10, 50, 50), border_radius=3)
    pygame.draw.rect(s, (170, 180, 200), (6, 6, 52, 40))
    pygame.draw.rect(s, (110, 120, 140), (6, 6, 52, 40), 3)
    for i in range(6):                                                    # навес
        color = (220, 60, 60) if i % 2 == 0 else (245, 245, 245)
        pygame.draw.rect(s, color, (6 + i * 52 // 6, 46, 52 // 6 + 1, 12))
    return s


def draw_factory() -> pygame.Surface:
    """Завод 2×2: «пилообразная» крыша цеха и дымовая труба."""
    s = new_surface(2, 2)
    pygame.draw.rect(s, SHADOW, (14, 26, 108, 96), border_radius=3)
    body = pygame.Rect(8, 20, 108, 96)
    stripe_w = 12
    for i, x in enumerate(range(body.left, body.right, stripe_w)):
        color = (150, 130, 120) if i % 2 == 0 else (110, 95, 90)
        pygame.draw.rect(s, color, (x, body.top, stripe_w, body.height))
    pygame.draw.rect(s, (70, 60, 55), body, 3)
    pygame.draw.circle(s, SHADOW, (104, 24), 14)
    pygame.draw.circle(s, (90, 85, 85), (100, 20), 13)                    # труба
    pygame.draw.circle(s, (40, 40, 40), (100, 20), 8)                     # отверстие
    return s


def draw_farm() -> pygame.Surface:
    """Ферма 2×2: грядки разных культур и красный амбар."""
    s = new_surface(2, 2)
    colors = [(200, 180, 80), (120, 170, 70), (200, 180, 80), (150, 190, 90)]
    for i, color in enumerate(colors):
        rect = pygame.Rect(6, 6 + i * 29, 116, 27)
        pygame.draw.rect(s, color, rect, border_radius=3)
        for x in range(rect.left + 4, rect.right, 8):                     # борозды
            pygame.draw.line(s, shade(color, 0.8), (x, rect.top + 3), (x, rect.bottom - 3), 1)
    pygame.draw.rect(s, SHADOW, (84, 82, 38, 40))
    pygame.draw.rect(s, (180, 50, 40), (80, 78, 38, 38))                  # амбар
    pygame.draw.line(s, (120, 30, 25), (80, 97), (117, 97), 3)
    pygame.draw.rect(s, (110, 30, 25), (80, 78, 38, 38), 2)
    return s


def draw_category_residential() -> pygame.Surface:
    """Картинка категории «Жилые здания» — три домика в ряд (широкая, для карточки)."""
    s = pygame.Surface((176, 80), pygame.SRCALPHA)
    for i, roof in enumerate([(200, 110, 80), (200, 160, 90), (170, 90, 70)]):
        house = pygame.transform.smoothscale(draw_house(roof), (56, 56))
        s.blit(house, (4 + i * 58, 12))
    return s


# Что рисовать: имя файла -> функция. Имя файла = id товара из data/shop.json
DRAWINGS = {
    BUILDINGS_DIR / "house_small.png": lambda: draw_house((200, 160, 90)),
    BUILDINGS_DIR / "cottage.png": lambda: draw_house((180, 90, 70)),
    BUILDINGS_DIR / "apartment.png": lambda: draw_apartment((150, 150, 165)),
    BUILDINGS_DIR / "skyscraper.png": lambda: draw_apartment((110, 140, 175), helipad=True),
    BUILDINGS_DIR / "road_asphalt.png": lambda: draw_road((75, 75, 80), seed=1),
    BUILDINGS_DIR / "road_dirt.png": lambda: draw_road((150, 120, 80), seed=2),
    BUILDINGS_DIR / "park.png": draw_park,
    BUILDINGS_DIR / "shop.png": draw_shop,
    BUILDINGS_DIR / "factory.png": draw_factory,
    BUILDINGS_DIR / "farm.png": draw_farm,
    CATEGORIES_DIR / "residential.png": draw_category_residential,
}


def main() -> int:
    pygame.init()  # окно не нужно: рисуем на поверхностях в памяти и сохраняем в файлы
    BUILDINGS_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIES_DIR.mkdir(parents=True, exist_ok=True)
    for path, draw in DRAWINGS.items():
        pygame.image.save(draw(), str(path))
        print(f"  {path.relative_to(PROJECT_DIR)}")
    print(f"Готово: {len(DRAWINGS)} картинок")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
