"""Меню: панель по центру экрана со страницами карточек.

Когда меню открыто:
  * игра под ним затемняется;
  * клики, колесо и клавиши не доходят до карты (меню их «съедает»);
  * закрыть можно крестиком, клавишей Esc, кликом мимо панели
    или повторным нажатием на кнопку меню.

Страницы:
  * «main»        (Меню)    — главная. Первая карточка «Магазин» открывает магазин.
  * «shop»        (Магазин) — карточки категорий из базы товаров.
  * «shop/<id>»   (Магазин / Дороги, ...) — товары одной категории.
Страницы магазина строятся автоматически из каталога (data/shop.json):
новая категория в файле = новая карточка и новая страница в магазине.

Переходы запоминаются в «стопке» страниц (self.page_stack):
    открыли магазин:   ["main"] -> ["main", "shop"]
    открыли «Дороги»:  ["main", "shop"] -> ["main", "shop", "shop/roads"]
    нажали «назад»:    ["main", "shop", "shop/roads"] -> ["main", "shop"]
Текущая страница — последняя в стопке. Благодаря стопке можно делать
сколько угодно вложенных страниц, и «назад» всегда вернёт на предыдущую.

Схема панели (3 колонки, 2 ряда). Стрелка «назад» видна только
на вложенных страницах:

    ┌──────────────────────────────────┐
    │ [<] Магазин / Дороги          [X]│  <- заголовок, MENU_HEADER_HEIGHT
    │ ┌──────┐  ┌──────┐  ┌──────┐     │
    │ │      │  │      │  │      │     │
    │ └──────┘  └──────┘  └──────┘     │  <- карточки, между ними CARD_GAP
    │ ┌──────┐  ┌──────┐  ┌──────┐     │
    │ │      │  │      │  │      │     │
    │ └──────┘  └──────┘  └──────┘     │
    └──────────────────────────────────┘
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

import pygame

from city_builder.config import (
    CARD_GAP,
    CARD_HEIGHT,
    CARD_WIDTH,
    CLOSE_BUTTON_SIZE,
    COLOR_MENU_OVERLAY,
    COLOR_MENU_PANEL,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_UI_BORDER,
    MENU_CARD_COLUMNS,
    MENU_CARD_COUNT,
    MENU_HEADER_HEIGHT,
    UI_BORDER_RADIUS,
)
from city_builder.data.catalog import Catalog
from city_builder.ui.button import ICON_BACK, ICON_CLOSE, Button
from city_builder.ui.card import Card, CardFonts

LEFT_BUTTON = 1  # левая кнопка мыши

# Идентификаторы страниц меню
PAGE_MAIN = "main"
PAGE_SHOP = "shop"


def category_page_id(category_id: str) -> str:
    """id страницы с товарами категории: "roads" -> "shop/roads"."""
    return f"{PAGE_SHOP}/{category_id}"


def items_count_text(n: int) -> str:
    """«1 товар», «3 товара», «5 товаров» — русские окончания после числа.

    Правило: смотрим на последнюю цифру, но 11–14 — всегда «товаров».
    """
    if n % 10 == 1 and n % 100 != 11:
        word = "товар"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "товара"
    else:
        word = "товаров"
    return f"{n} {word}"


@dataclass
class MenuPage:
    """Одна страница меню: заголовок и набор карточек."""
    title: str
    cards: list[Card]


class Menu:
    def __init__(self, screen_size: tuple[int, int], catalog: Catalog,
                 on_item_selected: Callable[[str], None]) -> None:
        self.is_open = False
        # Функция, которую меню вызовет, когда игрок кликнет по товару.
        # Меню не знает, что дальше делать с товаром, — это решает тот,
        # кто передал функцию (UIManager включит режим строительства).
        # Такой приём называется «обратный вызов» (callback).
        self.on_item_selected = on_item_selected
        screen_w, screen_h = screen_size

        # --- Размер панели ---
        # Панель одна на все страницы, поэтому её высоту считаем
        # по самой «длинной» странице: главная, список категорий, каждая категория.
        columns = MENU_CARD_COLUMNS
        page_sizes = [MENU_CARD_COUNT, len(catalog.categories)]
        page_sizes += [len(catalog.items_in(c.id)) for c in catalog.categories]
        rows = max(1, math.ceil(max(page_sizes) / columns))  # 6 карточек / 3 колонки = 2 ряда
        # Ширина: карточки + промежутки между ними и по краям (их на один больше, чем колонок)
        panel_w = columns * CARD_WIDTH + (columns + 1) * CARD_GAP
        panel_h = MENU_HEADER_HEIGHT + rows * CARD_HEIGHT + rows * CARD_GAP
        self.panel = pygame.Rect(0, 0, panel_w, panel_h)
        self.panel.center = (screen_w // 2, screen_h // 2)  # ставим панель по центру экрана

        # Вертикальный центр заголовка — по нему выравниваем кнопки и текст
        header_center_y = self.panel.top + MENU_HEADER_HEIGHT // 2

        # --- Кнопка-крестик в правом верхнем углу панели ---
        close_rect = pygame.Rect(0, 0, CLOSE_BUTTON_SIZE, CLOSE_BUTTON_SIZE)
        close_rect.midright = (self.panel.right - CARD_GAP, header_center_y)
        self.close_button = Button(close_rect, ICON_CLOSE)

        # --- Кнопка «назад» в левом верхнем углу панели ---
        back_rect = pygame.Rect(0, 0, CLOSE_BUTTON_SIZE, CLOSE_BUTTON_SIZE)
        back_rect.midleft = (self.panel.left + CARD_GAP, header_center_y)
        self.back_button = Button(back_rect, ICON_BACK)

        # --- Страницы ---
        self.pages = self._build_pages(catalog)
        self.page_stack = [PAGE_MAIN]  # см. описание в начале файла

        # --- Полупрозрачное затемнение на весь экран ---
        # SRCALPHA — поверхность с поддержкой прозрачности. Создаём её один раз,
        # а не каждый кадр: создание поверхностей — дорогая операция.
        self.overlay = pygame.Surface(screen_size, pygame.SRCALPHA)
        self.overlay.fill(COLOR_MENU_OVERLAY)

        self.title_font = pygame.font.SysFont("consolas", 24, bold=True)
        self.empty_font = pygame.font.SysFont("consolas", 18)
        self.card_fonts = CardFonts.create()

    # --- Построение страниц ---

    def _card_rects(self, count: int) -> list[pygame.Rect]:
        """Разложить count карточек по сетке внутри панели."""
        rects = []
        for i in range(count):
            col = i % MENU_CARD_COLUMNS   # номер колонки: 0, 1, 2, 0, 1, 2, ...
            row = i // MENU_CARD_COLUMNS  # номер ряда:    0, 0, 0, 1, 1, 1, ...
            x = self.panel.left + CARD_GAP + col * (CARD_WIDTH + CARD_GAP)
            y = self.panel.top + MENU_HEADER_HEIGHT + row * (CARD_HEIGHT + CARD_GAP)
            rects.append(pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT))
        return rects

    def _build_pages(self, catalog: Catalog) -> dict[str, MenuPage]:
        """Создать все страницы меню. Новая страница = новая запись в словаре."""
        pages: dict[str, MenuPage] = {}

        # --- Главная: первая карточка — «Магазин», остальные пока пустые ---
        main_rects = self._card_rects(MENU_CARD_COUNT)
        main_cards = [Card(main_rects[0], title="Магазин", opens=PAGE_SHOP)]
        main_cards += [Card(rect) for rect in main_rects[1:]]
        pages[PAGE_MAIN] = MenuPage("Меню", main_cards)

        # --- Магазин: карточка на каждую категорию + страница с её товарами ---
        category_cards = []
        category_rects = self._card_rects(len(catalog.categories))
        # zip идёт по двум спискам параллельно: (категория 1, место 1), (категория 2, место 2)...
        for category, rect in zip(catalog.categories, category_rects):
            items = catalog.items_in(category.id)
            page_id = category_page_id(category.id)

            # Карточка категории: клик открывает страницу с товарами
            category_cards.append(Card(
                rect,
                category.name,
                color=category.color,
                description=category.description,
                footer=items_count_text(len(items)),
                opens=page_id,
            ))

            # Страница категории: карточка на каждый товар
            item_cards = []
            for item, item_rect in zip(items, self._card_rects(len(items))):
                width, height = item.size
                item_cards.append(Card(
                    item_rect,
                    item.name,
                    color=item.color,
                    description=item.description,
                    footer=f"Цена: {item.price}",
                    badge=f"{width}×{height}",  # сколько клеток занимает здание
                    item_id=item.id,
                ))
            pages[page_id] = MenuPage(f"Магазин / {category.name}", item_cards)

        pages[PAGE_SHOP] = MenuPage("Магазин", category_cards)
        return pages

    # --- Навигация по страницам ---

    @property
    def current_page(self) -> MenuPage:
        """Текущая страница — последняя в стопке."""
        return self.pages[self.page_stack[-1]]

    @property
    def can_go_back(self) -> bool:
        """Есть ли куда возвращаться (на главной странице — некуда)."""
        return len(self.page_stack) > 1

    def open_page(self, page_id: str) -> None:
        self.page_stack.append(page_id)

    def go_back(self) -> None:
        if self.can_go_back:
            self.page_stack.pop()  # убираем текущую — становится видна предыдущая

    # --- Открыть / закрыть ---

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False
        # При следующем открытии меню начнётся с главной страницы
        self.page_stack = [PAGE_MAIN]

    def toggle(self) -> None:
        """Открыто -> закрыть, закрыто -> открыть."""
        if self.is_open:
            self.close()
        else:
            self.open()

    # --- Ввод и обновление ---

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Обработать событие, пока меню открыто.

        Возвращает True, если событие «съедено» меню и дальше
        (в управление картой) его передавать не нужно.
        """
        if not self.is_open:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # Esc во вложенной странице — назад, на главной — закрыть меню
                if self.can_go_back:
                    self.go_back()
                else:
                    self.close()
            return True  # пока меню открыто, клавиши карту не двигают

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == LEFT_BUTTON:
                self._handle_click(event.pos)
            return True

        if event.type in (pygame.MOUSEWHEEL, pygame.MOUSEMOTION):
            return True  # колесо и движение мыши не должны зумить/тянуть карту

        # Остальное (например, закрытие окна или отпускание кнопки мыши)
        # пропускаем дальше
        return False

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Левый клик внутри открытого меню."""
        if self.close_button.contains(pos):
            self.close()
        elif self.can_go_back and self.back_button.contains(pos):
            self.go_back()
        elif not self.panel.collidepoint(pos):
            self.close()  # клик мимо панели закрывает меню
        else:
            for card in self.current_page.cards:
                if card.contains(pos):
                    if card.opens:
                        self.open_page(card.opens)
                    elif card.item_id:
                        # Товар выбран: закрываем меню, чтобы было видно карту,
                        # и сообщаем, какой товар выбран
                        self.close()
                        self.on_item_selected(card.item_id)
                    break  # карточки не пересекаются — дальше искать незачем

    def update(self, mouse_pos: tuple[int, int]) -> None:
        """Обновить подсветку кнопок и карточек текущей страницы."""
        if not self.is_open:
            return
        self.close_button.update(mouse_pos)
        self.back_button.update(mouse_pos)
        for card in self.current_page.cards:
            card.update(mouse_pos)

    # --- Отрисовка ---

    def draw(self, screen: pygame.Surface) -> None:
        if not self.is_open:
            return
        page = self.current_page

        # 1. Затемняем всю игру под меню
        screen.blit(self.overlay, (0, 0))

        # 2. Панель с рамкой
        pygame.draw.rect(screen, COLOR_MENU_PANEL, self.panel, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, self.panel, 1, border_radius=UI_BORDER_RADIUS)

        # 3. Кнопка «назад» (если есть куда) и заголовок справа от неё
        if self.can_go_back:
            self.back_button.draw(screen)
            title_x = self.back_button.rect.right + CARD_GAP // 2
        else:
            title_x = self.panel.left + CARD_GAP
        title = self.title_font.render(page.title, True, COLOR_TEXT)
        screen.blit(title, title.get_rect(midleft=(title_x, self.back_button.rect.centery)))

        # 4. Крестик и карточки текущей страницы
        self.close_button.draw(screen)
        for card in page.cards:
            card.draw(screen, self.card_fonts)

        # 5. Пустая страница (например, категория без товаров) — подсказка вместо карточек
        if not page.cards:
            text = self.empty_font.render("Здесь пока ничего нет", True, COLOR_TEXT_DIM)
            screen.blit(text, text.get_rect(center=self.panel.center))
