"""Панель режимов просмотра слева (под панелью «Город»): обычный, электричество, вода, пробки.

    [Обычный] [Свет] [Вода] [Пробки]       клавиши F5 F6 F7 F8

  * «Свет»   — здания со светом зелёные, без света — красные, провода ЛЭП светятся;
  * «Вода»   — видны подземные трубы и зона, куда дотягивается вода;
  * «Пробки» — дороги раскрашены по загруженности.

Когда строишь линию, трубу или светофор, нужный режим включается сам
(auto_view) — и выключается, когда строительство закончено.
"""

from __future__ import annotations

import pygame

from city_builder.config import (
    COLOR_MENU_PANEL,
    COLOR_UI_BORDER,
    UI_BORDER_RADIUS,
    VIEW_NORMAL,
    VIEW_POWER,
    VIEW_TRAFFIC,
    VIEW_WATER,
)
from city_builder.ui.button import Button

LEFT_BUTTON = 1
BUTTON_W, BUTTON_H, GAP, PADDING = 72, 28, 4, 6

VIEWS = [  # (режим, надпись, клавиша)
    (VIEW_NORMAL, "Обычный", pygame.K_F5),
    (VIEW_POWER, "Свет", pygame.K_F6),
    (VIEW_WATER, "Вода", pygame.K_F7),
    (VIEW_TRAFFIC, "Пробки", pygame.K_F8),
]


class ViewPanel:
    def __init__(self) -> None:
        width = len(VIEWS) * BUTTON_W + (len(VIEWS) - 1) * GAP + 2 * PADDING
        self.rect = pygame.Rect(0, 0, width, BUTTON_H + 2 * PADDING)  # положение — в update()
        self.buttons: dict[str, Button] = {
            view: Button(pygame.Rect(0, 0, BUTTON_W, BUTTON_H), text=label) for view, label, _ in VIEWS
        }
        self.chosen = VIEW_NORMAL       # что выбрал игрок
        self.auto_view: str | None = None  # что включилось само (при строительстве сетей)

    @property
    def view(self) -> str:
        """Действующий режим: «автоматический» (если есть) важнее выбранного."""
        return self.auto_view or self.chosen

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN:
            for view, _, key in VIEWS:
                if event.key == key:
                    self.chosen = view
                    return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == LEFT_BUTTON and self.contains(event.pos):
            for view, button in self.buttons.items():
                if button.contains(event.pos):
                    self.chosen = view
            return True
        return False

    def update(self, mouse_pos: tuple[int, int], top_left: tuple[int, int]) -> None:
        self.rect.topleft = top_left
        for i, button in enumerate(self.buttons.values()):
            button.rect.topleft = (self.rect.left + PADDING + i * (BUTTON_W + GAP), self.rect.top + PADDING)
        for view, button in self.buttons.items():
            button.active = view == self.view
            button.update(mouse_pos)

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, COLOR_MENU_PANEL, self.rect, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)
        for button in self.buttons.values():
            button.draw(screen)
