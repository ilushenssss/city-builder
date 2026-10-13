"""Электросети и водопровод.

ЭЛЕКТРИЧЕСТВО
-------------
Ток идёт по ЛИНИЯМ ЭЛЕКТРОПЕРЕДАЧ (их тянут мышью) и ЧЕРЕЗ ЗДАНИЯ, стоящие вплотную:
    станция ═══ линия ═══ дом|дом|дом      ← дома вплотную передают ток друг другу
Всё, что так связано, — одна ЭЛЕКТРОСЕТЬ. У каждой сети свой баланс:
  1. Складываем выработку станций сети (power_output). Станция должна работать
     (у дороги — нужны работники) и касаться линии или здания сети.
  2. Раздаём энергию зданиям сети в порядке постройки, пока хватает.
  3. Кому не хватило — сидят без света и НЕ работают («гаснут» последние).
Дороги ток не проводят (но линию можно тянуть над дорогой).

ВОДА
----
Вода идёт по ВОДОПРОВОДУ — подземным трубам (их тоже тянут мышью, хоть под зданиями).
Связанные трубы — одна водопроводная сеть. Сеть снабжает здания, у которых хоть одна
клетка не дальше PIPE_RADIUS (2) клеток от трубы. Водокачка подключена, если её
клетки касаются трубы (или труба проходит под ней). Водокачке нужен свет — сначала
считаем электричество, потом воду.

Алгоритм «кто с кем связан» — система непересекающихся множеств (union-find):
каждый узел сначала сам по себе; соединяя соседей, сливаем их множества.
В конце узлы с одинаковым «корнем» — одна сеть.
"""

from collections import deque
from dataclasses import dataclass

from city_builder.config import PIPE_RADIUS, ROAD_CATEGORIES
from city_builder.world.building import Building
from city_builder.world.grid import Grid


@dataclass
class Network:
    """Одна электросеть или водопроводная сеть и её баланс."""
    id: int
    supply: int = 0   # сколько вырабатывается
    demand: int = 0   # сколько хотят потребить все здания сети
    used: int = 0     # сколько реально раздали

    @property
    def spare(self) -> int:
        """Свободный запас — хватит ли ещё на одно здание."""
        return self.supply - self.used


class UnionFind:
    """Система непересекающихся множеств: find(a) — «корень» множества a, union(a, b) — слить."""

    def __init__(self) -> None:
        self.parent: dict = {}

    def find(self, a):
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]  # «сжатие пути» — ускоряет следующие поиски
            a = self.parent[a]
        return a

    def union(self, a, b) -> None:
        self.parent[self.find(a)] = self.find(b)


def is_structure(b: Building) -> bool:
    """Здания, которые участвуют в сетях (дороги — нет)."""
    return b.item.category not in ROAD_CATEGORIES


