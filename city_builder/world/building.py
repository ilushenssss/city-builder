"""Здание, построенное на карте."""

from collections.abc import Iterator
from dataclasses import dataclass

from city_builder.data.catalog import ShopItem


# eq=False: здания сравниваются как разные объекты («это то же самое здание?»),
# а не по значениям полей. Нужно, чтобы grid.buildings.remove(building)
# и проверка «building is target» работали именно с конкретным зданием.
@dataclass(eq=False)
class Building:
    item: ShopItem  # что построено: товар из каталога (название, размер, цвет...)
    x: int          # левая верхняя клетка здания
    y: int
    # На этапе 2 сюда добавится состояние: работает ли, сколько жителей и т.п.

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
