"""Жители, бегающие по делам.

Это «оживление» города: человечки на экране не влияют на экономику, но показывают,
что город живёт. Их число зависит от населения: один человечек на
RESIDENTS_PER_WALKER жителей, но не больше MAX_WALKERS.

Жизненный цикл человечка (простой конечный автомат):

    INSIDE (дома) ──(подождал)──> WALKING (идёт по дороге) ──(дошёл)──> INSIDE (на месте)
        ^                                                                    │
        └─────────────────────(подождал, идёт обратно домой)─────────────────┘

Куда идёт из дома:
  * на работу — в здание с рабочими местами (с вероятностью WORK_CHANCE);
  * иначе по делам — в магазин, парк, школу, больницу (категории ERRAND_CATEGORIES).
Путь ищется только по дорогам (Grid.find_road_path). Нет пути — сидит дома и
пробует снова позже.

Человечек идёт по центрам клеток дороги, чуть смещаясь вправо по ходу движения,
чтобы встречные не шли друг сквозь друга.

Время — игровое: на паузе все стоят, на скорости ×3 бегут втрое быстрее.
"""

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto

from city_builder.config import (
    ERRAND_CATEGORIES,
    MAX_WALKERS,
    RESIDENTS_PER_WALKER,
    WALKER_COLORS,
    WALKER_SPEED,
    WORK_CHANCE,
)
from city_builder.economy.economy import Economy
from city_builder.world.building import Building
from city_builder.world.grid import Grid

SIDE_OFFSET = 0.17  # насколько клетки сдвинуться вправо по ходу движения


class WalkerState(Enum):
    INSIDE = auto()   # внутри здания (не виден)
    WALKING = auto()  # идёт по дороге


@dataclass(eq=False)
class Walker:
    home: Building
    color: tuple[int, int, int]
    state: WalkerState = WalkerState.INSIDE
    location: Building | None = None       # где сейчас находится (внутри какого здания)
    destination: Building | None = None    # куда идёт
    path: list[tuple[int, int]] = field(default_factory=list)  # клетки дороги
    step: int = 0           # индекс клетки пути, ИЗ которой сейчас идёт
    progress: float = 0.0   # от 0 до 1 — сколько пройдено до следующей клетки
    wait: float = 0.0       # сколько секунд ещё сидеть внутри
    x: float = 0.0          # положение на карте в дробных клетках (центр клетки = +0.5)
    y: float = 0.0

    @property
    def visible(self) -> bool:
        return self.state == WalkerState.WALKING


