"""Баннер «Новый уровень!» вверху по центру: что открылось в магазине.

    ┌─────────────────────────────────────────────┐
    │           ★  Уровень 3!  ★                 │
    │  Открыто: Многоэтажка, Офис, Завод, Школа…  │
    └─────────────────────────────────────────────┘

Появляется, когда GoalTracker сообщает о новом уровне (pending_level_up),
висит несколько секунд и плавно исчезает.
"""

from __future__ import annotations

import pygame

from city_builder.config import (
    COLOR_MENU_PANEL,
    COLOR_PRICE,
    COLOR_TEXT,
    UI_BORDER_RADIUS,
)
from city_builder.data.catalog import Catalog
from city_builder.economy.goals import GoalTracker

SHOW_TIME = 6.0   # секунд на экране
FADE_TIME = 1.0   # последние столько секунд — плавно исчезает
TOP = 70          # отступ сверху


class LevelBanner:
    def __init__(self, screen_size: tuple[int, int], goals: GoalTracker, catalog: Catalog) -> None:
        self.screen_w = screen_size[0]
        self.goals = goals
        self.catalog = catalog
        self.title_font = pygame.font.SysFont("consolas", 28, bold=True)
        self.font = pygame.font.SysFont("consolas", 16)
        self.surface: pygame.Surface | None = None
        self.age = 0.0

    def update(self, dt: float) -> None:
        if self.goals.pending_level_up is not None:
            self._show(self.goals.pending_level_up)
            self.goals.pending_level_up = None  # «забрали» новость
        if self.surface is not None:
            self.age += dt
            if self.age >= SHOW_TIME:
                self.surface = None

    def _show(self, level: int) -> None:
        names = [item.name for item in self.catalog.items if item.level == level]
        title = self.title_font.render(f"Новый уровень: {level}!", True, COLOR_PRICE)
        text = "Открыто: " + ", ".join(names) if names else "Город растёт!"
        line = self.font.render(text, True, COLOR_TEXT)
        width = max(title.get_width(), line.get_width()) + 48
        height = title.get_height() + line.get_height() + 30
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(surface, COLOR_MENU_PANEL, surface.get_rect(), border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(surface, COLOR_PRICE, surface.get_rect(), 2, border_radius=UI_BORDER_RADIUS)
        surface.blit(title, title.get_rect(midtop=(width // 2, 10)))
        surface.blit(line, line.get_rect(midtop=(width // 2, 16 + title.get_height())))
        self.surface = surface
        self.age = 0.0

    def draw(self, screen: pygame.Surface) -> None:
        if self.surface is None:
            return
        alpha = 255 if self.age < SHOW_TIME - FADE_TIME else int(255 * (SHOW_TIME - self.age) / FADE_TIME)
        self.surface.set_alpha(alpha)
        screen.blit(self.surface, self.surface.get_rect(midtop=(self.screen_w // 2, TOP)))

