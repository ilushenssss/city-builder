"""Кнопка: с иконкой (меню «☰», крестик «✕», выход «⏻», назад «←») или с текстом.

Button(rect, ICON_MENU)            — кнопка-иконка
Button(rect, text="Построить")     — кнопка с надписью

Иконки рисуем линиями, а не символами шрифта: в стандартных шрифтах
этих символов может не оказаться, и вместо них появятся «квадратики».
"""

from __future__ import annotations

import math

import pygame

from city_builder.config import (
    COLOR_UI_BORDER,
    COLOR_UI_BUTTON,
    COLOR_UI_BUTTON_HOVER,
    COLOR_UI_ICON,
    UI_BORDER_RADIUS,
)

# Какие иконки умеет рисовать кнопка
ICON_MENU = "menu"    # три горизонтальные полоски («гамбургер»)
ICON_CLOSE = "close"  # крестик
ICON_EXIT = "exit"    # значок «питание»: кружок с разрывом сверху и чёрточкой
ICON_BACK = "back"    # стрелка влево
ICON_DEMOLISH = "demolish"  # мусорная корзина (снос зданий)
ICON_PAUSE = "pause"  # две вертикальные полоски


class Button:
    def __init__(self, rect: pygame.Rect, icon: str | None = None, *,
                 text: str | None = None,
                 hover_color: tuple[int, int, int] = COLOR_UI_BUTTON_HOVER) -> None:
        self.rect = rect      # где кнопка на экране и какого она размера
        self.icon = icon      # одна из констант ICON_... выше (или None)
        self.text = text      # надпись на кнопке (или None)
        self.hover_color = hover_color  # цвет фона при наведении (у выхода — красный)
        self.hovered = False  # находится ли курсор над кнопкой (для подсветки)
        # «Нажатое» состояние для кнопок-переключателей (например, режим сноса включён):
        # кнопка подсвечена, даже когда курсор не над ней
        self.active = False
        # Шрифт нужен только кнопкам с текстом. Создаём один раз, а не каждый кадр.
        self.font = pygame.font.SysFont("consolas", 16, bold=True) if text else None

    def contains(self, pos: tuple[int, int]) -> bool:
        """Попадает ли точка экрана (например, курсор) в кнопку."""
        return self.rect.collidepoint(pos)

    def update(self, mouse_pos: tuple[int, int]) -> None:
        """Каждый кадр обновляем подсветку по положению курсора."""
        self.hovered = self.contains(mouse_pos)

    def draw(self, screen: pygame.Surface) -> None:
        # Фон: при наведении — светлее, чтобы было видно, что кнопка «живая»
        color = self.hover_color if (self.hovered or self.active) else COLOR_UI_BUTTON
        pygame.draw.rect(screen, color, self.rect, border_radius=UI_BORDER_RADIUS)
        # Рамка (толщина 1)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)
        if self.text and self.font:
            label = self.font.render(self.text, True, COLOR_UI_ICON)
            screen.blit(label, label.get_rect(center=self.rect.center))
        else:
            self._draw_icon(screen)

    def _draw_icon(self, screen: pygame.Surface) -> None:
        """Рисует иконку внутри кнопки. Подчёркивание в имени — «внутренний» метод,
        снаружи класса его вызывать не предполагается."""
        # Иконка занимает середину кнопки с отступом в 30% размера от каждого края
        pad = self.rect.width * 0.3
        left = self.rect.left + pad
        right = self.rect.right - pad
        top = self.rect.top + pad
        bottom = self.rect.bottom - pad
        width = 3  # толщина линий иконки

        if self.icon == ICON_MENU:
            # Три горизонтальные линии: сверху, посередине, снизу
            for y in (top, self.rect.centery, bottom):
                pygame.draw.line(screen, COLOR_UI_ICON, (left, y), (right, y), width)
        elif self.icon == ICON_CLOSE:
            # Две диагонали крест-накрест
            pygame.draw.line(screen, COLOR_UI_ICON, (left, top), (right, bottom), width)
            pygame.draw.line(screen, COLOR_UI_ICON, (left, bottom), (right, top), width)
        elif self.icon == ICON_EXIT:
            # Значок «питание» ⏻: дуга окружности с разрывом сверху...
            circle = pygame.Rect(left, top, right - left, bottom - top)
            # Углы в pygame — в радианах, отсчёт от направления «вправо»
            # против часовой стрелки. math.pi / 2 — это «вверх».
            # Рисуем дугу от «вверх + 0.6» почти по кругу до «вверх - 0.6»,
            # оставляя сверху разрыв.
            gap = 0.6
            pygame.draw.arc(screen, COLOR_UI_ICON, circle,
                            math.pi / 2 + gap, math.pi / 2 - gap + 2 * math.pi, width)
            # ...и вертикальная чёрточка, входящая в разрыв
            cx = self.rect.centerx
            pygame.draw.line(screen, COLOR_UI_ICON, (cx, top - 2), (cx, self.rect.centery), width)
        elif self.icon == ICON_BACK:
            # Стрелка влево: горизонтальная линия и два «уса» от её левого конца
            cx, cy = self.rect.center
            pygame.draw.line(screen, COLOR_UI_ICON, (left, cy), (right, cy), width)
            pygame.draw.line(screen, COLOR_UI_ICON, (left, cy), (cx, top), width)
            pygame.draw.line(screen, COLOR_UI_ICON, (left, cy), (cx, bottom), width)
        elif self.icon == ICON_PAUSE:
            # Две вертикальные полоски по бокам от центра
            cx = self.rect.centerx
            for x in (cx - 4, cx + 4):
                pygame.draw.line(screen, COLOR_UI_ICON, (x, top), (x, bottom), 4)
        elif self.icon == ICON_DEMOLISH:
            # Мусорная корзина: ручка, крышка, ведро с двумя полосками
            cx = round(self.rect.centerx)
            lid_y = round(top)
            # Ручка — маленький прямоугольник над крышкой
            pygame.draw.rect(screen, COLOR_UI_ICON, pygame.Rect(cx - 3, lid_y - 4, 7, 5), 2)
            # Крышка — горизонтальная линия чуть шире ведра
            pygame.draw.line(screen, COLOR_UI_ICON, (left - 1, lid_y), (right + 1, lid_y), width)
            # Ведро — рамка под крышкой, чуть уже крышки и чуть ниже обычной иконки
            body = pygame.Rect(round(left) + 2, lid_y + 3, round(right - left) - 3, round(bottom - lid_y))
            pygame.draw.rect(screen, COLOR_UI_ICON, body, 2, border_radius=2)
            # Две вертикальные полоски на ведре
            for x in (cx - 3, cx + 2):
                pygame.draw.line(screen, COLOR_UI_ICON, (x, body.top + 4), (x, body.bottom - 5), 2)
