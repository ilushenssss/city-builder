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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Цвет — три числа (красный, зелёный, синий) от 0 до 255
Color = tuple[int, int, int]

# Где можно ставить товар (поле "placement" в shop.json)
PLACEMENT_LAND = "land"              # только на суше (по умолчанию)
PLACEMENT_WATER = "water"            # только на воде (например, мост)
PLACEMENT_NEAR_WATER = "near_water"  # на суше, но вплотную к воде (электростанция — для охлаждения)
PLACEMENTS = (PLACEMENT_LAND, PLACEMENT_WATER, PLACEMENT_NEAR_WATER)

# Слои «сетей» (поле "layer"): такие товары — не здания, а линии поверх/под клетками
LAYER_POWER = "power"    # линия электропередач (тянется мышью)
LAYER_PIPE = "pipe"      # водопровод под землёй (тянется мышью)
LAYER_SIGNAL = "signal"  # светофор на перекрёстке
LAYERS = (LAYER_POWER, LAYER_PIPE, LAYER_SIGNAL)
MAX_LEVEL = 5


class CatalogError(Exception):
    """Ошибка в файле каталога. Текст ошибки объясняет, что и где не так."""


# frozen=True — объект нельзя изменить после создания. Товары — это справочник,
# во время игры они не меняются, и так случайно испортить их не получится.
@dataclass(frozen=True)
class Category:
    id: str            # уникальный идентификатор, на него ссылаются товары
    name: str          # название для игрока
    color: Color       # цвет, если картинки нет
    description: str   # короткое описание
    # Путь к картинке относительно папки assets/. None — искать по умолчанию:
    # assets/categories/<id>.png (см. render/images.py)
    image: str | None = None


@dataclass(frozen=True)
class ShopItem:
    id: str                 # уникальный идентификатор товара
    name: str               # название для игрока
    category: str           # id категории, к которой относится товар
    price: int              # цена постройки
    upkeep: int             # содержание — сколько денег списывается за каждый тик экономики
    size: tuple[int, int]   # сколько клеток занимает: (ширина, высота)
    color: Color            # цвет на карте и на карточке, если картинки нет
    description: str        # короткое описание
    placement: str = PLACEMENT_LAND  # где можно строить: PLACEMENT_LAND или PLACEMENT_WATER
    # Путь к картинке относительно папки assets/. None — искать по умолчанию:
    # assets/buildings/<id>.png (см. render/images.py)
    image: str | None = None

    # --- Экономика (см. economy/economy.py) ---
    housing: int = 0          # мест для жителей (жилые здания)
    workers: int = 0          # рабочих мест
    income: int = 0           # доход за тик, если все рабочие места заняты
    needs_road: bool = True   # работает, только если рядом есть дорога
    floors: int = 1           # этажей — высота здания в изометрии (0 — плоское: дорога, парк)

    # --- Инфраструктура (см. economy/networks.py) ---
    power_output: int = 0     # сколько электричества даёт (электростанция)
    power_use: int = 0        # сколько потребляет; без электричества здание не работает
    water_output: int = 0     # сколько воды даёт (водонапорная башня)
    water_use: int = 0        # сколько потребляет; без воды здание не работает

    # --- Производство (см. economy/economy.py) ---
    # Словари «ресурс -> сколько за тик»: {"wood": 6}. Ресурсы — в config.RESOURCE_NAMES.
    # field(default_factory=dict) — у каждого товара свой пустой словарь по умолчанию
    produces: dict[str, int] = field(default_factory=dict)
    consumes: dict[str, int] = field(default_factory=dict)
    storage: int = 0          # на сколько увеличивает склад (для каждого ресурса)

    # --- Счастье (см. economy/happiness.py) ---
    happiness: int = 0        # влияние на счастье домов в радиусе: + (парк) или − (завод)
    radius: int = 0           # радиус влияния в клетках

    # --- Прогресс и сети ---
    level: int = 1            # с какого уровня города товар можно купить
    layer: str | None = None  # None — здание; "power"/"pipe"/"signal" — сеть (см. LAYERS)
    capacity: int = 0         # пропускная способность дороги (машин за тик)


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
        image=_get(record, "image", str, where, default=None),
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

    # Числовые поля: необязательные, отрицательными быть не могут.
    # По умолчанию 0, а этажей — 1 (обычное одноэтажное здание).
    numbers: dict[str, Any] = {}
    non_negative = (("housing", 0), ("workers", 0), ("income", 0), ("floors", 1),
                    ("power_output", 0), ("power_use", 0), ("water_output", 0), ("water_use", 0),
                    ("storage", 0), ("radius", 0))
    non_negative += (("capacity", 0),)
    for name, default in non_negative:
        value = _get(record, name, int, where, default=default)
        if value < 0:
            raise CatalogError(f'{where}: поле "{name}" не может быть отрицательным')
        numbers[name] = value
    # Счастье может быть и отрицательным (загрязнение от завода)
    numbers["happiness"] = _get(record, "happiness", int, where, default=0)
    if numbers["happiness"] and not numbers["radius"]:
        raise CatalogError(f'{where}: у "happiness" должен быть "radius" — на сколько клеток действует')

    numbers["level"] = _get(record, "level", int, where, default=1)
    if not 1 <= numbers["level"] <= MAX_LEVEL:
        raise CatalogError(f'{where}: "level" должен быть от 1 до {MAX_LEVEL}')
    numbers["layer"] = _get(record, "layer", str, where, default=None)
    if numbers["layer"] is not None and numbers["layer"] not in LAYERS:
        raise CatalogError(f'{where}: "layer" должен быть одним из {LAYERS}')

    # Производство и потребление ресурсов
    numbers["produces"] = _parse_resources(_get(record, "produces", dict, where, default={}), where, "produces")
    numbers["consumes"] = _parse_resources(_get(record, "consumes", dict, where, default={}), where, "consumes")

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
        image=_get(record, "image", str, where, default=None),
        needs_road=_get(record, "needs_road", bool, where, default=True),
        **numbers,  # ** раскрывает словарь в именованные аргументы: housing=..., workers=...
    )


# ---------------------------------------------------------------------------
# Вспомогательные проверки
# ---------------------------------------------------------------------------

# Особое значение «по умолчанию не задано». Нельзя использовать None:
# тогда нельзя было бы отличить «значения по умолчанию нет» от «по умолчанию None».
_MISSING = object()

# Названия типов для сообщений об ошибках
_TYPE_NAMES = {
    str: "строкой",
    int: "целым числом",
    bool: "true или false",
    list: "списком [...]",
    dict: "объектом {...}",
}


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


def _parse_resources(value: dict, where: str, field_name: str) -> dict[str, int]:
    """{"wood": 6} — ресурс из config.RESOURCE_NAMES и положительное целое количество."""
    from city_builder.config import RESOURCE_NAMES  # импорт здесь, чтобы было видно, откуда список

    for resource, amount in value.items():
        if resource not in RESOURCE_NAMES:
            raise CatalogError(
                f'{where}: в "{field_name}" неизвестный ресурс "{resource}". '
                f"Доступные: {', '.join(RESOURCE_NAMES)}"
            )
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise CatalogError(f'{where}: в "{field_name}" количество «{resource}» должно быть целым > 0')
    return dict(value)


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
