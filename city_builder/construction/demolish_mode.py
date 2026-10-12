"""Режим сноса — логика без отрисовки. Устроен так же, как BuildMode.

    IDLE ──(кнопка 🗑 / Delete)──> SELECTING ──(клик по зданию)──> CONFIRMING
     ^                               │   ^                             │
     └──(Esc / ПКМ / кнопка 🗑)───────┘   └──(Отмена / Esc)─────────────┤
                                          └──(Снести / Enter)──────────┘
                                              здание снесено,
                                              можно сносить следующее

  IDLE       — ничего не сносим.
  SELECTING  — здание под курсором подсвечивается красным.
  CONFIRMING — здание выбрано, ждём «Снести» или «Отмена».

Как это выглядит, решают Renderer (подсветка здания) и BuildPanel (панель внизу).
"""

from enum import Enum, auto

import pygame

from city_builder.economy.economy import Economy
from city_builder.world.building import Building
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile

LEFT_BUTTON = 1
RIGHT_BUTTON = 3


class DemolishState(Enum):
    IDLE = auto()
    SELECTING = auto()
    CONFIRMING = auto()


class DemolishMode:
    def __init__(self, grid: Grid, economy: Economy) -> None:
        self.grid = grid
        self.economy = economy  # чтобы вернуть часть стоимости при сносе
        self.state = DemolishState.IDLE
        self.hovered: Building | None = None  # здание под курсором (обновляется каждый кадр)
        self.hovered_tile: Tile | None = None  # клетка под курсором (для подсветки пустой клетки)
        self.target: Building | None = None   # выбранное здание, ждёт подтверждения

    @property
    def active(self) -> bool:
        return self.state != DemolishState.IDLE

    # --- Переходы между состояниями ---

    def start(self) -> None:
        self.state = DemolishState.SELECTING
        self.target = None

    def cancel(self) -> None:
        self.state = DemolishState.IDLE
        self.hovered = None
        self.target = None

    def toggle(self) -> None:
        """Кнопка 🗑 / Delete: включить или выключить режим сноса."""
        if self.active:
            self.cancel()
        else:
            self.start()

    def choose(self) -> None:
        """Клик по карте: выбрать здание под курсором для сноса."""
        if self.hovered is None:
            return  # под курсором пусто — сносить нечего
        if self.state == DemolishState.CONFIRMING and self.hovered is self.target:
            # Повторный клик по уже выбранному зданию — подтверждение
            self.confirm()
            return
        # «is» — это то же самое здание (а не просто такое же)
        self.target = self.hovered
        self.state = DemolishState.CONFIRMING

    def confirm(self) -> Building | None:
        """«Снести»: убираем здание с карты. Возвращает снесённое здание."""
        if self.state != DemolishState.CONFIRMING or self.target is None:
            return None
        building = self.target
        self.grid.remove(building)
        self.economy.refund(building.item)  # возвращаем часть цены (DEMOLISH_REFUND)
        self.target = None
        self.hovered = None
        self.state = DemolishState.SELECTING  # можно сносить дальше
        return building

    def reject(self) -> None:
        """«Отмена»: здание остаётся, режим сноса — тоже."""
        if self.state == DemolishState.CONFIRMING:
            self.target = None
            self.state = DemolishState.SELECTING

    def back(self) -> None:
        """Esc / правая кнопка: шаг назад."""
        if self.state == DemolishState.CONFIRMING:
            self.reject()
        else:
            self.cancel()

    # --- Каждый кадр ---

    def update_hover(self, tile: Tile | None) -> None:
        if not self.active:
            return
        self.hovered_tile = tile
        # У большого здания каждая его клетка ссылается на само здание,
        # поэтому навести можно на любую часть
        self.hovered = tile.building if tile else None

    # --- Ввод ---

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.back()
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.confirm()
                return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == LEFT_BUTTON:
                self.choose()
                return True
            if event.button == RIGHT_BUTTON:
                self.back()
                return True

        return False