class Infrastructure:
    def __init__(self, grid: Grid) -> None:
        self.grid = grid
        self.power: dict[int, Network] = {}
        self.water: dict[int, Network] = {}
        self._power_of_tile: dict[tuple[int, int], int] = {}   # клетка линии/здания -> сеть
        self._water_cover: dict[tuple[int, int], list[int]] = {}  # клетка -> водопроводные сети рядом

    def recompute(self) -> None:
        """Пересчитать сети, свет и воду. Вызывается после постройки/сноса."""
        buildings = [b for b in self.grid.buildings if is_structure(b)]
        for b in self.grid.buildings:
            b.powered = b.watered = True  # дорогам ничего не нужно
            b.power_net = b.water_net = None
        self._compute_power(buildings)
        self._compute_water(buildings)

    # --- Электричество ---

    def _compute_power(self, buildings: list[Building]) -> None:
        grid = self.grid
        uf = UnionFind()
        lines = {(t.x, t.y) for t in grid if t.power_line is not None}
        for x, y in lines:  # линия соединяется с соседними линиями
            uf.find(("L", x, y))
            for nxt in ((x + 1, y), (x, y + 1)):
                if nxt in lines:
                    uf.union(("L", x, y), ("L", *nxt))
        owner = {}  # клетка -> здание на ней
        for b in buildings:
            for cell in b.footprint():
                owner[cell] = b
        for b in buildings:  # здание соединяется с линиями и зданиями вплотную
            node = ("B", id(b))
            uf.find(node)
            for cell in grid._around(b.x, b.y, b.width, b.height):
                if cell in lines:
                    uf.union(node, ("L", *cell))
                elif cell in owner and owner[cell] is not b:
                    uf.union(node, ("B", id(owner[cell])))

        # Корни -> номера сетей 0, 1, 2...
        ids: dict = {}
        self.power = {}
        self._power_of_tile = {}

        def net_of(node) -> int:
            root = uf.find(node)
            if root not in ids:
                ids[root] = len(ids)
                self.power[ids[root]] = Network(ids[root])
            return ids[root]

        for x, y in lines:
            self._power_of_tile[(x, y)] = net_of(("L", x, y))
        for b in buildings:
            b.power_net = net_of(("B", id(b)))
            for cell in b.footprint():
                self._power_of_tile[cell] = b.power_net

        # Выработка: станция работает, если у дороги (ей нужны работники)
        for b in buildings:
            if b.item.power_output and (b.connected or not b.item.needs_road):
                self.power[b.power_net].supply += b.item.power_output
        # Раздача в порядке постройки (старые здания — первыми)
        for b in buildings:
            b.powered = self._give(self.power, b.power_net, b.item.power_use)

    # --- Вода ---

    def _compute_water(self, buildings: list[Building]) -> None:
        grid = self.grid
        pipes = {(t.x, t.y) for t in grid if t.pipe is not None}
        # Сети труб — заливкой (поиск в ширину) по соседним трубам
        self.water = {}
        net_of_pipe: dict[tuple[int, int], int] = {}
        for start in sorted(pipes):
            if start in net_of_pipe:
                continue
            net = len(self.water)
            self.water[net] = Network(net)
            net_of_pipe[start] = net
            queue = deque([start])
            while queue:
                x, y = queue.popleft()
                for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nxt in pipes and nxt not in net_of_pipe:
                        net_of_pipe[nxt] = net
                        queue.append(nxt)
        # Зона покрытия: клетки в радиусе PIPE_RADIUS от трубы
        self._water_cover = {}
        r = PIPE_RADIUS
        for (x, y), net in net_of_pipe.items():
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    nets = self._water_cover.setdefault((x + dx, y + dy), [])
                    if net not in nets:
                        nets.append(net)

        # Водокачки: касаются трубы (или труба под ними), работают и есть свет
        for b in buildings:
            if not b.item.water_output or not b.powered or not (b.connected or not b.item.needs_road):
                continue
            cells = list(b.footprint()) + grid._around(b.x, b.y, b.width, b.height)
            nets = {net_of_pipe[c] for c in cells if c in net_of_pipe}
            for net in nets:  # одна водокачка может питать несколько сетей — делим поровну
                self.water[net].supply += b.item.water_output // len(nets)

        # Раздача: здание берёт воду из той сети рядом, где больше всего запас
        for b in buildings:
            nets = self.water_nets_near(b.x, b.y, b.width, b.height)
            best = max(nets, key=lambda n: n.spare) if nets else None
            b.water_net = best.id if best else None
            b.watered = self._give(self.water, b.water_net, b.item.water_use)

    @staticmethod
    def _give(networks: dict[int, Network], net_id: int | None, amount: int) -> bool:
        """Выдать зданию amount из сети. True — хватило (или зданию это не нужно)."""
        if amount == 0:
            return True
        if net_id is None:
            return False
        net = networks[net_id]
        net.demand += amount
        if net.spare >= amount:
            net.used += amount
            return True
        return False

    # --- Для подсказок при строительстве ---

    def power_nets_near(self, x: int, y: int, width: int, height: int) -> list[Network]:
        """Электросети, к которым подключится здание в этом месте (касается линии или здания)."""
        ids = {self._power_of_tile[c] for c in self.grid._around(x, y, width, height) if c in self._power_of_tile}
        return [self.power[i] for i in sorted(ids)]

    def water_nets_near(self, x: int, y: int, width: int, height: int) -> list[Network]:
        """Водопроводные сети, в зону которых попадает область."""
        ids: set[int] = set()
        for ty in range(y, y + height):
            for tx in range(x, x + width):
                ids.update(self._water_cover.get((tx, ty), []))
        return [self.water[i] for i in sorted(ids)]

    def is_watered_tile(self, x: int, y: int) -> bool:
        """Покрыта ли клетка водопроводом (для режима просмотра «Вода»)."""
        return (x, y) in self._water_cover

    # --- Итоги по городу (для панели) ---

    def totals(self) -> tuple[Network, Network]:
        """(электричество, вода) — суммы по всем сетям, для панели «Город»."""
        result = []
        for networks in (self.power, self.water):
            total = Network(-1)
            for net in networks.values():
                total.supply += net.supply
                total.demand += net.demand
                total.used += net.used
            result.append(total)
        return result[0], result[1]
