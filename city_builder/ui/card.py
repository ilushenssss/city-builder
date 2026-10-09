"""Карточка в меню.

Карточка — универсальный «прямоугольник с содержимым». Она ничего не знает
о магазине и товарах: меню само решает, что в неё написать. Все поля,
кроме rect, необязательные:

    ┌──────────────────┐
    │ ┌──────────────┐ │
    │ │    color     │ │  <- цветной прямоугольник (заглушка для картинки)
    │ └──────────────┘ │
    │      title       │  <- название (переносится на несколько строк)
    │   description    │  <- описание (сколько поместится)
    │                  │
    │ footer     badge │  <- внизу: слева, например, цена; справа — размер
    └──────────────────┘

Если у карточки есть только title — он рисуется просто по центру
(так выглядит карточка «Магазин» в главном меню).

Поведение по клику (обрабатывает Menu):
  * opens   — какую страницу меню открыть (например, категорию магазина);
  * item_id — какой товар выбран (используем на этапе 1 для строительства).
"""

from dataclasses import dataclass

import pygame

from city_builder.config import (
    CARD_IMAGE_HEIGHT,
    CARD_PADDING,
    COLOR_CARD,
    COLOR_CARD_HOVER,
    COLOR_PRICE,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_UI_BORDER,
    UI_BORDER_RADIUS,
)

Color = tuple[int, int, int]


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
        description: str = "",
        footer: str | None = None,
        badge: str | None = None,
        opens: str | None = None,
        item_id: str | None = None,
    ) -> None:
        self.rect = rect                # положение и размер карточки на экране
        self.title = title              # название (None — пустая карточка)
        self.color = color              # цвет картинки-заглушки (None — без картинки)
        self.description = description  # описание мелким шрифтом
        self.footer = footer            # текст внизу слева (цена, количество товаров)
        self.badge = badge              # текст внизу справа (размер здания)
        self.opens = opens              # id страницы меню, которую открывает клик
        self.item_id = item_id          # id товара из каталога (для покупки)
        self.hovered = False            # курсор над карточкой — подсвечиваем её

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def update(self, mouse_pos: tuple[int, int]) -> None:
        self.hovered = self.contains(mouse_pos)

    def draw(self, screen: pygame.Surface, fonts: CardFonts) -> None:
        # --- Фон и рамка ---
        bg = COLOR_CARD_HOVER if self.hovered else COLOR_CARD
        pygame.draw.rect(screen, bg, self.rect, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.rect, 1, border_radius=UI_BORDER_RADIUS)

        # --- Простая карточка: только надпись по центру ---
        if self.color is None and not self.description and not self.footer:
            if self.title:
                text = fonts.title.render(self.title, True, COLOR_TEXT)
                screen.blit(text, text.get_rect(center=self.rect.center))
            return

        # --- Подробная карточка: содержимое сверху вниз ---
        # inflate(-24, -24) — прямоугольник, уменьшенный на 12 px с каждой стороны
        inner = self.rect.inflate(-2 * CARD_PADDING, -2 * CARD_PADDING)
        y = inner.top  # «курсор» по вертикали: куда рисовать следующий элемент

        # 1. Картинка-заглушка
        if self.color is not None:
            image_rect = pygame.Rect(inner.left, y, inner.width, CARD_IMAGE_HEIGHT)
            pygame.draw.rect(screen, self.color, image_rect, border_radius=UI_BORDER_RADIUS)
            y = image_rect.bottom + 10

        # 2. Название — по центру, может занять несколько строк
        if self.title:
            for line in wrap_text(self.title, fonts.title, inner.width):
                text = fonts.title.render(line, True, COLOR_TEXT)
                screen.blit(text, text.get_rect(midtop=(inner.centerx, y)))
                y += text.get_height()
            y += 6

        # 3. Описание — сколько строк поместится до нижней строки
        footer_top = inner.bottom - fonts.footer.get_height()
        line_height = fonts.text.get_linesize()
        for line in wrap_text(self.description, fonts.text, inner.width):
            if y + line_height > footer_top - 4:
                break  # не помещается — остальное не рисуем, чтобы не залезть на цену
            text = fonts.text.render(line, True, COLOR_TEXT_DIM)
            screen.blit(text, text.get_rect(midtop=(inner.centerx, y)))
            y += line_height

        # 4. Нижняя строка: footer слева, badge справа
        if self.footer:
            text = fonts.footer.render(self.footer, True, COLOR_PRICE)
            screen.blit(text, text.get_rect(bottomleft=inner.bottomleft))
        if self.badge:
            text = fonts.footer.render(self.badge, True, COLOR_TEXT_DIM)
            screen.blit(text, text.get_rect(bottomright=inner.bottomright))
