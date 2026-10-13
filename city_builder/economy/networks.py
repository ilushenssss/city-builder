"""Районы, электричество и вода.

РАЙОН — это связная дорожная сеть: все клетки дороги, по которым можно доехать
друг до друга. Здание относится к району той дороги, у которой стоит.
Если в городе две несвязанные сети дорог — это два района, и у каждого
своё электричество и своя вода (по дорогам «идут провода и трубы»).

    ═══════╗          ╔═══     ← два района: левый и правый
     дома  ║  трава   ║ завод    электростанция левого района
    ═══════╝          ╚═══     не питает завод в правом

Как распределяется электричество в районе:
  1. Складываем выработку всех электростанций района (power_output).
  2. Идём по зданиям в порядке постройки и раздаём им power_use, пока хватает.
  3. Кому не хватило — сидят без света и НЕ работают.
  Получается, что при нехватке «гаснут» здания, построенные последними.

С водой — так же, но водокачке самой нужно электричество: обесточенная
водонапорная башня воду не даёт. Поэтому сначала считаем свет, потом воду.
"""

from collections import deque
from dataclasses import dataclass

from city_builder.world.building import Building
from city_builder.world.grid import Grid


@dataclass
class District:
    """Один район (дорожная сеть) и его баланс энергии и воды."""
    id: int
    power_supply: int = 0   # сколько электричества вырабатывается
    power_demand: int = 0   # сколько хотят потребить все здания района
    power_used: int = 0     # сколько реально раздали
    water_supply: int = 0
    water_demand: int = 0
    water_used: int = 0

    @property
    def power_spare(self) -> int:
        """Свободное электричество — хватит ли на ещё одно здание."""
        return self.power_supply - self.power_used

    @property
    def water_spare(self) -> int:
        return self.water_supply - self.water_used


class Infrastructure:
    def __init__(self, grid: Grid) -> None:
        self.grid = grid
        self.road_district: dict[tuple[int, int], int] = {}  # клетка дороги -> номер района
        self.districts: dict[int, District] = {}

    def recompute(self) -> None:
        """Пересчитать районы, свет и воду. Вызывается после постройки/сноса."""
        self._label_districts()
        buildings = self.grid.buildings
        district_of = {b: self.district_of(b) for b in buildings}

        # --- Электричество ---
        for b in buildings:
            if b.item.power_output and b.connected and district_of[b] is not None:
                self.districts[district_of[b]].power_supply += b.item.power_output
        for b in buildings:  # в порядке постройки: старые здания получают свет первыми
            b.powered = self._give(b.item.power_use, district_of[b], "power")

        # --- Вода (водокачкам нужно электричество, поэтому — после света) ---
        for b in buildings:
            if b.item.water_output and b.connected and b.powered and district_of[b] is not None:
                self.districts[district_of[b]].water_supply += b.item.water_output
        for b in buildings:
            b.watered = self._give(b.item.water_use, district_of[b], "water")

    def _give(self, amount: int, district_id: int | None, kind: str) -> bool:
        """Выдать зданию amount энергии или воды из его района. True — хватило."""
        if amount == 0:
            return True  # зданию это не нужно
        if district_id is None:
            return False  # здание не у дороги — не подключено ни к какому району
        district = self.districts[district_id]
        setattr(district, f"{kind}_demand", getattr(district, f"{kind}_demand") + amount)
        used = getattr(district, f"{kind}_used")
        if getattr(district, f"{kind}_supply") - used >= amount:
            setattr(district, f"{kind}_used", used + amount)
            return True
        return False

    # --- Районы ---

    def _label_districts(self) -> None:
        """Разметить клетки дорог номерами районов (поиск в ширину от каждой
        ещё не размеченной клетки дороги — получается «заливка» сети)."""
        self.road_district = {}
        self.districts = {}
        roads = {(b.x, b.y) for b in self.grid.buildings if self.grid.is_road(b.x, b.y)}
        next_id = 0
        for start in sorted(roads):  # sorted — чтобы номера районов не скакали
            if start in self.road_district:
                continue
            self.districts[next_id] = District(next_id)
            self.road_district[start] = next_id
            queue = deque([start])
            while queue:
                x, y = queue.popleft()
                for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nxt in roads and nxt not in self.road_district:
                        self.road_district[nxt] = next_id
                        queue.append(nxt)
            next_id += 1

    def districts_near(self, x: int, y: int, width: int, height: int) -> list[District]:
        """Районы, к дорогам которых примыкает область (обычно один)."""
        ids = set()
        for tx, ty in self.grid._around(x, y, width, height):
            if (tx, ty) in self.road_district:
                ids.add(self.road_district[(tx, ty)])
        return [self.districts[i] for i in sorted(ids)]

    def district_of(self, building: Building) -> int | None:
        """Номер района здания (если примыкает к нескольким — берём первый)."""
        near = self.districts_near(building.x, building.y, building.width, building.height)
        return near[0].id if near else None

    # --- Итоги по городу (для панели) ---

    def totals(self) -> District:
        """Сумма по всем районам — для панели «Город»."""
        total = District(-1)
        for d in self.districts.values():
            total.power_supply += d.power_supply
            total.power_demand += d.power_demand
            total.power_used += d.power_used
            total.water_supply += d.water_supply
            total.water_demand += d.water_demand
            total.water_used += d.water_used
        return total
