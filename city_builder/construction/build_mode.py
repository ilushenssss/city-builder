"""Режим строительства — логика без отрисовки.

Режим проходит три состояния (это называется «конечный автомат»):

    IDLE ──(выбрали товар в магазине)──> PLACING ──(клик по карте)──> CONFIRMING
     ^                                    │   ^                          │
     └────────(Esc / правая кнопка)───────┘   └──(Отмена / Esc)──────────┤
                                              └──(Построить / Enter)─────┘
                                                  здание поставлено,
                                                  можно ставить ещё одно

  IDLE       — ничего не строим, клики по карте ничего не делают.
  PLACING    — товар выбран, «призрак» здания ходит за курсором.
  CONFIRMING — место выбрано и зафиксировано, ждём «Построить» или «Отмена».

После постройки режим возвращается в PLACING с тем же товаром:
удобно поставить несколько дорог или домов подряд.

Здесь нет pygame-отрисовки: как всё это выглядит, решают Renderer
(призрак на карте) и BuildPanel (панель внизу экрана).
"""

from enum import Enum, auto

import pygame

from city_builder.data.catalog import ShopItem
from city_builder.economy.economy import Economy
from city_builder.world.building import Building
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile

LEFT_BUTTON = 1
RIGHT_BUTTON = 3


class BuildState(Enum):
    # auto() сам раздаёт значения 1, 2, 3 — нам важны только имена
    IDLE = auto()
    PLACING = auto()
    CONFIRMING = auto()


class BuildMode:
    def __init__(self, grid: Grid, economy: Economy) -> None:
        self.grid = grid
        self.economy = economy  # чтобы проверять и списывать деньги
        self.state = BuildState.IDLE
        self.item: ShopItem | None = None  # что строим

        # Куда встанет здание, если кликнуть прямо сейчас (левая верхняя клетка),
        # и почему туда нельзя (None — можно). Обновляется каждый кадр.
        self.cursor_pos: tuple[int, int] | None = None
        self.cursor_error: str | None = None
        # Предупреждение: строить можно, но что-то не так (например, нет дороги)
        self.cursor_warning: str | None = None

        # Выбранное место, ждущее подтверждения (только в CONFIRMING)
        self.target: tuple[int, int] | None = None

    @property
    def active(self) -> bool:
        """Идёт ли сейчас строительство (выбран товар)."""
        return self.state != BuildState.IDLE

    # --- Переходы между состояниями ---

    def select(self, item: ShopItem) -> None:
        """Игрок выбрал товар в магазине -> начинаем выбирать место."""
        self.item = item
        self.state = BuildState.PLACING
        self.target = None

    def cancel(self) -> None:
        """Полностью выйти из режима строительства."""
        self.state = BuildState.IDLE
        self.item = None
        self.cursor_pos = None
        self.cursor_error = None
        self.cursor_warning = None
        self.target = None

    # --- Проверки места ---

    def site_error(self, x: int, y: int) -> str | None:
        """Почему здесь нельзя строить (None — можно): место или деньги."""
        assert self.item is not None
        error = self.grid.placement_error(self.item, x, y)
        if error:
            return error
        if not self.economy.can_afford(self.item.price):
            return f"Не хватает денег: нужно {self.item.price}, есть {self.economy.money}"
        return None

    def site_warning(self, x: int, y: int) -> str | None:
        """Строить можно, но здание не будет работать — предупреждаем заранее."""
        assert self.item is not None
        width, height = self.item.size
        if self.item.needs_road and not self.grid.site_has_road(x, y, width, height):
            return "Рядом нет дороги — здание не будет работать"
        return None

    @property
    def target_warning(self) -> str | None:
        """Предупреждение для уже выбранного места (в подтверждении)."""
        if self.target is None or self.item is None:
            return None
        return self.site_warning(*self.target)  # * раскладывает (x, y) на два аргумента

    # --- Переходы между состояниями (продолжение) ---

    def choose_site(self) -> None:
        """Клик по карте: зафиксировать место под курсором, если там можно строить."""
        if self.cursor_pos is None or self.cursor_error is not None:
            return  # курсор вне карты или место плохое — ничего не делаем
        if self.state == BuildState.CONFIRMING and self.cursor_pos == self.target:
            # Повторный клик по уже выбранному месту — считаем это подтверждением
            self.confirm()
            return
        # В PLACING — выбираем место; в CONFIRMING — переносим выбор на новое место
        self.target = self.cursor_pos
        self.state = BuildState.CONFIRMING

    def confirm(self) -> Building | None:
        """«Построить»: ставим здание на карту. Возвращает построенное здание."""
        if self.state != BuildState.CONFIRMING or self.target is None or self.item is None:
            return None
        x, y = self.target
        # Проверяем ещё раз: пока игрок думал, место могло стать недоступным,
        # а деньги — закончиться (на содержание за прошедшие тики)
        if self.site_error(x, y) is not None:
            self.reject()
            return None
        self.economy.spend(self.item.price)
        building = self.grid.place(self.item, x, y)
        self.target = None
        self.state = BuildState.PLACING  # тот же товар — можно строить дальше
        return building

    def reject(self) -> None:
        """«Отмена» в подтверждении: место сбрасывается, товар остаётся выбранным."""
        if self.state == BuildState.CONFIRMING:
            self.target = None
            self.state = BuildState.PLACING

    def back(self) -> None:
        """Esc / правая кнопка: шаг назад по цепочке состояний."""
        if self.state == BuildState.CONFIRMING:
            self.reject()  # из подтверждения — обратно к выбору места
        else:
            self.cancel()  # из выбора места — выход из строительства

    # --- Каждый кадр ---

    def update_hover(self, tile: Tile | None) -> None:
        """Пересчитать, куда встанет здание при клике, по клетке под курсором."""
        if not self.active or self.item is None:
            return
        if tile is None:  # курсор вне карты или над интерфейсом
            self.cursor_pos = None
            self.cursor_error = None
            self.cursor_warning = None
            return
        # Курсор указывает на центр здания, а нам нужна левая верхняя клетка.
        # Для 1×1 и 2×2 это сама клетка под курсором, для 3×3 — на одну левее и выше.
        width, height = self.item.size
        x = tile.x - (width - 1) // 2
        y = tile.y - (height - 1) // 2
        self.cursor_pos = (x, y)
        self.cursor_error = self.site_error(x, y)
        # Предупреждение имеет смысл, только если строить вообще можно
        self.cursor_warning = None if self.cursor_error else self.site_warning(x, y)

    # --- Ввод ---

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Клики по карте и клавиши строительства.
        Возвращает True, если событие обработано и дальше его передавать не нужно."""
        if not self.active:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.back()
                return True  # важно: иначе Esc дойдёт до InputHandler и закроет игру
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.confirm()
                return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == LEFT_BUTTON:
                self.choose_site()
                return True
            if event.button == RIGHT_BUTTON:
                self.back()
                return True

        return False
