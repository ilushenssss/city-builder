"""Панель ресурсов вверху слева: деньги, жители, работа, день и скорость времени.

    ┌────────────────────────────────────────────────────────────────────────────┐
    │ Деньги: 1 250 (+35) │ Жители: 120 / 150 │ Работа: 80 / 100 │ День 12 [⏸][1×][2×][3×] │
    └────────────────────────────────────────────────────────────────────────────┘
                                                              ▔▔▔▔ полоска до следующего тика

  * (+35) — сколько денег прибавится за следующий тик (зелёным) или убавится (красным).
    Наведите курсор на деньги — появится подсказка, из чего складывается эта сумма.
  * «Без дороги: 3» — появляется, если есть неработающие здания.
  * Скорость: кнопки или клавиши Пробел (пауза), 1, 2, 3.

Ширина панели зависит от текста, поэтому раскладка (где что стоит)
пересчитывается каждый кадр в update().
"""

import pygame

from city_builder.config import (
    COLOR_MENU_PANEL,
    COLOR_MONEY_NEGATIVE,
    COLOR_MONEY_POSITIVE,
    COLOR_PRICE,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_UI_BORDER,
    COLOR_WARNING,
    GAME_SPEEDS,
    RESOURCE_BAR_HEIGHT,
    SPEED_BUTTON_HEIGHT,
    SPEED_BUTTON_WIDTH,
    TAX_PER_WORKER,
    UI_BORDER_RADIUS,
    UI_MARGIN,
)
from city_builder.economy.clock import GameClock
from city_builder.economy.economy import Economy
from city_builder.ui.button import ICON_PAUSE, Button

LEFT_BUTTON = 1
PADDING = 12        # отступ от краёв панели
SEGMENT_GAP = 18    # расстояние между блоками (посередине — разделитель)

# Клавиша -> скорость. KP — цифры на дополнительной клавиатуре справа.
SPEED_KEYS = {
    pygame.K_1: 1, pygame.K_KP1: 1,
    pygame.K_2: 2, pygame.K_KP2: 2,
    pygame.K_3: 3, pygame.K_KP3: 3,
}

# Кусок текста одного цвета: ("Деньги: ", серый). Блок панели — несколько таких кусков.
Piece = tuple[str, tuple[int, int, int]]


def format_number(n: int) -> str:
    """1250 -> «1 250»: пробел между тысячами, так легче читать."""
    return f"{n:,}".replace(",", " ")


def format_signed(n: int) -> str:
    """35 -> «+35», -12 -> «−12»."""
    return f"+{format_number(n)}" if n >= 0 else f"−{format_number(-n)}"


