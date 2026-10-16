"""Карточка в меню.

Карточка — универсальный «прямоугольник с содержимым». Она ничего не знает
о магазине и товарах: меню само решает, что в неё написать. Все поля,
кроме rect, необязательные:

    ┌──────────────────┐
    │ ┌──────────────┐ │
    │ │ image / color│ │  <- картинка, а если её нет — цветной прямоугольник
    │ └──────────────┘ │
    │      title       │  <- название (переносится на несколько строк)
    │   description    │  <- описание (сколько поместится)
    │                  │
    │     details      │  <- характеристики: «Жильё: 6 · Содержание: 1» (голубым)
    │ footer     badge │  <- внизу: слева, например, цена; справа — размер
    └──────────────────┘

Если у карточки есть только title — он рисуется просто по центру
(так выглядит карточка «Магазин» в главном меню).

Поведение по клику (обрабатывает Menu):
  * opens   — какую страницу меню открыть (например, категорию магазина);
  * item_id — какой товар выбран (включает режим строительства).
"""

from __future__ import annotations

from typing import Tuple

from dataclasses import dataclass

import pygame

from city_builder.config import (
    CARD_IMAGE_HEIGHT,
    CARD_PADDING,
    COLOR_CARD,
    COLOR_CARD_HOVER,
    COLOR_CARD_IMAGE_BG,
    COLOR_DETAILS,
    COLOR_PRICE,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_UI_BORDER,
    UI_BORDER_RADIUS,
)

Color = Tuple[int, int, int]


@dataclass
class CardFonts:
    """Шрифты для карточек. Создаются один раз в меню и передаются в draw():
    загружать шрифт заново для каждой карточки каждый кадр было бы очень медленно."""
    title: pygame.font.Font
    text: pygame.font.Font
    footer: pygame.font.Font

    @classmethod
    def create(cls) -> "CardFonts":
        # classmethod — метод, который вызывается у класса, а не у объекта:
        # CardFonts.create(). Удобно для «фабрик», создающих объект.
        return cls(
            title=pygame.font.SysFont("consolas", 18, bold=True),
            text=pygame.font.SysFont("consolas", 14),
            footer=pygame.font.SysFont("consolas", 15, bold=True),
        )


