"""Сетка карты — хранит все клетки мира.

Важно: здесь нет ничего про pygame и отрисовку. Это «чистые данные».
Благодаря этому карту легко сохранить в файл, проверить тестами
или нарисовать совсем по-другому (например, спрайтами вместо квадратов).
"""

import random
from collections.abc import Iterator

from city_builder.data.catalog import PLACEMENT_WATER, ShopItem
from city_builder.world.building import Building
from city_builder.world.tile import Tile, TileType


class Grid:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        # Двумерный список: список строк, каждая строка — список клеток.
        # Поэтому доступ к клетке — self.tiles[y][x] (сначала строка, потом столбец).
        # Изначально все клетки — трава.
        self.tiles = [[Tile(x, y) for x in range(width)] for y in range(height)]
        # Список всех зданий — удобно перебирать при отрисовке и (на этапе 2) в экономике
        self.buildings: list[Building] = []

    def in_bounds(self, x: int, y: int) -> bool:
        """Лежат ли координаты внутри карты."""
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> Tile | None:
        """Безопасно получить клетку: вернёт None, если координаты за картой.

        Используйте этот метод вместо прямого self.tiles[y][x], когда
        координаты могут быть «плохими» (например, курсор вне карты).
        Без проверки отрицательный индекс в Python не упадёт, а молча
        вернёт клетку с другого края — это коварная ошибка.
        """
        if not self.in_bounds(x, y):
            return None
        return self.tiles[y][x]

    # --- Строительство ---

    def placement_error(self, item: ShopItem, x: int, y: int) -> str | None:
        """Можно ли поставить товар item левым верхним углом в клетку (x, y).

        Возвращает None, если можно, или текст причины, если нельзя.
        Текст сразу показывается игроку, поэтому он на русском.
        """
        needs_water = item.placement == PLACEMENT_WATER
        width, height = item.size
        # Проверяем каждую клетку, которую займёт здание
        for ty in range(y, y + height):
            for tx in range(x, x + width):
                tile = self.get(tx, ty)
                if tile is None:
                    return "Здание выходит за край карты"
                if tile.building is not None:
                    return f"Место занято: {tile.building.item.name}"
                is_water = tile.type == TileType.WATER
                if needs_water and not is_water:
                    return f"{item.name}: строится только на воде"
                if not needs_water and is_water:
                    return "Нельзя строить на воде"
        return None

    def place(self, item: ShopItem, x: int, y: int) -> Building:
        """Поставить здание. Перед вызовом место нужно проверить через placement_error."""
        building = Building(item, x, y)
        for tx, ty in building.footprint():
            self.tiles[ty][tx].building = building
        self.buildings.append(building)
        return building

    def remove(self, building: Building) -> None:
        """Снести здание: освободить все его клетки и убрать из списка."""
        for tx, ty in building.footprint():
            self.tiles[ty][tx].building = None
        self.buildings.remove(building)

    def __iter__(self) -> Iterator[Tile]:
        """Позволяет перебирать все клетки одним циклом: for tile in grid: ..."""
        for row in self.tiles:
            yield from row  # отдаём по одной все клетки строки

    def generate(self, seed: int | None = None) -> None:
        """Простая генерация карты: одно озеро и одна извилистая река.

        seed — «зерно» случайности. Одинаковый seed даёт одинаковую карту
        (удобно для отладки). None — каждый раз новая карта.
        """
        # Отдельный генератор случайных чисел, чтобы не влиять
        # на глобальный random в остальной программе.
        rng = random.Random(seed)

        # --- Озеро: круг со случайным центром и радиусом ---
        # Центр берём из средней половины карты, чтобы озеро не ушло за край.
        cx = rng.randrange(self.width // 4, self.width * 3 // 4)
        cy = rng.randrange(self.height // 4, self.height * 3 // 4)
        radius = rng.randint(3, 5)
        for tile in self:
            # Уравнение круга: (x - cx)² + (y - cy)² <= r²
            if (tile.x - cx) ** 2 + (tile.y - cy) ** 2 <= radius ** 2:
                tile.type = TileType.WATER

        # --- Река: шириной 2 клетки, идёт сверху вниз ---
        x = rng.randrange(self.width)  # случайный столбец в верхней строке
        for y in range(self.height):
            # Делаем водой клетку x и соседнюю справа (ширина реки = 2)
            for dx in (0, 1):
                tile = self.get(x + dx, y)
                if tile:
                    tile.type = TileType.WATER
            # На следующей строке река сдвигается влево (-1), вправо (+1)
            # или идёт прямо (0). Ноль указан дважды — прямо она идёт чаще.
            # max/min не дают реке выйти за край карты.
            x = max(0, min(self.width - 2, x + rng.choice((-1, 0, 0, 1))))
