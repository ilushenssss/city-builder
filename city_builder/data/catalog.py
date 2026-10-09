"""Каталог товаров магазина: загрузка из JSON-файла и проверка данных.

Сами товары лежат не в коде, а в файле data/shop.json. Чтобы добавить
товар или категорию, достаточно дописать запись в этот файл — код менять
не нужно.

Структура файла:

    {
      "categories": [ {"id": "roads", "name": "Дороги", ...}, ... ],
      "items":      [ {"id": "road_dirt", "category": "roads", ...}, ... ]
    }

Товар ссылается на свою категорию через поле "category" (это id категории).

Загрузчик строго проверяет файл. Если в нём ошибка (опечатка в поле,
неверный тип, несуществующая категория), игра сразу остановится
с понятным сообщением, а не упадёт непонятно где посреди игры.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Цвет — три числа (красный, зелёный, синий) от 0 до 255
Color = tuple[int, int, int]

# Где можно ставить товар (поле "placement" в shop.json)
PLACEMENT_LAND = "land"    # только на суше (по умолчанию)
PLACEMENT_WATER = "water"  # только на воде (например, мост)
PLACEMENTS = (PLACEMENT_LAND, PLACEMENT_WATER)


class CatalogError(Exception):
    """Ошибка в файле каталога. Текст ошибки объясняет, что и где не так."""


# frozen=True — объект нельзя изменить после создания. Товары — это справочник,
# во время игры они не меняются, и так случайно испортить их не получится.
@dataclass(frozen=True)
class Category:
    id: str            # уникальный идентификатор, на него ссылаются товары
    name: str          # название для игрока
    color: Color       # цвет карточки-заглушки (позже — иконка)
    description: str   # короткое описание


@dataclass(frozen=True)
class ShopItem:
    id: str                 # уникальный идентификатор товара
    name: str               # название для игрока
    category: str           # id категории, к которой относится товар
    price: int              # цена постройки
    upkeep: int             # содержание — сколько стоит за каждый тик экономики (этап 2)
    size: tuple[int, int]   # сколько клеток занимает: (ширина, высота)
    color: Color            # цвет на карте и на карточке (позже — картинка)
    description: str        # короткое описание
    placement: str = PLACEMENT_LAND  # где можно строить: PLACEMENT_LAND или PLACEMENT_WATER


class Catalog:
    """Все категории и товары. Создаётся функцией load_catalog()."""

    def __init__(self, categories: list[Category], items: list[ShopItem]) -> None:
        # Порядок сохраняется как в файле — в таком же порядке они будут в магазине
        self.categories = categories
        self.items = items
        # Словарь для быстрого поиска товара по id: {"road_dirt": ShopItem(...), ...}
        self._items_by_id = {item.id: item for item in items}

    def items_in(self, category_id: str) -> list[ShopItem]:
        """Все товары одной категории."""
        return [item for item in self.items if item.category == category_id]

    def get_item(self, item_id: str) -> ShopItem:
        """Товар по id. Понадобится на этапе 1: игрок выбрал товар — ставим его на карту."""
        return self._items_by_id[item_id]


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------

def load_catalog(path: Path) -> Catalog:
    """Прочитать каталог из JSON-файла и проверить его.

    При любой ошибке в файле выбрасывает CatalogError с понятным текстом.
    """
    # 1. Читаем файл
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # from None — не показывать в ошибке «технический» хвост исходной ошибки
        raise CatalogError(f"Файл каталога не найден: {path}") from None

    # 2. Разбираем JSON (текст -> словари и списки Python)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CatalogError(
            f"{path.name}, строка {e.lineno}, столбец {e.colno}: ошибка в JSON — {e.msg}"
        ) from None

    if not isinstance(data, dict):
        raise CatalogError(f"{path.name}: файл должен начинаться с {{ и содержать объект")

    # 3. Превращаем словари в объекты Category / ShopItem, проверяя каждое поле
    raw_categories = _get(data, "categories", list, path.name)
    raw_items = _get(data, "items", list, path.name)
    categories = [_parse_category(record, i) for i, record in enumerate(raw_categories)]
    items = [_parse_item(record, i) for i, record in enumerate(raw_items)]

    # 4. Проверки, которые касаются нескольких записей сразу
    _check_unique_ids([c.id for c in categories], "категорий")
    _check_unique_ids([item.id for item in items], "товаров")

    category_ids = {c.id for c in categories}
    for item in items:
        if item.category not in category_ids:
            raise CatalogError(
                f'Товар "{item.id}": категории "{item.category}" не существует. '
                f"Доступные категории: {', '.join(sorted(category_ids))}"
            )

    return Catalog(categories, items)


def _parse_category(record: Any, index: int) -> Category:
    where = f"Категория №{index + 1}"  # пока id не прочитан — называем по номеру
    if not isinstance(record, dict):
        raise CatalogError(f"{where}: должна быть объектом {{...}}")
    category_id = _get(record, "id", str, where)
    where = f'Категория "{category_id}"'  # теперь id известен — сообщения понятнее
    return Category(
        id=category_id,
        name=_get(record, "name", str, where),
        color=_parse_color(_get(record, "color", list, where), where),
        description=_get(record, "description", str, where, default=""),
    )


def _parse_item(record: Any, index: int) -> ShopItem:
    where = f"Товар №{index + 1}"
    if not isinstance(record, dict):
        raise CatalogError(f"{where}: должен быть объектом {{...}}")
    item_id = _get(record, "id", str, where)
    where = f'Товар "{item_id}"'

    price = _get(record, "price", int, where)
    upkeep = _get(record, "upkeep", int, where, default=0)
    if price < 0 or upkeep < 0:
        raise CatalogError(f"{where}: цена и содержание не могут быть отрицательными")

    placement = _get(record, "placement", str, where, default=PLACEMENT_LAND)
    if placement not in PLACEMENTS:
        raise CatalogError(
            f'{where}: поле "placement" должно быть одним из {PLACEMENTS}, а сейчас {placement!r}'
        )

    return ShopItem(
        id=item_id,
        name=_get(record, "name", str, where),
        category=_get(record, "category", str, where),
        price=price,
        upkeep=upkeep,
        size=_parse_size(_get(record, "size", list, where, default=[1, 1]), where),
        color=_parse_color(_get(record, "color", list, where), where),
        description=_get(record, "description", str, where, default=""),
        placement=placement,
    )


# ---------------------------------------------------------------------------
# Вспомогательные проверки
# ---------------------------------------------------------------------------

# Особое значение «по умолчанию не задано». Нельзя использовать None:
# тогда нельзя было бы отличить «значения по умолчанию нет» от «по умолчанию None».
_MISSING = object()

# Названия типов для сообщений об ошибках
_TYPE_NAMES = {str: "строкой", int: "целым числом", list: "списком [...]", dict: "объектом {...}"}


def _get(record: dict, field: str, expected_type: type, where: str, default: Any = _MISSING) -> Any:
    """Достать поле из словаря и проверить его тип.

    Если поля нет: вернуть default, а если default не задан — это ошибка.
    """
    if field not in record:
        if default is not _MISSING:
            return default
        raise CatalogError(f'{where}: нет обязательного поля "{field}"')

    value = record[field]
    # Особый случай: в Python True/False — тоже целые числа (True == 1),
    # поэтому отдельно запрещаем их там, где ждём число.
    wrong_bool = expected_type is int and isinstance(value, bool)
    if not isinstance(value, expected_type) or wrong_bool:
        raise CatalogError(
            f'{where}: поле "{field}" должно быть {_TYPE_NAMES[expected_type]}, а сейчас {value!r}'
        )
    return value


def _parse_color(value: list, where: str) -> Color:
    """[r, g, b] -> (r, g, b), каждое число от 0 до 255."""
    valid = len(value) == 3 and all(
        isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value
    )
    if not valid:
        raise CatalogError(f"{where}: цвет должен быть [r, g, b] с числами от 0 до 255, а сейчас {value}")
    return value[0], value[1], value[2]


def _parse_size(value: list, where: str) -> tuple[int, int]:
    """[ширина, высота] в клетках, оба числа >= 1."""
    valid = len(value) == 2 and all(
        isinstance(n, int) and not isinstance(n, bool) and n >= 1 for n in value
    )
    if not valid:
        raise CatalogError(f"{where}: размер должен быть [ширина, высота] с числами от 1, а сейчас {value}")
    return value[0], value[1]


def _check_unique_ids(ids: list[str], what: str) -> None:
    """Каждый id должен встречаться один раз — иначе непонятно, какой товар имеется в виду."""
    seen = set()
    for item_id in ids:
        if item_id in seen:
            raise CatalogError(f'id "{item_id}" повторяется в списке {what}')
        seen.add(item_id)