def wrap_parts(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Перенос строки характеристик «по смыслу»: только по разделителям « · » и после «→»,
    чтобы не оставалось висящих «·» и одиноких чисел. Кусок длиннее строки — обычный перенос."""
    # Режем на куски: «Энергия −25 · Вода −10» -> ["Энергия −25", "Вода −10"],
    # «Древесина 6 → Товары 12» -> ["Древесина 6 →", "Товары 12"]
    parts = text.replace(" → ", " →\n").replace(" · ", "\n").split("\n")
    lines: list[str] = []
    current = ""
    for part in parts:
        joiner = " " if current.endswith("→") else " · "
        candidate = f"{current}{joiner}{part}" if current else part
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = part
    if current:
        lines.append(current)
    # Если кусок сам по себе не влез — переносим его по словам
    return [piece for line in lines for piece in wrap_text(line, font, max_width)]


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Разбить текст на строки, чтобы каждая помещалась в max_width пикселей.

    Набираем слова в строку, пока она помещается; не поместилось — начинаем новую.
    font.size(текст) возвращает (ширина, высота) текста в пикселях.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word  # слишком длинное слово всё равно ставим — резать слова не будем
    if current:
        lines.append(current)
    return lines


class Card:
    def __init__(
        self,
        rect: pygame.Rect,
        title: str | None = None,
        *,  # всё после звёздочки можно передавать только по имени: Card(rect, color=...)
        color: Color | None = None,
        image: pygame.Surface | None = None,
        description: str = "",
        details: list[str] | None = None,
        footer: str | None = None,
        badge: str | None = None,
        opens: str | None = None,
        item_id: str | None = None,
    ) -> None:
        self.rect = rect                # положение и размер карточки на экране
        self.title = title              # название (None — пустая карточка)
        self.color = color              # цвет картинки-заглушки (None — без картинки)
        # Картинка, уже уменьшенная под размер карточки (это делает Menu).
        # Если она есть, вместо цветного прямоугольника рисуется она.
        self.image = image
        self.description = description  # описание мелким шрифтом
        # Характеристики над нижней строкой — список строк. «or []»: если передали None,
        # берём пустой список (пустой список по умолчанию в аргументах писать нельзя —
        # он был бы общим для всех карточек)
        self.details = details or []
        self.footer = footer            # текст внизу слева (цена, количество товаров)
        self.badge = badge              # текст внизу справа (размер здания)
        self.opens = opens              # id страницы меню, которую открывает клик
        self.item_id = item_id          # id товара из каталога (для покупки)
        self.hovered = False            # курсор над карточкой — подсвечиваем её
        # Товар ещё закрыт: нужен этот уровень города (None — открыт). Меню обновляет каждый кадр.
        self.locked_level: int | None = None

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def update(self, mouse_pos: tuple[int, int]) -> None:
        self.hovered = self.contains(mouse_pos) and self.locked_level is None

    def _draw_lock(self, screen: pygame.Surface, fonts: "CardFonts") -> None:
        """Закрытый товар: затемнение, замок и «Уровень N» по центру карточки."""
        shade_layer = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(shade_layer, (15, 18, 24, 170), shade_layer.get_rect(), border_radius=UI_BORDER_RADIUS)
        screen.blit(shade_layer, self.rect)
        cx, cy = self.rect.centerx, self.rect.centery - 14
        body = pygame.Rect(0, 0, 30, 24)
        body.center = (cx, cy + 8)
        pygame.draw.circle(screen, (200, 200, 205), (cx, cy - 4), 10, 4)   # дужка
        pygame.draw.rect(screen, (200, 200, 205), body, border_radius=4)     # корпус
        pygame.draw.circle(screen, (60, 60, 70), (cx, cy + 6), 3)            # скважина
        text = fonts.title.render(f"Уровень {self.locked_level}", True, (235, 235, 240))
        screen.blit(text, text.get_rect(midtop=(cx, cy + 26)))

    def draw(self, screen: pygame.Surface, fonts: CardFonts) -> None:
        # --- Фон и рамка ---
        bg = COLOR_CARD_HOVER if self.hovered else COLOR_CARD
        pygame.draw.rect(screen, bg, self.rect, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)

        # --- Простая карточка: только надпись по центру ---
        if self.color is None and self.image is None and not self.description and not self.footer:
            if self.title:
                text = fonts.title.render(self.title, True, COLOR_TEXT)
                screen.blit(text, text.get_rect(center=self.rect.center))
            return

        # --- Подробная карточка: содержимое сверху вниз ---
        # inflate(-24, -24) — прямоугольник, уменьшенный на 12 px с каждой стороны
        inner = self.rect.inflate(-2 * CARD_PADDING, -2 * CARD_PADDING)
        y = inner.top  # «курсор» по вертикали: куда рисовать следующий элемент

        # 1. Картинка — или цветной прямоугольник, если картинки нет
        image_rect = pygame.Rect(inner.left, y, inner.width, CARD_IMAGE_HEIGHT)
        if self.image is not None:
            # Тёмная подложка, а на ней картинка по центру
            # (картинка уже уменьшена с сохранением пропорций и может быть уже области)
            pygame.draw.rect(screen, COLOR_CARD_IMAGE_BG, image_rect, border_radius=UI_BORDER_RADIUS)
            screen.blit(self.image, self.image.get_rect(center=image_rect.center))
            y = image_rect.bottom + 10
        elif self.color is not None:
            pygame.draw.rect(screen, self.color, image_rect, border_radius=UI_BORDER_RADIUS)
            y = image_rect.bottom + 10

        # 2. Название — по центру, может занять несколько строк
        if self.title:
            for line in wrap_text(self.title, fonts.title, inner.width):
                text = fonts.title.render(line, True, COLOR_TEXT)
                screen.blit(text, text.get_rect(midtop=(inner.centerx, y)))
                y += text.get_height()
            y += 6

        line_height = fonts.text.get_linesize()

        # 3. Характеристики — прижаты к низу, над ценой. Считаем их место заранее,
        #    чтобы описание знало, где остановиться.
        footer_top = inner.bottom - fonts.footer.get_height()
        # Каждую строку характеристик тоже переносим, если она не влезает по ширине
        details_lines = [part for line in self.details for part in wrap_parts(line, fonts.text, inner.width)]
        details_top = footer_top - 6 - len(details_lines) * line_height
        for i, line in enumerate(details_lines):
            text = fonts.text.render(line, True, COLOR_DETAILS)
            screen.blit(text, text.get_rect(midtop=(inner.centerx, details_top + i * line_height)))

        # 4. Описание — сколько строк поместится до характеристик
        desc_lines = wrap_text(self.description, fonts.text, inner.width)
        fits = max(0, int((details_top - 4 - y) // line_height))  # сколько строк влезает
        if len(desc_lines) > fits:
            # Не помещается целиком — показываем сколько можно и ставим многоточие
            desc_lines = desc_lines[:fits]
            if desc_lines:
                desc_lines[-1] = desc_lines[-1].rstrip(" ,.") + "…"
        for line in desc_lines:
            text = fonts.text.render(line, True, COLOR_TEXT_DIM)
            screen.blit(text, text.get_rect(midtop=(inner.centerx, y)))
            y += line_height

        # 5. Нижняя строка: footer слева, badge справа
        if self.footer:
            text = fonts.footer.render(self.footer, True, COLOR_PRICE)
            screen.blit(text, text.get_rect(bottomleft=inner.bottomleft))
        if self.badge:
            text = fonts.footer.render(self.badge, True, COLOR_TEXT_DIM)
            screen.blit(text, text.get_rect(bottomright=inner.bottomright))

        if self.locked_level is not None:
            self._draw_lock(screen, fonts)
