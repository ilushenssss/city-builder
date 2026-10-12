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
    # Есть ли рядом дорога. Пересчитывает экономика (Economy.refresh) после каждой
    # постройки и сноса. Без дороги здание не работает: нет жителей, работы и дохода.
    connected: bool = True

    @property
    def working(self) -> bool:
        """Работает ли здание: ему не нужна дорога, или дорога рядом есть."""
        return self.connected or not self.item.needs_road

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
