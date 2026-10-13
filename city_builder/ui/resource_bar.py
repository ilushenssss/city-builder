"""Панель ресурсов вверху слева: деньги, жители, работа, день и скорость времени.

    ┌────────────────────────────────────────────────────────────────────────────┐
    │ Деньги: 1 250 (+35) │ Жители: 120 / 150 │ Работа: 80 / 100 │ День 12 [⏸][1×][2×][3×] │
    └────────────────────────────────────────────────────────────────────────────┘
                                                              ▔▔▔▔ полоска до следующего тика

  * (+35) — насколько изменились деньги за последний тик (зелёным — плюс, красным — минус).
    Наведите курсор на деньги — появится подсказка, из чего складывается эта сумма.
  * «Проблемы: 3» — здания без дороги, света, воды или сырья (значки над ними).
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
from city_builder.ui.icons import icon

LEFT_BUTTON = 1
PADDING = 12        # отступ от краёв панели
SEGMENT_GAP = 18    # расстояние между блоками (посередине — разделитель)

# Клавиша -> скорость. KP — цифры на дополнительной клавиатуре справа.
SPEED_KEYS = {
    pygame.K_1: 1, pygame.K_KP1: 1,
    pygame.K_2: 2, pygame.K_KP2: 2,
    pygame.K_3: 3, pygame.K_KP3: 3,
}

# Значок каждого блока (см. ui/icons.py) и подсказка при наведении на блок
ICONS = {"money": "coin", "people": "people", "jobs": "work", "problems": "warning", "day": "sun"}
HINTS = {
    "people": "Жители / мест в домах",
    "jobs": "Работающие / рабочих мест",
    "problems": "Зданий с проблемами — смотрите значки над ними",
    "day": "Игровой день. Пробел — пауза, 1 / 2 / 3 — скорость",
}
ICON_SIZE = 20
ICON_GAP = 6  # расстояние от значка до числа

# Кусок блока: текст одного цвета ("1 250", жёлтый) или готовая картинка (значок).
Piece = tuple[str | pygame.Surface, tuple[int, int, int]]


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
        # Где какой блок (для подсказок при наведении): [(имя блока, прямоугольник)]
        self._segment_rects: list[tuple[str, pygame.Rect]] = []
        self.hint: str | None = None  # короткая подсказка под наведённым блоком

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

    def _segments(self, compact: bool = False) -> list[tuple[str, list[Piece]]]:
        """Блоки панели слева направо: (имя блока, [значок, тексты]).
        compact=True — без изменения денег за тик, если панель не помещается на узком экране."""
        eco = self.economy
        net = eco.forecast().net
        money_color = COLOR_MONEY_NEGATIVE if eco.money < 0 else COLOR_PRICE
        net_color = COLOR_MONEY_POSITIVE if net >= 0 else COLOR_MONEY_NEGATIVE

        def head(name: str) -> Piece:
            return icon(ICONS[name], ICON_SIZE), COLOR_TEXT

        money: list[Piece] = [head("money"), (format_number(eco.money), money_color)]
        if not compact:
            money.append((f" ({format_signed(net)})", net_color))
        segments = [
            ("money", money),
            ("people", [head("people"),
                        (f"{format_number(eco.population)} / {format_number(eco.stats.housing)}", COLOR_TEXT)]),
            ("jobs", [head("jobs"),
                      (f"{format_number(eco.employed)} / {format_number(eco.stats.jobs)}", COLOR_TEXT)]),
        ]
        problems = eco.problem_count
        if problems:
            segments.append(("problems", [head("problems"), (str(problems), COLOR_WARNING)]))
        day_text = "Пауза" if self.clock.paused else f"День {eco.day}"
        segments.append(("day", [head("day"), (day_text, COLOR_WARNING if self.clock.paused else COLOR_TEXT)]))
        return segments

    def _tooltip_lines(self) -> list[Piece]:
        """Подсказка при наведении на деньги: из чего сложилась сумма за последний тик."""
        report = self.economy.forecast()

        def colored(n: int) -> tuple[int, int, int]:
            return COLOR_MONEY_POSITIVE if n >= 0 else COLOR_MONEY_NEGATIVE

        return [
            (f"Налоги ({self.economy.employed} работающих × {TAX_PER_WORKER}): "
             f"{format_signed(report.taxes)}", colored(report.taxes)),
            (f"Доход предприятий (работников {round(self.economy.staffing * 100)}%): "
             f"{format_signed(report.income)}", colored(report.income)),
            (f"Содержание зданий: {format_signed(-report.upkeep)}", colored(-report.upkeep)),
            (f"Итого за тик: {format_signed(report.net)}", colored(report.net)),
        ]

    # --- Раскладка и отрисовка ---

    def update(self, mouse_pos: tuple[int, int], max_right: int | None = None) -> None:
        """Пересчитать тексты и положение всех частей панели.
        max_right — правая граница, за которую нельзя заезжать (кнопки в углу).
        Не помещаемся — раскладываем ещё раз с короткими подписями."""
        self._layout(self._segments())
        if max_right is not None and self.rect.right > max_right:
            self._layout(self._segments(compact=True))

        # Подсветка: «нажата» кнопка текущей скорости (или паузы)
        self.pause_button.active = self.clock.paused
        for speed, button in self.speed_buttons.items():
            button.active = self.clock.speed == speed
        for button in self.buttons:
            button.update(mouse_pos)

        self.show_tooltip = self.money_rect.collidepoint(mouse_pos)
        self.hint = None
        for name, rect in self._segment_rects:
            if name in HINTS and rect.collidepoint(mouse_pos):
                self.hint = HINTS[name]

    def _layout(self, segments: list[tuple[str, list[Piece]]]) -> None:
        """Разложить тексты и кнопки слева направо и посчитать ширину панели."""
        self._texts.clear()
        self._separators.clear()
        self._segment_rects.clear()
        center_y = self.rect.centery
        x = self.rect.left + PADDING

        for index, (name, segment) in enumerate(segments):
            if index > 0:
                self._separators.append(x + SEGMENT_GAP // 2)
                x += SEGMENT_GAP
            start_x = x
            for piece, color in segment:
                if isinstance(piece, pygame.Surface):  # значок
                    surface, gap = piece, ICON_GAP
                else:
                    surface, gap = self.font.render(piece, True, color), 0
                self._texts.append((surface, (x, center_y - surface.get_height() // 2)))
                x += surface.get_width() + gap
            segment_rect = pygame.Rect(start_x, self.rect.top, x - start_x, self.rect.height)
            self._segment_rects.append((name, segment_rect))
            if name == "money":
                self.money_rect = segment_rect
            if name == "day":
                self.day_rect = segment_rect

        # Кнопки скорости — справа от текста
        x += SEGMENT_GAP // 2
        for button in self.buttons:
            button.rect.midleft = (x, center_y)
            x = button.rect.right + 4
        self.rect.width = x - 4 + PADDING - self.rect.left

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
        elif self.hint:
            self._draw_hint(screen)

    def _draw_hint(self, screen: pygame.Surface) -> None:
        """Короткая подсказка под наведённым блоком («Жители / мест в домах»)."""
        text = self.tooltip_font.render(self.hint or "", True, COLOR_TEXT)
        mouse_x = pygame.mouse.get_pos()[0]
        box = pygame.Rect(0, 0, text.get_width() + 2 * PADDING, text.get_height() + 12)
        box.topleft = (max(self.rect.left, mouse_x - box.width // 2), self.rect.bottom + 6)
        pygame.draw.rect(screen, COLOR_MENU_PANEL, box, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, box, 1, border_radius=UI_BORDER_RADIUS)
        screen.blit(text, (box.left + PADDING, box.top + 6))

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
