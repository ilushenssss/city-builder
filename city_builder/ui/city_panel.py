"""Панель «Город» под панелью цели: энергия, вода, счастье и склад.

    ┌──────────────────────────────────┐
    │ Энергия        180 / 300         │  <- потребляют / вырабатывают (жёлтым)
    │ Вода            40 / 80   −20    │  <- (синим); не хватает — красным, с размером нехватки
    │ Счастье        65%   пробки −4   │
    │ Дороги         72%   опаздывают 8% │  <- загруженность дорог
    │ Еда             30 / 100   +6    │  <- на складе / вместимость, изменение за тик
    │ Древесина       10 / 100   +2    │
    │ Товары          25 / 100   −1    │
    │ Голод: жители уезжают!           │  <- только при проблемах (красным)
    └──────────────────────────────────┘
"""

import pygame

from city_builder.config import (
    COLOR_MENU_PANEL,
    COLOR_MONEY_NEGATIVE,
    COLOR_MONEY_POSITIVE,
    COLOR_POWER,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_WARNING,
    COLOR_UI_BORDER,
    COLOR_WATER,
    GOAL_PANEL_WIDTH,
    RESOURCE_NAMES,
    UI_BORDER_RADIUS,
    UNHAPPY_LEVEL,
)
from city_builder.economy.economy import Economy

PADDING = 12
VALUE_X = 100   # где начинаются числа (от левого края панели)
DELTA_X = 182   # где изменение за тик и пояснения

Color = tuple[int, int, int]
Row = tuple[str, str, Color, str, Color]  # (название, значение, его цвет, изменение, его цвет)


class CityPanel:
    def __init__(self, economy: Economy) -> None:
        self.economy = economy
        self.rect = pygame.Rect(0, 0, GOAL_PANEL_WIDTH, 0)
        self.font = pygame.font.SysFont("consolas", 14, bold=True)
        self._rows: list[Row] = []
        self._warnings: list[str] = []

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def _build_rows(self) -> None:
        eco = self.economy
        power, water = eco.infrastructure.totals()
        rows: list[Row] = []

        # Энергия и вода: сколько потребляют / сколько вырабатывается.
        # Если кому-то не хватило (спрос больше выдачи) — число красное.
        for name, used, demand, supply, color in (
            ("Энергия", power.used, power.demand, power.supply, COLOR_POWER),
            ("Вода", water.used, water.demand, water.supply, COLOR_WATER),
        ):
            short = demand - used
            value_color = COLOR_MONEY_NEGATIVE if short > 0 else color
            note = f"−{short}" if short > 0 else ""  # нехватка
            rows.append((name, f"{used} / {supply}", value_color, note, COLOR_MONEY_NEGATIVE))

        happiness = round(eco.happiness)
        h_color = COLOR_MONEY_NEGATIVE if happiness < UNHAPPY_LEVEL else (
            COLOR_MONEY_POSITIVE if happiness >= 60 else COLOR_TEXT)
        penalty = round(eco.traffic_penalty)
        rows.append(("Счастье", f"{happiness}%", h_color,
                     f"пробки −{penalty}" if penalty else "", COLOR_MONEY_NEGATIVE))
        # Пробки: средняя загруженность дорог и сколько работников опаздывает
        load = eco.traffic.average_ratio
        load_color = COLOR_MONEY_POSITIVE if load < 0.7 else (COLOR_WARNING if load < 1 else COLOR_MONEY_NEGATIVE)
        late = round((1 - eco.traffic.commute_factor) * 100)
        rows.append(("Дороги", f"{round(load * 100)}%", load_color,
                     f"опаздывают {late}%" if late else "", COLOR_MONEY_NEGATIVE))

        # Склад: сколько есть / вместимость и изменение за последний тик
        report = eco.last_report
        for resource, name in RESOURCE_NAMES.items():
            amount = eco.stock[resource]
            delta = report.produced.get(resource, 0) - report.consumed.get(resource, 0)
            delta_text = f"{delta:+.0f}" if abs(delta) >= 0.5 else ""
            delta_color = COLOR_MONEY_POSITIVE if delta >= 0 else COLOR_MONEY_NEGATIVE
            rows.append((name, f"{amount:.0f} / {eco.stats.storage}", COLOR_TEXT, delta_text, delta_color))
        self._rows = rows

        self._warnings = []
        if report.hungry:
            self._warnings.append("Голод: жители уезжают! Нужна ферма")
        if report.unhappy:
            self._warnings.append("Жители несчастны и уезжают")

    def update(self, top_left: tuple[int, int]) -> None:
        self._build_rows()
        line_h = self.font.get_linesize()
        height = 2 * PADDING + (len(self._rows) + len(self._warnings)) * line_h + 4
        self.rect = pygame.Rect(top_left, (GOAL_PANEL_WIDTH, height))

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, COLOR_MENU_PANEL, self.rect, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)
        x = self.rect.left + PADDING
        y = self.rect.top + PADDING
        line_h = self.font.get_linesize()
        for i, (name, value, value_color, delta, delta_color) in enumerate(self._rows):
            if i == 4:
                # Линия-разделитель между «инфраструктурой» и «складом»
                pygame.draw.line(screen, COLOR_UI_BORDER, (x, y + 1), (self.rect.right - PADDING, y + 1))
                y += 4
            screen.blit(self.font.render(name, True, COLOR_TEXT_DIM), (x, y))
            screen.blit(self.font.render(value, True, value_color), (self.rect.left + VALUE_X, y))
            if delta:
                screen.blit(self.font.render(delta, True, delta_color), (self.rect.left + DELTA_X, y))
            y += line_h
        for warning in self._warnings:
            screen.blit(self.font.render(warning, True, COLOR_MONEY_NEGATIVE), (x, y))
            y += line_h
