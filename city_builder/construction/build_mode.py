"""Режим строительства — логика без отрисовки.

Режим — это «конечный автомат» из четырёх состояний:

    IDLE ──(выбрали товар)──> PLACING ──(клик)──────────────────> CONFIRMING
     ^                         │  │                                │  │
     │                         │  └─(дорога: зажали кнопку)─> DRAGGING ─(отпустили)─┘  │
     └──(Esc / правая кнопка)──┘                                   │                    │
                               ^──────(Отмена / Esc)───────────────┘                    │
                               ^──────(Построить / Enter: здания поставлены)────────────┘

  IDLE       — ничего не строим, клики по карте ничего не делают.
  PLACING    — товар выбран, «призрак» здания ходит за курсором.
  DRAGGING   — только для дорог: кнопка мыши зажата, тянем дорогу от клетки к клетке.
  CONFIRMING — место (или участок дороги) выбрано, ждём «Построить» или «Отмена».

Дорогу протягивают буквой «Г»: сначала вдоль той оси, по которой тянули дальше,
потом поворот. Клетки, где дорога уже есть, пропускаются (бесплатно),
клетки, где строить нельзя (вода, дом), — тоже пропускаются и подсвечиваются красным.

После постройки режим возвращается в PLACING с тем же товаром:
удобно ставить несколько домов или участков дороги подряд.

Здесь нет pygame-отрисовки: как всё это выглядит, решают Renderer
(призрак на карте) и BuildPanel (панель внизу экрана).
"""

from enum import Enum, auto

import pygame

from city_builder.config import ROAD_CATEGORIES
from city_builder.data.catalog import ShopItem
from city_builder.economy.economy import Economy
from city_builder.world.building import Building
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile

LEFT_BUTTON = 1
RIGHT_BUTTON = 3

Site = tuple[int, int]  # клетка (x, y): левый верхний угол здания


class BuildState(Enum):
    # auto() сам раздаёт значения 1, 2, 3, 4 — нам важны только имена
    IDLE = auto()
    PLACING = auto()
    DRAGGING = auto()
    CONFIRMING = auto()


def l_shaped_path(start: Site, end: Site) -> list[Site]:
    """Клетки дороги буквой «Г» от start до end.

    Сначала идём вдоль оси, по которой расстояние больше, потом поворачиваем:
        start ■■■■■■■
                    ■
                    ■ end
    """
    (sx, sy), (ex, ey) = start, end
    step_x = 1 if ex >= sx else -1
    step_y = 1 if ey >= sy else -1
    xs = list(range(sx, ex + step_x, step_x))  # все x от sx до ex включительно
    ys = list(range(sy, ey + step_y, step_y))
    if abs(ex - sx) >= abs(ey - sy):
        # Сначала по x (на строке sy), потом по y (в столбце ex)
        return [(x, sy) for x in xs] + [(ex, y) for y in ys[1:]]
    # Сначала по y (в столбце sx), потом по x (на строке ey)
    return [(sx, y) for y in ys] + [(x, ey) for x in xs[1:]]


