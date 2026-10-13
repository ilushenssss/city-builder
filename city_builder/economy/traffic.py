"""Пробки: сколько машин едет по каждой клетке дороги и хватает ли ей пропускной способности.

Как считаем
-----------
1. Для каждого дома ищем путь по дорогам до ближайшего места работы.
   Один «обратный» поиск в ширину от всех работ сразу даёт кратчайший путь
   от любой клетки дороги до ближайшей работы — не нужно искать для каждого дома отдельно.
   Пути пересчитываются только после постройки/сноса.

2. Каждый тик: жители дома (доля населения по размеру дома) × COMMUTE_SHARE
   выезжают на работу. Их число добавляется к НАГРУЗКЕ каждой клетки их пути.

3. ЗАГРУЖЕННОСТЬ клетки = нагрузка / пропускная способность.
   Пропускная способность — поле "capacity" дороги (грунтовка 30, асфальт 60,
   проспект 140). Перекрёсток без светофора пропускает вдвое меньше
   (INTERSECTION_CAPACITY) — машины уступают друг другу. Светофор это исправляет.

4. Пробка дома = самая загруженная клетка на его пути (1.0 — дорога заполнена,
   2.0 — машин вдвое больше, чем она пропускает).

Что дают пробки (см. Economy.tick)
----------------------------------
  * работники опаздывают: предприятия работают хуже (commute_factor);
  * жители домов в пробках менее счастливы (до −CONGESTION_HAPPINESS).
"""

from collections import deque

from city_builder.config import COMMUTE_SHARE, DEFAULT_ROAD_CAPACITY, INTERSECTION_CAPACITY
from city_builder.world.building import Building
from city_builder.world.grid import Grid

Tile = tuple[int, int]


class TrafficModel:
    def __init__(self, grid: Grid) -> None:
        self.grid = grid
        self.paths: dict[Building, list[Tile]] = {}  # дом -> путь до работы
        self.load: dict[Tile, float] = {}            # клетка дороги -> машин за тик
        self.ratio: dict[Tile, float] = {}           # клетка дороги -> загруженность
        self.commute_factor = 1.0   # насколько вовремя приезжают работники (0..1)
        self.average_ratio = 0.0    # средняя загруженность занятых дорог — для панели

    # --- Пути (после постройки/сноса) ---

    def recompute_paths(self) -> None:
        grid = self.grid
        jobs = [b for b in grid.buildings if b.item.workers and b.working]
        goals = {cell for b in jobs for cell in grid.roads_around(b)}
        # Обратный поиск в ширину от всех работ: next_step[клетка] — куда ехать дальше
        next_step: dict[Tile, Tile | None] = {g: None for g in goals}
        queue = deque(goals)
        while queue:
            x, y = queue.popleft()
            for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nxt not in next_step and grid.is_road(*nxt):
                    next_step[nxt] = (x, y)
                    queue.append(nxt)
        self.paths = {}
        for home in grid.buildings:
            if not home.item.housing or not home.working:
                continue
            starts = [c for c in grid.roads_around(home) if c in next_step]
            if not starts:
                continue
            path = [starts[0]]
            while next_step[path[-1]] is not None:
                path.append(next_step[path[-1]])  # type: ignore[arg-type]
            self.paths[home] = path

    # --- Каждый тик ---

    def capacity(self, cell: Tile) -> float:
        tile = self.grid.get(*cell)
        if tile is None or tile.building is None:
            return DEFAULT_ROAD_CAPACITY
        cap = tile.building.item.capacity or DEFAULT_ROAD_CAPACITY
        if tile.signal is None and self.grid.is_intersection(*cell):
            cap *= INTERSECTION_CAPACITY  # перекрёсток без светофора — бутылочное горлышко
        return cap

    def tick(self, population: int, housing: int) -> None:
        self.load = {}
        for home, path in self.paths.items():
            residents = population * home.item.housing / housing if housing else 0
            commuters = residents * COMMUTE_SHARE
            for cell in path:
                self.load[cell] = self.load.get(cell, 0.0) + commuters
        self.ratio = {cell: load / self.capacity(cell) for cell, load in self.load.items()}

        total, on_time = 0.0, 0.0
        for home in self.grid.buildings:
            path = self.paths.get(home)
            home.congestion = max((self.ratio.get(c, 0.0) for c in path), default=0.0) if path else 0.0
            if path:
                weight = home.item.housing
                total += weight
                # Загруженность 2.0 — дорога вдвое дольше, работник приезжает «наполовину»
                on_time += weight / max(1.0, home.congestion)
        self.commute_factor = on_time / total if total else 1.0
        self.average_ratio = sum(self.ratio.values()) / len(self.ratio) if self.ratio else 0.0
