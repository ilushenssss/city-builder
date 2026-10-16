"""Маленькие значки для панелей (монета, жители, работа, предупреждение, солнце...).

Рисуются кодом (кругами и многоугольниками) с увеличением и сглаживанием,
как текстуры зданий, — поэтому чёткие и без картинок-файлов.
Каждый значок рисуется один раз и запоминается (icon() с кэшем).
"""

from __future__ import annotations

import pygame

SUPERSAMPLE = 4  # рисуем в 4 раза крупнее и плавно уменьшаем — края гладкие
_cache: dict[tuple[str, int], pygame.Surface] = {}


def icon(name: str, size: int = 20) -> pygame.Surface:
    """Значок name размером size×size пикселей."""
    key = (name, size)
    if key not in _cache:
        big = size * SUPERSAMPLE
        surface = pygame.Surface((big, big), pygame.SRCALPHA)
        DRAWERS[name](surface, big)
        _cache[key] = pygame.transform.smoothscale(surface, (size, size))
    return _cache[key]


def _coin(s: pygame.Surface, n: int) -> None:
    """Монета: золотой круг с ободком и бликом."""
    c = n // 2
    pygame.draw.circle(s, (180, 120, 20), (c, c + n // 16), n // 2 - n // 16)
    pygame.draw.circle(s, (250, 200, 60), (c, c), n // 2 - n // 10)
    pygame.draw.circle(s, (215, 160, 35), (c, c), n // 2 - n // 4, n // 14)
    pygame.draw.circle(s, (255, 240, 170), (c - n // 7, c - n // 7), n // 10)


def _people(s: pygame.Surface, n: int) -> None:
    """Жители: два человечка — голова и плечи."""
    for dx, color in ((-n // 6, (120, 170, 230)), (n // 6, (90, 200, 140))):
        cx = n // 2 + dx
        pygame.draw.circle(s, (240, 205, 165), (cx, n * 5 // 16), n * 3 // 16)
        pygame.draw.ellipse(s, color, (cx - n // 4, n * 9 // 16, n // 2, n * 7 // 16))


def _briefcase(s: pygame.Surface, n: int) -> None:
    """Работа: портфель с ручкой."""
    pygame.draw.rect(s, (150, 95, 55), (n // 8, n * 5 // 16, n * 3 // 4, n * 9 // 16), border_radius=n // 10)
    pygame.draw.rect(s, (120, 75, 45), (n * 3 // 8, n * 3 // 16, n // 4, n // 6), n // 16, border_radius=n // 20)
    pygame.draw.line(s, (100, 60, 35), (n // 8, n * 9 // 16), (n * 7 // 8, n * 9 // 16), n // 16)
    pygame.draw.rect(s, (230, 190, 90), (n * 7 // 16, n * 1 // 2, n // 8, n // 8))


def _warning(s: pygame.Surface, n: int) -> None:
    """Предупреждение: жёлтый треугольник с «!»."""
    pygame.draw.polygon(s, (240, 180, 40), [(n // 2, n // 10), (n * 15 // 16, n * 7 // 8), (n // 16, n * 7 // 8)])
    pygame.draw.line(s, (60, 40, 10), (n // 2, n * 3 // 8), (n // 2, n * 5 // 8), n // 10)
    pygame.draw.circle(s, (60, 40, 10), (n // 2, n * 3 // 4), n // 16)


def _sun(s: pygame.Surface, n: int) -> None:
    """День: солнце с лучами."""
    import math
    c = n // 2
    for i in range(8):
        a = i * math.pi / 4
        pygame.draw.line(s, (250, 190, 50), (c + math.cos(a) * n * 0.28, c + math.sin(a) * n * 0.28),
                         (c + math.cos(a) * n * 0.46, c + math.sin(a) * n * 0.46), n // 12)
    pygame.draw.circle(s, (255, 210, 70), (c, c), n * 5 // 18)
    pygame.draw.circle(s, (255, 240, 160), (c - n // 12, c - n // 12), n // 10)


DRAWERS = {
    "coin": _coin,
    "people": _people,
    "work": _briefcase,
    "warning": _warning,
    "sun": _sun,
}