class CitizenManager:
    def __init__(self, grid: Grid, economy: Economy, seed: int | None = None) -> None:
        self.grid = grid
        self.economy = economy
        self.walkers: list[Walker] = []
        self.rng = random.Random(seed)
        self._grid_version = -1

    # --- Каждый кадр ---

    def update(self, dt: float) -> None:
        """dt — игровое время в секундах (0 на паузе, ×2 и ×3 на ускорении)."""
        if self._grid_version != self.grid.version:
            self._grid_version = self.grid.version
            self._on_grid_changed()
        self._adjust_count()
        if dt <= 0:
            return
        for walker in self.walkers:
            if walker.state == WalkerState.INSIDE:
                walker.wait -= dt
                if walker.wait <= 0:
                    self._leave_building(walker)
            else:
                self._walk(walker, dt)

    # --- Сколько человечков ---

    def _target_count(self) -> int:
        return min(MAX_WALKERS, self.economy.population // RESIDENTS_PER_WALKER)

    def _adjust_count(self) -> None:
        """Добавить или убрать человечков под текущее население."""
        target = self._target_count()
        if len(self.walkers) > target:
            # Убираем в первую очередь тех, кто внутри зданий, — чтобы никто не исчез посреди улицы
            self.walkers.sort(key=lambda w: w.state == WalkerState.WALKING)
            del self.walkers[target:]
            return
        homes = [b for b in self.grid.buildings if b.item.housing > 0 and b.working]
        if not homes:
            return
        weights = [b.item.housing for b in homes]  # в большом доме больше жителей
        while len(self.walkers) < target:
            home = self.rng.choices(homes, weights)[0]  # случайный дом с учётом веса
            walker = Walker(home=home, color=self.rng.choice(WALKER_COLORS), location=home)
            walker.wait = self.rng.uniform(0, 6)  # выходят из домов не все сразу
            self.walkers.append(walker)

    # --- Карта изменилась (построили или снесли) ---

    def _on_grid_changed(self) -> None:
        alive = set(self.grid.buildings)
        kept = []
        for walker in self.walkers:
            if walker.home not in alive:
                continue  # дом снесли — житель уехал
            if walker.state == WalkerState.WALKING:
                # Снесли цель или кусок дороги впереди — «возвращаем» домой
                road_ok = all(self.grid.is_road(*tile) for tile in walker.path[walker.step:])
                if walker.destination not in alive or not road_ok:
                    self._enter(walker, walker.home)
            elif walker.location not in alive:
                self._enter(walker, walker.home)
            kept.append(walker)
        self.walkers = kept

    # --- Решения и движение ---

    def _choose_destination(self, walker: Walker) -> Building | None:
        """Куда пойти: из дома — на работу или по делам; из любого другого места — домой."""
        if walker.location is not walker.home:
            return walker.home
        buildings = [b for b in self.grid.buildings if b.working and b is not walker.home]
        jobs = [b for b in buildings if b.item.workers > 0]
        errands = [b for b in buildings if b.item.category in ERRAND_CATEGORIES]
        if jobs and (self.rng.random() < WORK_CHANCE or not errands):
            return self.rng.choice(jobs)
        return self.rng.choice(errands) if errands else None

    def _leave_building(self, walker: Walker) -> None:
        """Выйти из здания и пойти к следующей цели (если до неё есть дорога)."""
        location = walker.location or walker.home
        destination = self._choose_destination(walker)
        starts = self.grid.roads_around(location)
        goals = set(self.grid.roads_around(destination)) if destination else set()
        path = self.grid.find_road_path(self.rng.choice(starts), goals) if starts and goals else None
        if not path:
            walker.wait = self.rng.uniform(3, 8)  # идти некуда — посидим ещё и попробуем снова
            return
        if len(path) < 2:
            # Здания стоят у одной и той же клетки дороги — идти не нужно, сразу заходим
            self._enter(walker, destination)
            return
        walker.state = WalkerState.WALKING
        walker.destination = destination
        walker.path = path
        walker.step = 0
        walker.progress = 0.0
        walker.x, walker.y = path[0][0] + 0.5, path[0][1] + 0.5

    def _enter(self, walker: Walker, building: Building) -> None:
        """Зайти в здание и пробыть там какое-то время."""
        walker.state = WalkerState.INSIDE
        walker.location = building
        walker.destination = None
        walker.path = []
        at_home = building is walker.home
        walker.wait = self.rng.uniform(6, 14) if at_home else self.rng.uniform(4, 9)

    def _walk(self, walker: Walker, dt: float) -> None:
        """Продвинуть человечка по пути на WALKER_SPEED клеток в секунду."""
        walker.progress += WALKER_SPEED * dt
        while walker.progress >= 1.0:  # за один кадр можно пройти больше клетки (на ×3)
            walker.progress -= 1.0
            walker.step += 1
            if walker.step >= len(walker.path) - 1:
                assert walker.destination is not None
                self._enter(walker, walker.destination)
                return
        # Позиция между текущей и следующей клеткой
        (ax, ay), (bx, by) = walker.path[walker.step], walker.path[walker.step + 1]
        t = walker.progress
        dx, dy = bx - ax, by - ay
        # Сдвиг вправо по ходу движения: вектор (dx, dy), повёрнутый на 90° — (−dy, dx)
        side_x, side_y = -dy * SIDE_OFFSET, dx * SIDE_OFFSET
        walker.x = ax + dx * t + 0.5 + side_x
        walker.y = ay + dy * t + 0.5 + side_y

    # --- Для отрисовки ---

    def visible_walkers(self) -> list[Walker]:
        return [w for w in self.walkers if w.visible]

    @staticmethod
    def bob(walker: Walker) -> float:
        """Покачивание при ходьбе (0..1): человечек чуть подпрыгивает на каждом шаге."""
        return abs(math.sin(walker.progress * math.pi * 4))