class BuildMode:
    def __init__(self, grid: Grid, economy: Economy) -> None:
        self.grid = grid
        self.economy = economy  # чтобы проверять и списывать деньги
        self.state = BuildState.IDLE
        self.item: ShopItem | None = None  # что строим

        # Куда встанет здание, если кликнуть прямо сейчас (левая верхняя клетка),
        # и почему туда нельзя (None — можно). Обновляется каждый кадр.
        self.cursor_pos: Site | None = None
        self.cursor_error: str | None = None
        # Предупреждение: строить можно, но что-то не так (например, нет дороги)
        self.cursor_warning: str | None = None

        # Протягивание дороги (DRAGGING): откуда тянем и что получилось
        self.drag_start: Site | None = None
        self.drag_ok: list[Site] = []       # здесь построим
        self.drag_skip: list[Site] = []     # здесь уже есть дорога — пропустим
        self.drag_bad: list[Site] = []      # здесь строить нельзя — пропустим
        self._targets_before_drag: list[Site] = []

        # Что ждёт подтверждения (CONFIRMING): одно место здания или клетки дороги
        self.targets: list[Site] = []

    # --- Свойства ---

    @property
    def active(self) -> bool:
        """Идёт ли сейчас строительство (выбран товар)."""
        return self.state != BuildState.IDLE

    @property
    def draggable(self) -> bool:
        """Можно ли товар протягивать мышью (дороги — да, здания — нет)."""
        return self.item is not None and self.item.category in ROAD_CATEGORIES

    @property
    def total_price(self) -> int:
        """Сколько стоит всё, что ждёт подтверждения (или что сейчас тянем)."""
        if self.item is None:
            return 0
        count = len(self.drag_ok) if self.state == BuildState.DRAGGING else len(self.targets)
        return count * self.item.price

    @property
    def confirm_error(self) -> str | None:
        """Почему нельзя подтвердить (не хватает денег) или None."""
        if self.state in (BuildState.CONFIRMING, BuildState.DRAGGING) and \
                not self.economy.can_afford(self.total_price):
            return f"Не хватает денег: нужно {self.total_price}, есть {self.economy.money}"
        return None

    @property
    def target_warning(self) -> str | None:
        """Предупреждение для выбранного места здания (в подтверждении)."""
        if self.item is None or len(self.targets) != 1 or self.draggable:
            return None
        return self.site_warning(*self.targets[0])  # * раскладывает (x, y) на два аргумента

    # --- Проверки места ---

    def site_error(self, x: int, y: int) -> str | None:
        """Почему здесь нельзя строить одно здание (None — можно): место или деньги."""
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
        # Дорога есть — хватит ли в этом районе электричества и воды?
        return self.economy.site_warning(self.item, x, y)

    # --- Переходы между состояниями ---

    def select(self, item: ShopItem) -> None:
        """Игрок выбрал товар в магазине -> начинаем выбирать место."""
        self.cancel()
        self.item = item
        self.state = BuildState.PLACING

    def cancel(self) -> None:
        """Полностью выйти из режима строительства."""
        self.state = BuildState.IDLE
        self.item = None
        self.cursor_pos = None
        self.cursor_error = None
        self.cursor_warning = None
        self.targets = []
        self._clear_drag()

    def _clear_drag(self) -> None:
        self.drag_start = None
        self.drag_ok, self.drag_skip, self.drag_bad = [], [], []

    def choose_site(self) -> None:
        """Клик по карте (обычное здание): зафиксировать место под курсором."""
        if self.cursor_pos is None or self.cursor_error is not None:
            return  # курсор вне карты или место плохое — ничего не делаем
        if self.state == BuildState.CONFIRMING and self.targets == [self.cursor_pos]:
            # Повторный клик по уже выбранному месту — считаем это подтверждением
            self.confirm()
            return
        # В PLACING — выбираем место; в CONFIRMING — переносим выбор на новое место
        self.targets = [self.cursor_pos]
        self.state = BuildState.CONFIRMING

    def start_drag(self) -> None:
        """Зажали кнопку мыши на карте (дорога): начинаем тянуть."""
        if self.cursor_pos is None:
            return
        self._targets_before_drag = self.targets
        self.drag_start = self.cursor_pos
        self.state = BuildState.DRAGGING
        self._update_drag(self.cursor_pos)

    def finish_drag(self) -> None:
        """Отпустили кнопку мыши: участок дороги выбран, ждём подтверждения."""
        if self.state != BuildState.DRAGGING:
            return
        tiles = self.drag_ok
        self._clear_drag()
        if not tiles:
            self.targets = []
            self.state = BuildState.PLACING  # строить нечего (всё занято или уже дорога)
            return
        self.targets = tiles
        self.state = BuildState.CONFIRMING
        if tiles == self._targets_before_drag:
            self.confirm()  # тот же участок второй раз — как двойной клик: подтверждаем

    def confirm(self) -> list[Building]:
        """«Построить»: ставим здания на карту. Возвращает список построенного."""
        if self.state != BuildState.CONFIRMING or not self.targets or self.item is None:
            return []
        # Проверяем ещё раз: пока игрок думал, место могло стать недоступным
        valid = [site for site in self.targets if self.grid.placement_error(self.item, *site) is None]
        if not valid:
            self.reject()
            return []
        cost = len(valid) * self.item.price
        if not self.economy.spend(cost):
            return []  # денег не хватает — ждём (панель покажет ошибку)
        built = [self.grid.place(self.item, *site) for site in valid]
        self.targets = []
        self.state = BuildState.PLACING  # тот же товар — можно строить дальше
        return built

    def reject(self) -> None:
        """«Отмена» в подтверждении: выбор сбрасывается, товар остаётся выбранным."""
        if self.state in (BuildState.CONFIRMING, BuildState.DRAGGING):
            self.targets = []
            self._clear_drag()
            self.state = BuildState.PLACING

    def back(self) -> None:
        """Esc / правая кнопка: шаг назад по цепочке состояний."""
        if self.state in (BuildState.CONFIRMING, BuildState.DRAGGING):
            self.reject()  # обратно к выбору места
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

        if self.state == BuildState.DRAGGING:
            self._update_drag(self.cursor_pos)
            self.cursor_error = self.confirm_error
            self.cursor_warning = None
            return

        self.cursor_error = self.site_error(x, y)
        # Предупреждение имеет смысл, только если строить вообще можно
        self.cursor_warning = None if self.cursor_error else self.site_warning(x, y)

    def _update_drag(self, end: Site) -> None:
        """Разложить клетки от drag_start до end на «построим / уже дорога / нельзя»."""
        assert self.item is not None and self.drag_start is not None
        self.drag_ok, self.drag_skip, self.drag_bad = [], [], []
        for site in l_shaped_path(self.drag_start, end):
            tile = self.grid.get(*site)
            if tile is not None and tile.building is not None \
                    and tile.building.item.category in ROAD_CATEGORIES:
                self.drag_skip.append(site)
            elif self.grid.placement_error(self.item, *site) is None:
                self.drag_ok.append(site)
            else:
                self.drag_bad.append(site)

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
                if self.draggable:
                    self.start_drag()   # дорога: начинаем протягивать
                else:
                    self.choose_site()  # здание: выбираем место
                return True
            if event.button == RIGHT_BUTTON:
                self.back()
                return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == LEFT_BUTTON \
                and self.state == BuildState.DRAGGING:
            self.finish_drag()
            return True

        return False
