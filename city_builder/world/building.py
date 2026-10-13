"""Здание, построенное на карте."""

from collections.abc import Iterator
from dataclasses import dataclass, field

from city_builder.data.catalog import ShopItem


# eq=False: здания сравниваются как разные объекты («это то же самое здание?»),
# а не по значениям полей. Нужно, чтобы grid.buildings.remove(building)
# и проверка «building is target» работали именно с конкретным зданием.
@dataclass(eq=False)
class Building:
    item: ShopItem  # что построено: товар из каталога (название, размер, цвет...)
    x: int          # левая верхняя клетка здания
    y: int
    # Есть ли рядом дорога. Пересчитывает экономика (Economy.refresh) после каждой
    # постройки и сноса. Без дороги здание не работает: нет жителей, работы и дохода.
    connected: bool = True
    # Есть ли электричество и вода (если здание их потребляет). Считает economy/networks.py.
    powered: bool = True
    watered: bool = True
    # Насколько здание работает в последнем тике: 1.0 — полностью, 0.5 — наполовину
    # (не хватает работников или сырья). Считает Economy.tick.
    efficiency: float = 1.0
    # Счастье жителей дома (0–100), только для жилых зданий. Считает economy/happiness.py.
    happiness: float = 0.0
    # Список проблем для значка и подсказки: "road", "power", "water", "inputs"
    problems: list[str] = field(default_factory=list)

    @property
    def working(self) -> bool:
        """Работает ли здание вообще: есть дорога (если нужна), электричество и вода.
        Нехватка работников или сырья не «выключает» здание, а снижает efficiency."""
        has_road = self.connected or not self.item.needs_road
        return has_road and self.powered and self.watered

    @property
    def width(self) -> int:
        return self.item.size[0]

    @property
    def height(self) -> int:
        return self.item.size[1]

    def footprint(self) -> Iterator[tuple[int, int]]:
        """Все клетки, которые занимает здание. Для здания 2×2 в (5, 7):
        (5, 7), (6, 7), (5, 8), (6, 8)."""
        for ty in range(self.y, self.y + self.height):
            for tx in range(self.x, self.x + self.width):
                yield tx, ty
