"""Сетка карты — хранит все клетки мира.

Важно: здесь нет ничего про pygame и отрисовку. Это «чистые данные».
Благодаря этому карту легко сохранить в файл, проверить тестами
или нарисовать совсем по-другому (например, спрайтами вместо квадратов).
"""

import random
from collections.abc import Iterator

from city_builder.config import ROAD_CATEGORIES
from city_builder.data.catalog import PLACEMENT_NEAR_WATER, PLACEMENT_WATER, ShopItem
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
        # Список всех зданий — удобно перебирать при отрисовке и в экономике
        self.buildings: list[Building] = []
        # «Номер версии» карты: увеличивается при каждой постройке и сносе.
        # Экономика сравнивает его с запомненным и пересчитывает статистику,
        # только если карта изменилась, — а не каждый кадр.
        self.version = 0

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
        if item.placement == PLACEMENT_NEAR_WATER and not self.site_near_water(x, y, width, height):
            return f"{item.name}: строится только вплотную к воде"
        return None

    def _around(self, x: int, y: int, width: int, height: int) -> list[tuple[int, int]]:
        """Клетки вплотную к области (сверху, снизу, слева, справа; без углов)."""
        around = [(tx, y - 1) for tx in range(x, x + width)] + [(tx, y + height) for tx in range(x, x + width)]
        around += [(x - 1, ty) for ty in range(y, y + height)] + [(x + width, ty) for ty in range(y, y + height)]
        return around

    def site_near_water(self, x: int, y: int, width: int, height: int) -> bool:
        """Есть ли вода вплотную к области — для электростанции и водоочистной."""
        for tx, ty in self._around(x, y, width, height):
            tile = self.get(tx, ty)
            if tile is not None and tile.type == TileType.WATER:
                return True
        return False

    def place(self, item: ShopItem, x: int, y: int) -> Building:
        """Поставить здание. Перед вызовом место нужно проверить через placement_error."""
        building = Building(item, x, y)
        for tx, ty in building.footprint():
            self.tiles[ty][tx].building = building
        self.buildings.append(building)
        self.version += 1
        return building

    def remove(self, building: Building) -> None:
        """Снести здание: освободить все его клетки и убрать из списка."""
        for tx, ty in building.footprint():
            self.tiles[ty][tx].building = None
        self.buildings.remove(building)
        self.version += 1

    # --- Дороги ---

    def is_road(self, x: int, y: int) -> bool:
        """Стоит ли на клетке дорога."""
        tile = self.get(x, y)
        return (tile is not None and tile.building is not None
                and tile.building.item.category in ROAD_CATEGORIES)

    def site_has_road(self, x: int, y: int, width: int, height: int) -> bool:
        """Есть ли дорога вплотную к области (сверху, снизу, слева или справа).

        Для здания 2×2 в (5, 5) проверяются клетки вокруг него:

              . R R .        R — проверяемые клетки
              R # # R        # — само здание
              R # # R        углы (.) не считаются: по диагонали дорога не примыкает
              . R R .
        """
        for tx in range(x, x + width):
            if self.is_road(tx, y - 1) or self.is_road(tx, y + height):  # сверху и снизу
                return True
        for ty in range(y, y + height):
            if self.is_road(x - 1, ty) or self.is_road(x + width, ty):  # слева и справа
                return True
        return False

    def has_road_access(self, building: Building) -> bool:
        return self.site_has_road(building.x, building.y, building.width, building.height)

    def roads_around(self, building: Building) -> list[tuple[int, int]]:
        """Все клетки дороги вплотную к зданию (те же клетки, что в site_has_road).
        Отсюда жители выходят из здания и сюда приходят."""
        around = self._around(building.x, building.y, building.width, building.height)
        return [(tx, ty) for tx, ty in around if self.is_road(tx, ty)]

    def find_road_path(self, start: tuple[int, int],
                       goals: set[tuple[int, int]]) -> list[tuple[int, int]] | None:
        """Кратчайший путь по дорогам от клетки start до любой клетки из goals.

        Поиск в ширину (BFS): сначала проверяем соседей start, потом соседей
        соседей и т.д. — как круги на воде. Первая достигнутая цель — самая близкая.
        Для каждой клетки запоминаем, откуда в неё пришли (came_from), а в конце
        восстанавливаем путь, двигаясь от цели назад к старту.

        Возвращает список клеток от start до цели или None, если пути нет.
        """
        from collections import deque  # очередь: быстро добавлять в конец и брать из начала

        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            if current in goals:
                # Восстанавливаем путь от цели к старту и разворачиваем
                path = []
                node: tuple[int, int] | None = current
                while node is not None:
                    path.append(node)
                    node = came_from[node]
                return path[::-1]  # [::-1] — список задом наперёд
            cx, cy = current
            for nxt in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if nxt not in came_from and self.is_road(*nxt):
                    came_from[nxt] = current
                    queue.append(nxt)
        return None

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
