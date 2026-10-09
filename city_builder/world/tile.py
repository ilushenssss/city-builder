"""Клетка карты — минимальная единица игрового мира."""

from dataclasses import dataclass
from enum import Enum

from city_builder.world.building import Building


class TileType(Enum):
    """Тип местности клетки.

    Enum — перечисление: фиксированный набор вариантов. Это надёжнее
    простых строк: опечатка вроде TileType.GRAS сразу даст ошибку.
    Новые типы (песок, лес, горы) добавляются сюда одной строкой
    + цвет в config.TILE_COLORS.
    """
    GRASS = "grass"  # трава — на ней можно строить
    WATER = "water"  # вода — строить можно только мосты


# @dataclass автоматически создаёт __init__, __repr__ и __eq__
# по списку полей. То есть можно писать Tile(3, 5) или Tile(3, 5, TileType.WATER)
# без ручного конструктора.
@dataclass
class Tile:
    x: int                            # столбец клетки на карте (0..GRID_WIDTH-1)
    y: int                            # строка клетки на карте (0..GRID_HEIGHT-1)
    type: TileType = TileType.GRASS   # тип местности, по умолчанию трава
    # Здание на клетке (None — пусто). Здание 2×2 занимает 4 клетки,
    # и во всех четырёх лежит ссылка на ОДИН и тот же объект Building.
    building: Building | None = None
