"""Панель цели под панелью ресурсов: уровень города, прогресс к победе, долг.

    ┌────────────────────────────────────┐
    │ Уровень 2 · до 3-го: 120 / 150     │  <- уровень и сколько жителей до следующего
    │ ████████████░░░░░░░░░░░░░░░░░░░░░  │
    │ Цель: 500 жителей           24%    │
    │ ████████░░░░░░░░░░░░░░░░░░░░░░░░░  │  <- полоска прогресса
    │ Долг! Банкротство через 12 дн.     │  <- только если деньги в минусе (красным)
    └────────────────────────────────────┘

После победы и «Продолжить» панель показывает «Свободная игра».
"""

from __future__ import annotations

import pygame

from city_builder.config import (
    COLOR_MENU_PANEL,
    COLOR_MONEY_NEGATIVE,
    COLOR_PROGRESS,
    COLOR_PRICE,
    COLOR_PROGRESS_BG,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_UI_BORDER,
    COLOR_VICTORY,
    GOAL_PANEL_WIDTH,
    LEVEL_POPULATION,
    UI_BORDER_RADIUS,
)
from city_builder.economy.goals import GoalTracker, Outcome

PADDING = 12
BAR_HEIGHT = 8


class GoalPanel:
    def __init__(self, goals: GoalTracker) -> None:
        self.goals = goals
        self.rect = pygame.Rect(0, 0, GOAL_PANEL_WIDTH, 0)  # положение и высота — в update()
        self.font = pygame.font.SysFont("consolas", 15, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 14, bold=True)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def update(self, top_left: tuple[int, int]) -> None:
        """Панель стоит под панелью ресурсов — UIManager передаёт, где именно.
        Высота зависит от того, показывается ли строка про долг."""
        line_h = self.font.get_linesize()
        height = PADDING + 2 * (line_h + 6 + BAR_HEIGHT) + 6 + PADDING
        if self._debt_text():
            height += self.small_font.get_linesize() + 4
        self.rect = pygame.Rect(top_left, (GOAL_PANEL_WIDTH, height))

    def _debt_text(self) -> str | None:
        """Предупреждение о банкротстве или None, если долга нет (или цель уже не проверяется)."""
        if not self.goals.active or not self.goals.in_debt:
            return None
        return f"Долг! Банкротство через {self.goals.ticks_until_bankruptcy} дн."

    @staticmethod
    def _bar(screen: pygame.Surface, x: int, y: int, width: int, progress: float, color) -> None:
        """Полоска прогресса: серый фон и заполненная часть цвета color."""
        pygame.draw.rect(screen, COLOR_PROGRESS_BG, (x, y, width, BAR_HEIGHT), border_radius=BAR_HEIGHT // 2)
        filled = round(width * progress)
        if filled > 0:
            pygame.draw.rect(screen, color, (x, y, filled, BAR_HEIGHT), border_radius=BAR_HEIGHT // 2)

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, COLOR_MENU_PANEL, self.rect, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)
        x = self.rect.left + PADDING
        y = self.rect.top + PADDING
        inner_w = self.rect.width - 2 * PADDING

        # --- Уровень города и прогресс до следующего ---
        goals = self.goals
        need = goals.next_level_population
        if need is None:
            level_text = f"Уровень {goals.level} — максимальный"
            level_progress = 1.0
        else:
            prev = LEVEL_POPULATION[goals.level - 1]
            level_text = f"Уровень {goals.level} · до {goals.level + 1}-го: {goals.best_population} / {need}"
            level_progress = max(0.0, min(1.0, (goals.best_population - prev) / (need - prev)))
        screen.blit(self.font.render(level_text, True, COLOR_PRICE), (x, y))
        y += self.font.get_linesize() + 6
        self._bar(screen, x, y, inner_w, level_progress, COLOR_PRICE)
        y += BAR_HEIGHT + 10

        # --- Строка 1: что за цель и процент ---
        if self.goals.outcome == Outcome.WON:
            text = "Цель выполнена — свободная игра" if self.goals.continued else "Цель выполнена!"
            title = self.font.render(text, True, COLOR_VICTORY)
            screen.blit(title, (x, y))
        else:
            title = self.font.render(f"Цель: {self.goals.target} жителей", True, COLOR_TEXT)
            percent = self.font.render(f"{round(self.goals.progress * 100)}%", True, COLOR_TEXT_DIM)
            screen.blit(title, (x, y))
            screen.blit(percent, percent.get_rect(topright=(self.rect.right - PADDING, y)))
        y += self.font.get_linesize() + 6

        # --- Строка 2: полоска прогресса ---
        self._bar(screen, x, y, inner_w, self.goals.progress, COLOR_PROGRESS)
        y += BAR_HEIGHT + 4

        # --- Строка 3: долг (мигает: полсекунды виден, полсекунды тусклее) ---
        debt = self._debt_text()
        if debt:
            bright = (pygame.time.get_ticks() // 500) % 2 == 0  # get_ticks — миллисекунды с запуска
            color = COLOR_MONEY_NEGATIVE if bright else COLOR_TEXT_DIM
            screen.blit(self.small_font.render(debt, True, color), (x, y))
