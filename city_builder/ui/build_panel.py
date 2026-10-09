"""Панель внизу экрана для строительства и сноса. Видна, пока один из режимов включён.

Строительство, выбор места (BuildState.PLACING):
    ┌───────────────────────────────────────────────────────────────┐
    │ Строительство: Дом   Цена: 50   Размер: 1×1                   │
    │ ЛКМ — выбрать место   ПКМ / Esc — отменить                    │  <- или ошибка красным
    └───────────────────────────────────────────────────────────────┘

Строительство, подтверждение (BuildState.CONFIRMING):
    ┌───────────────────────────────────────────────────────────────┐
    │ Построить «Дом» за 50?                 [Построить] [ Отмена ] │
    │ Enter — построить   Esc — другое место                        │
    └───────────────────────────────────────────────────────────────┘

Снос — то же самое, но кнопка называется [Снести] и подсвечивается красным.

Панель только показывает состояние BuildMode / DemolishMode и передаёт им
нажатия кнопок. Логика — в construction/build_mode.py и demolish_mode.py.
"""

import pygame

from city_builder.config import (
    BUILD_PANEL_HEIGHT,
    BUILD_PANEL_WIDTH,
    COLOR_MENU_PANEL,
    COLOR_PRICE,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_TEXT_ERROR,
    COLOR_UI_BORDER,
    COLOR_UI_CONFIRM_HOVER,
    COLOR_UI_DANGER_HOVER,
    TEXT_BUTTON_HEIGHT,
    TEXT_BUTTON_WIDTH,
    UI_BORDER_RADIUS,
    UI_BUTTON_GAP,
    UI_MARGIN,
)
from city_builder.construction.build_mode import BuildMode, BuildState
from city_builder.construction.demolish_mode import DemolishMode, DemolishState
from city_builder.ui.button import Button

LEFT_BUTTON = 1
PADDING = 14  # отступ текста и кнопок от края панели

Color = tuple[int, int, int]