class ResourceBar:
    def __init__(self, economy: Economy, clock: GameClock) -> None:
        self.economy = economy
        self.clock = clock

        self.rect = pygame.Rect(UI_MARGIN, UI_MARGIN, 0, RESOURCE_BAR_HEIGHT)  # ширина — в update()
        self.font = pygame.font.SysFont("consolas", 16, bold=True)
        self.tooltip_font = pygame.font.SysFont("consolas", 14)

        # Кнопки скорости. Положение задаётся в update(), здесь — только размер.
        size = (SPEED_BUTTON_WIDTH, SPEED_BUTTON_HEIGHT)
        self.pause_button = Button(pygame.Rect((0, 0), size), ICON_PAUSE)
        self.speed_buttons = {
            speed: Button(pygame.Rect((0, 0), size), text=f"{speed}×") for speed in GAME_SPEEDS
        }
        self.buttons = [self.pause_button, *self.speed_buttons.values()]

        # Результат раскладки (заполняется в update)
        self._texts: list[tuple[pygame.Surface, tuple[int, int]]] = []  # картинка текста и где её рисовать
        self._separators: list[int] = []         # x-координаты вертикальных разделителей
        self.money_rect = pygame.Rect(0, 0, 0, 0)  # область «Деньги» — для подсказки
        self.day_rect = pygame.Rect(0, 0, 0, 0)    # область «День» — под ней полоска тика
        self.show_tooltip = False

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    # --- Ввод ---

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.clock.toggle_pause()
                return True
            if event.key in SPEED_KEYS:
                self.clock.set_speed(SPEED_KEYS[event.key])
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            if event.button == LEFT_BUTTON:
                if self.pause_button.contains(event.pos):
                    self.clock.toggle_pause()
                for speed, button in self.speed_buttons.items():
                    if button.contains(event.pos):
                        self.clock.set_speed(speed)
            return True  # клик по панели не должен доходить до карты
        return False

    # --- Содержимое панели ---

    def _segments(self) -> list[list[Piece]]:
        """Тексты всех блоков панели слева направо."""
        eco = self.economy
        net = eco.forecast().net
        money_color = COLOR_MONEY_NEGATIVE if eco.money < 0 else COLOR_PRICE
        net_color = COLOR_MONEY_POSITIVE if net >= 0 else COLOR_MONEY_NEGATIVE

        segments = [
            [("Деньги: ", COLOR_TEXT_DIM), (format_number(eco.money), money_color),
             (f" ({format_signed(net)})", net_color)],
            [("Жители: ", COLOR_TEXT_DIM),
             (f"{format_number(eco.population)} / {format_number(eco.stats.housing)}", COLOR_TEXT)],
            [("Работа: ", COLOR_TEXT_DIM),
             (f"{format_number(eco.employed)} / {format_number(eco.stats.jobs)}", COLOR_TEXT)],
        ]
        if eco.stats.no_road:
            segments.append([("Без дороги: ", COLOR_TEXT_DIM), (str(eco.stats.no_road), COLOR_WARNING)])
        day_text = "Пауза" if self.clock.paused else f"День {eco.day}"
        segments.append([(day_text, COLOR_WARNING if self.clock.paused else COLOR_TEXT)])
        return segments

    def _tooltip_lines(self) -> list[Piece]:
        """Подсказка при наведении на деньги: из чего складывается сумма за тик."""
        report = self.economy.forecast()

        def colored(n: int) -> tuple[int, int, int]:
            return COLOR_MONEY_POSITIVE if n >= 0 else COLOR_MONEY_NEGATIVE

        return [
            (f"Налоги ({self.economy.employed} работающих × {TAX_PER_WORKER}): "
             f"{format_signed(report.taxes)}", colored(report.taxes)),
            (f"Доход предприятий ({round(self.economy.staffing * 100)}% работников): "
             f"{format_signed(report.income)}", colored(report.income)),
            (f"Содержание зданий: {format_signed(-report.upkeep)}", colored(-report.upkeep)),
            (f"Итого за тик: {format_signed(report.net)}", colored(report.net)),
        ]

    # --- Раскладка и отрисовка ---

    def update(self, mouse_pos: tuple[int, int]) -> None:
        """Пересчитать тексты и положение всех частей панели."""
        self._texts.clear()
        self._separators.clear()
        center_y = self.rect.centery
        x = self.rect.left + PADDING

        segments = self._segments()
        for index, segment in enumerate(segments):
            if index > 0:
                self._separators.append(x + SEGMENT_GAP // 2)
                x += SEGMENT_GAP
            start_x = x
            for text, color in segment:
                surface = self.font.render(text, True, color)
                self._texts.append((surface, (x, center_y - surface.get_height() // 2)))
                x += surface.get_width()
            segment_rect = pygame.Rect(start_x, self.rect.top, x - start_x, self.rect.height)
            if index == 0:
                self.money_rect = segment_rect
            if index == len(segments) - 1:
                self.day_rect = segment_rect

        # Кнопки скорости — справа от текста
        x += SEGMENT_GAP // 2
        for button in self.buttons:
            button.rect.midleft = (x, center_y)
            x = button.rect.right + 4
        self.rect.width = x - 4 + PADDING - self.rect.left

        # Подсветка: «нажата» кнопка текущей скорости (или паузы)
        self.pause_button.active = self.clock.paused
        for speed, button in self.speed_buttons.items():
            button.active = self.clock.speed == speed
        for button in self.buttons:
            button.update(mouse_pos)

        self.show_tooltip = self.money_rect.collidepoint(mouse_pos)

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, COLOR_MENU_PANEL, self.rect, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)

        for surface, pos in self._texts:
            screen.blit(surface, pos)
        for x in self._separators:
            pygame.draw.line(screen, COLOR_UI_BORDER, (x, self.rect.top + 10), (x, self.rect.bottom - 10))

        # Полоска под «День N»: сколько осталось до следующего тика
        if not self.clock.paused:
            bar_y = self.rect.bottom - 7
            full = self.day_rect.width
            pygame.draw.line(screen, COLOR_UI_BORDER, (self.day_rect.left, bar_y), (self.day_rect.right, bar_y), 2)
            filled = round(full * self.clock.progress)
            if filled > 0:
                pygame.draw.line(screen, COLOR_PRICE, (self.day_rect.left, bar_y),
                                 (self.day_rect.left + filled, bar_y), 2)

        for button in self.buttons:
            button.draw(screen)

        if self.show_tooltip:
            self._draw_tooltip(screen)

    def _draw_tooltip(self, screen: pygame.Surface) -> None:
        """Небольшая панель под деньгами с расшифровкой доходов и расходов."""
        lines = [self.tooltip_font.render(text, True, color) for text, color in self._tooltip_lines()]
        line_h = self.tooltip_font.get_linesize()
        width = max(line.get_width() for line in lines) + 2 * PADDING
        height = len(lines) * line_h + 2 * 10
        box = pygame.Rect(self.money_rect.left - PADDING // 2, self.rect.bottom + 6, width, height)
        pygame.draw.rect(screen, COLOR_MENU_PANEL, box, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, box, 1, border_radius=UI_BORDER_RADIUS)
        y = box.top + 10
        for i, line in enumerate(lines):
            if i == len(lines) - 1:
                # Линия перед «Итого»
                pygame.draw.line(screen, COLOR_UI_BORDER, (box.left + PADDING, y - 2), (box.right - PADDING, y - 2))
            screen.blit(line, (box.left + PADDING, y))
            y += line_h
