"""Машины на дорогах — «оживление» города, как и человечки.

Каждая машина едет по дорогам от клетки к клетке к случайной цели, а доехав,
выбирает новую. Путь ищется тем же поиском в ширину, что и у человечков
(Grid.find_road_path). Машина держится правой полосы: смещена от центра дороги
вправо по ходу движения, — поэтому встречные разъезжаются.

Число машин зависит от длины дорог и населения: на пустых дорогах нового
города машин мало, в большом городе — оживлённое движение.

На экономику машины не влияют, но ПОКАЗЫВАЮТ её: по забитым дорогам (см. economy/traffic.py)
едут медленнее, а у светофоров останавливаются на красный.
"""

import random
from dataclasses import dataclass, field

from city_builder.config import CAR_COLORS, CAR_SPEED, MAX_CARS, ROAD_TILES_PER_CAR, SIGNAL_CYCLE
from city_builder.economy.economy import Economy
from city_builder.world.grid import Grid

LANE_OFFSET = 0.2   # насколько клетки машина сдвинута вправо от центра дороги
MAX_TRIP = 40       # самая дальняя поездка (в клетках) — чтобы путь искался быстро
STOP_LINE = 0.7     # у красного света машина ждёт, проехав 70% клетки перед перекрёстком


def signal_state(time: float, x: int, y: int) -> str:
    """Какой свет у светофора на перекрёстке (x, y) в момент time.

    Возвращает "x" — зелёный едущим вдоль оси x, "y" — вдоль оси y, "yellow" — жёлтый всем.
    Цикл: 45% времени зелёный по x, 5% жёлтый, 45% зелёный по y, 5% жёлтый.
    Сдвиг (x + y) — чтобы соседние светофоры переключались не одновременно.
    """
    t = (time + (x + y) * 0.7) % SIGNAL_CYCLE / SIGNAL_CYCLE
    if t < 0.45:
        return "x"
    if t < 0.5 or t >= 0.95:
        return "yellow"
    return "y"


@dataclass(eq=False)
class Car:
    color: int                                    # номер цвета в CAR_COLORS
    path: list[tuple[int, int]] = field(default_factory=list)
    step: int = 0           # индекс клетки, из которой едет
    progress: float = 0.0   # 0..1 — сколько проехано до следующей клетки
    x: float = 0.0          # положение на карте (дробные клетки)
    y: float = 0.0
    along: str = "x"        # вдоль какой оси сейчас едет — для картинки

    @property
    def tile(self) -> tuple[int, int]:
        return self.path[self.step]


class TrafficManager:
    def __init__(self, grid: Grid, economy: Economy, seed: int | None = None) -> None:
        self.grid = grid
        self.economy = economy
        self.cars: list[Car] = []
        self.rng = random.Random(seed)
        self._version = -1
        self._roads: list[tuple[int, int]] = []
        self.time = 0.0  # игровое время — по нему переключаются светофоры

    def _target_count(self) -> int:
        by_roads = len(self._roads) // ROAD_TILES_PER_CAR
        by_people = 2 + self.economy.population // 12
        return min(MAX_CARS, by_roads, by_people)

    def update(self, dt: float) -> None:
        """dt — игровое время (0 на паузе)."""
        if self._version != self.grid.version:
            self._version = self.grid.version
            self._roads = [(b.x, b.y) for b in self.grid.buildings if self.grid.is_road(b.x, b.y)]
            # Дорогу под машиной снесли — убираем машину, остальным пересчитаем путь
            self.cars = [c for c in self.cars if self.grid.is_road(*c.tile)]
            for car in self.cars:
                if not all(self.grid.is_road(*t) for t in car.path[car.step:]):
                    self._new_trip(car, car.tile)

        target = self._target_count()
        while len(self.cars) > target:
            self.cars.pop()
        while len(self.cars) < target:
            car = Car(color=self.rng.randrange(len(CAR_COLORS)))
            if not self._new_trip(car, self.rng.choice(self._roads)):
                break
            car.progress = self.rng.random()  # чтобы не стояли «строем»
            self.cars.append(car)

        if dt > 0:
            self.time += dt
            for car in self.cars:
                self._drive(car, dt)

    def _new_trip(self, car: Car, start: tuple[int, int]) -> bool:
        """Новая поездка из start к случайной клетке дороги неподалёку."""
        sx, sy = start
        nearby = [r for r in self._roads if abs(r[0] - sx) + abs(r[1] - sy) <= MAX_TRIP and r != start]
        if not nearby:
            car.path, car.step, car.progress = [start, start], 0, 0.0
            return True  # стоит на месте (одна клетка дороги)
        goal = self.rng.choice(nearby)
        path = self.grid.find_road_path(start, {goal})
        if not path or len(path) < 2:
            car.path, car.step, car.progress = [start, start], 0, 0.0
            return True
        car.path, car.step, car.progress = path, 0, 0.0
        return True

    def _drive(self, car: Car, dt: float) -> None:
        # Пробка: чем сильнее загружена клетка, тем медленнее едем (вдвое больше машин — вдвое медленнее)
        ratio = self.economy.traffic.ratio.get(car.path[car.step], 0.0)
        car.progress += CAR_SPEED / max(1.0, ratio) * dt
        # Красный свет на следующей клетке — ждём у стоп-линии
        if car.step + 1 < len(car.path) and car.progress > STOP_LINE:
            nx, ny = car.path[car.step + 1]
            tile = self.grid.get(nx, ny)
            if tile is not None and tile.signal is not None:
                ax, ay = car.path[car.step]
                axis = "x" if nx != ax else "y"
                if signal_state(self.time, nx, ny) != axis:
                    car.progress = STOP_LINE
        while car.progress >= 1.0:
            car.progress -= 1.0
            car.step += 1
            if car.step >= len(car.path) - 1:
                self._new_trip(car, car.path[-1])
        (ax, ay), (bx, by) = car.path[car.step], car.path[min(car.step + 1, len(car.path) - 1)]
        dx, dy = bx - ax, by - ay
        if dx or dy:
            car.along = "x" if dx else "y"
        t = car.progress
        # Правая полоса: вектор движения, повёрнутый на 90°, — (−dy, dx)
        car.x = ax + dx * t + 0.5 - dy * LANE_OFFSET
        car.y = ay + dy * t + 0.5 + dx * LANE_OFFSET
