"""Экран конца игры: победа или банкротство.

Победа:                               Поражение:
    ┌──────────────────────────────┐      ┌──────────────────────────────┐
    │           Победа!            │      │         Банкротство          │
    │ Город вырос до 500 жителей   │      │ Деньги были в минусе 30 дней │
    │                              │      │                              │
    │ Дней прошло:          124    │      │ Дней прошло:           87    │
    │ Жителей:              512    │      │ ...                          │
    │ ...                          │      │                              │
    │ [Продолжить] [Новая] [Выход] │      │      [Новая игра] [Выход]    │
    └──────────────────────────────┘      └──────────────────────────────┘

Пока экран показан, он «съедает» все события: карта, меню и строительство
недоступны. Enter нажимает первую кнопку.

Сам экран ничего не решает: он ставит флаги (new_game_requested,
quit_requested) или вызывает goals.continue_playing(), а Game их обрабатывает.
"""

import pygame

from city_builder.config import (
    BANKRUPTCY_TICKS,
    COLOR_DEFEAT,
    COLOR_END_OVERLAY,
    COLOR_MENU_PANEL,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_UI_BORDER,
    COLOR_UI_CONFIRM_HOVER,
    COLOR_UI_DANGER_HOVER,
    COLOR_VICTORY,
    END_SCREEN_WIDTH,
    TEXT_BUTTON_HEIGHT,
    TEXT_BUTTON_WIDTH,
    UI_BORDER_RADIUS,
    UI_BUTTON_GAP,
)
from city_builder.economy.economy import Economy
from city_builder.economy.goals import GoalTracker, Outcome
from city_builder.ui.button import Button
from city_builder.ui.resource_bar import format_number

LEFT_BUTTON = 1
PADDING = 24


class EndScreen:
    def __init__(self, screen_size: tuple[int, int], goals: GoalTracker, economy: Economy) -> None:
        self.goals = goals
        self.economy = economy
        self.screen_size = screen_size
        self.new_game_requested = False
        self.quit_requested = False

        self.overlay = pygame.Surface(screen_size, pygame.SRCALPHA)
        self.overlay.fill(COLOR_END_OVERLAY)
        self.title_font = pygame.font.SysFont("consolas", 36, bold=True)
        self.text_font = pygame.font.SysFont("consolas", 17)
        self.stat_font = pygame.font.SysFont("consolas", 17, bold=True)

        size = (TEXT_BUTTON_WIDTH, TEXT_BUTTON_HEIGHT)
        self.continue_button = Button(pygame.Rect((0, 0), size), text="Продолжить",
                                      hover_color=COLOR_UI_CONFIRM_HOVER)
        self.new_game_button = Button(pygame.Rect((0, 0), size), text="Новая игра",
                                      hover_color=COLOR_UI_CONFIRM_HOVER)
        self.quit_button = Button(pygame.Rect((0, 0), size), text="Выход",
                                  hover_color=COLOR_UI_DANGER_HOVER)
        self.panel = pygame.Rect(0, 0, END_SCREEN_WIDTH, 0)  # высота — в update()

    @property
    def visible(self) -> bool:
        return self.goals.finished

    @property
    def won(self) -> bool:
        return self.goals.outcome == Outcome.WON

    @property
    def buttons(self) -> list[Button]:
        """Кнопки в порядке слева направо. «Продолжить» — только после победы."""
        if self.won:
            return [self.continue_button, self.new_game_button, self.quit_button]
        return [self.new_game_button, self.quit_button]

    # --- Содержимое ---

    def _texts(self) -> tuple[str, tuple[int, int, int], str]:
        """(заголовок, его цвет, пояснение)."""
        if self.won:
            return "Победа!", COLOR_VICTORY, f"Город вырос до {self.goals.target} жителей"
        return "Банкротство", COLOR_DEFEAT, f"Деньги были в минусе {BANKRUPTCY_TICKS} дней подряд"

    def _stats(self) -> list[tuple[str, str]]:
        """Итоги игры: (название, значение)."""
        eco = self.economy
        buildings = len(eco.grid.buildings)
        return [
            ("Дней прошло", format_number(eco.day)),
            ("Жителей", format_number(eco.population)),
            ("Рабочих мест", format_number(eco.stats.jobs)),
            ("Зданий построено", format_number(buildings)),
            ("Деньги", format_number(eco.money)),
        ]

    # --- Ввод ---

    def _press(self, button: Button) -> None:
        """Что делает каждая кнопка."""
        if button is self.continue_button:
            self.goals.continue_playing()
        elif button is self.new_game_button:
            self.new_game_requested = True
        elif button is self.quit_button:
            self.quit_requested = True

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == LEFT_BUTTON:
            for button in self.buttons:
                if button.contains(event.pos):
                    self._press(button)
                    break
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._press(self.buttons[0])  # Enter — первая кнопка
        # Закрытие окна (крестик) пропускаем дальше, всё остальное «съедаем»
        return event.type != pygame.QUIT

    # --- Раскладка и отрисовка ---

    def update(self, mouse_pos: tuple[int, int]) -> None:
        if not self.visible:
            return
        line_h = self.stat_font.get_linesize()
        height = (PADDING + self.title_font.get_linesize() + 8 + self.text_font.get_linesize()
                  + 20 + len(self._stats()) * (line_h + 4) + 20 + TEXT_BUTTON_HEIGHT + PADDING)
        self.panel = pygame.Rect(0, 0, END_SCREEN_WIDTH, height)
        self.panel.center = (self.screen_size[0] // 2, self.screen_size[1] // 2)

        # Кнопки внизу по центру
        buttons = self.buttons
        total_w = len(buttons) * TEXT_BUTTON_WIDTH + (len(buttons) - 1) * UI_BUTTON_GAP
        x = self.panel.centerx - total_w // 2
        for button in buttons:
            button.rect.topleft = (x, self.panel.bottom - PADDING - TEXT_BUTTON_HEIGHT)
            x += TEXT_BUTTON_WIDTH + UI_BUTTON_GAP
            button.update(mouse_pos)

    def draw(self, screen: pygame.Surface) -> None:
        if not self.visible:
            return
        screen.blit(self.overlay, (0, 0))
        pygame.draw.rect(screen, COLOR_MENU_PANEL, self.panel, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.panel, 1, border_radius=UI_BORDER_RADIUS)

        title, title_color, subtitle = self._texts()
        y = self.panel.top + PADDING
        surface = self.title_font.render(title, True, title_color)
        screen.blit(surface, surface.get_rect(midtop=(self.panel.centerx, y)))
        y += self.title_font.get_linesize() + 8
        surface = self.text_font.render(subtitle, True, COLOR_TEXT_DIM)
        screen.blit(surface, surface.get_rect(midtop=(self.panel.centerx, y)))
        y += self.text_font.get_linesize() + 20

        # Итоги: название слева, значение справа
        left = self.panel.left + PADDING * 2
        right = self.panel.right - PADDING * 2
        for name, value in self._stats():
            name_surface = self.text_font.render(name, True, COLOR_TEXT_DIM)
            value_surface = self.stat_font.render(value, True, COLOR_TEXT)
            screen.blit(name_surface, (left, y))
            screen.blit(value_surface, value_surface.get_rect(topright=(right, y)))
            y += self.stat_font.get_linesize() + 4

        for button in self.buttons:
            button.draw(screen)