class BuildPanel:
    def __init__(self, screen_size: tuple[int, int], build_mode: BuildMode,
                 demolish_mode: DemolishMode) -> None:
        self.build = build_mode
        self.demolish = demolish_mode
        screen_w, screen_h = screen_size

        # Панель по центру внизу экрана. min() — чтобы на узком экране не вылезла за края.
        width = min(BUILD_PANEL_WIDTH, screen_w - 2 * UI_MARGIN)
        self.rect = pygame.Rect(0, 0, width, BUILD_PANEL_HEIGHT)
        self.rect.midbottom = (screen_w // 2, screen_h - UI_MARGIN)

        # Кнопки справа: [Построить / Снести] [Отмена].
        # Надпись и цвет первой кнопки меняются в update() в зависимости от режима.
        cancel_rect = pygame.Rect(0, 0, TEXT_BUTTON_WIDTH, TEXT_BUTTON_HEIGHT)
        cancel_rect.midright = (self.rect.right - PADDING, self.rect.centery)
        confirm_rect = pygame.Rect(0, 0, TEXT_BUTTON_WIDTH, TEXT_BUTTON_HEIGHT)
        confirm_rect.midright = (cancel_rect.left - UI_BUTTON_GAP, self.rect.centery)
        self.confirm_button = Button(confirm_rect, text="Построить", hover_color=COLOR_UI_CONFIRM_HOVER)
        self.cancel_button = Button(cancel_rect, text="Отмена")

        self.title_font = pygame.font.SysFont("consolas", 17, bold=True)
        self.hint_font = pygame.font.SysFont("consolas", 14)

    # --- Состояние ---

    @property
    def visible(self) -> bool:
        return self.build.active or self.demolish.active

    @property
    def confirming(self) -> bool:
        """Ждём ли подтверждения (в любом из режимов) — тогда показываем кнопки."""
        return (self.build.state == BuildState.CONFIRMING
                or self.demolish.state == DemolishState.CONFIRMING)

    def contains(self, pos: tuple[int, int]) -> bool:
        """Курсор над панелью? (Пока панель скрыта — всегда нет.)"""
        return self.visible and self.rect.collidepoint(pos)

    # --- Ввод и обновление ---

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            if event.button == LEFT_BUTTON and self.confirming:
                # Кнопки передают нажатие тому режиму, который сейчас включён
                mode = self.demolish if self.demolish.active else self.build
                if self.confirm_button.contains(event.pos):
                    mode.confirm()
                elif self.cancel_button.contains(event.pos):
                    mode.reject()
            # Любой клик по панели «съедаем», иначе он дойдёт до карты
            # и попытается построить (или снести) что-то под панелью
            return True
        return False

    def update(self, mouse_pos: tuple[int, int]) -> None:
        # Первая кнопка: «Снести» (красная) при сносе, «Построить» (зелёная) при строительстве
        if self.demolish.active:
            self.confirm_button.text = "Снести"
            self.confirm_button.hover_color = COLOR_UI_DANGER_HOVER
        else:
            self.confirm_button.text = "Построить"
            self.confirm_button.hover_color = COLOR_UI_CONFIRM_HOVER
        self.confirm_button.update(mouse_pos)
        self.cancel_button.update(mouse_pos)

    # --- Тексты для каждого режима ---

    def _build_texts(self) -> tuple[str, Color, str, Color]:
        """(заголовок, его цвет, подсказка, её цвет) для строительства."""
        item = self.build.item
        assert item is not None  # панель рисуется, только когда товар выбран
        if self.build.state == BuildState.CONFIRMING:
            return (f"Построить «{item.name}» за {item.price}?", COLOR_PRICE,
                    "Enter — построить   Esc — выбрать другое место", COLOR_TEXT_DIM)
        width, height = item.size
        title = f"Строительство: {item.name}   Цена: {item.price}   Размер: {width}×{height}"
        if self.build.cursor_error:
            # Курсор над местом, где строить нельзя, — объясняем почему
            return title, COLOR_TEXT, self.build.cursor_error, COLOR_TEXT_ERROR
        return (title, COLOR_TEXT,
                "ЛКМ — выбрать место   ПКМ / Esc — отменить строительство", COLOR_TEXT_DIM)

    def _demolish_texts(self) -> tuple[str, Color, str, Color]:
        """(заголовок, его цвет, подсказка, её цвет) для сноса."""
        if self.demolish.state == DemolishState.CONFIRMING and self.demolish.target:
            return (f"Снести «{self.demolish.target.item.name}»?", COLOR_TEXT_ERROR,
                    "Enter — снести   Esc — выбрать другое здание", COLOR_TEXT_DIM)
        hovered = self.demolish.hovered
        if hovered:
            return (f"Снос: {hovered.item.name}", COLOR_TEXT,
                    "ЛКМ — выбрать для сноса   ПКМ / Esc — выйти из режима сноса", COLOR_TEXT_DIM)
        return ("Снос зданий", COLOR_TEXT,
                "Наведите курсор на здание   ПКМ / Esc — выйти из режима сноса", COLOR_TEXT_DIM)

    # --- Отрисовка ---

    def draw(self, screen: pygame.Surface) -> None:
        if not self.visible:
            return

        # Фон и рамка
        pygame.draw.rect(screen, COLOR_MENU_PANEL, self.rect, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)

        if self.demolish.active:
            title, title_color, hint, hint_color = self._demolish_texts()
        else:
            title, title_color, hint, hint_color = self._build_texts()

        # Две строки текста слева: заголовок и подсказка
        title_surface = self.title_font.render(title, True, title_color)
        hint_surface = self.hint_font.render(hint, True, hint_color)
        x = self.rect.left + PADDING
        total_h = title_surface.get_height() + 4 + hint_surface.get_height()
        y = self.rect.centery - total_h // 2  # обе строки вместе — по центру панели
        screen.blit(title_surface, (x, y))
        screen.blit(hint_surface, (x, y + title_surface.get_height() + 4))

        # Кнопки — только в подтверждении
        if self.confirming:
            self.confirm_button.draw(screen)
            self.cancel_button.draw(screen)
