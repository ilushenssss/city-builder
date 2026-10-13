"""Картинки (спрайты) зданий, категорий и местности: загрузка из assets/, кэш, масштабирование.

Где ищется картинка:
  * здание:    поле "image" из shop.json, иначе assets/buildings/<id товара>.png;
  * категория: поле "image", иначе assets/categories/<id>.png;
  * местность: assets/terrain/<grass|water>.png.

Если файла нет, игра НЕ ломается: sprite() и terrain() рисуют запасной
спрайт сами (простая коробка цвета товара или ровный ромб — см. iso_sprites.py).
Поэтому картинки можно добавлять по одной.

Все спрайты — изометрические, нарисованы в масштабе текстуры (ромб клетки 128×64),
см. README «Картинки».

Зачем кэш:
  1. Чтение файла с диска — медленно. Каждую картинку читаем один раз.
  2. Растягивание (scale) — тоже медленно. Растянутую копию запоминаем
     по ключу (картинка, размер, прозрачность, тонировка) и берём готовую.
"""

from pathlib import Path

import pygame

from city_builder.config import (
    ASSETS_DIR,
    FLAT_CATEGORIES,
    IMAGE_CACHE_LIMIT,
    IMAGE_SMOOTH_SCALING,
    TILE_COLORS,
)
from city_builder.data.catalog import Category, ShopItem
from city_builder.render import iso_sprites

Color = tuple[int, int, int]


class ImageLibrary:
    def __init__(self, assets_dir: Path = ASSETS_DIR) -> None:
        self.assets_dir = assets_dir
        # Оригиналы: {"buildings/house_small.png": Surface или None}.
        # None тоже запоминаем — чтобы не проверять отсутствующий файл каждый кадр.
        self._originals: dict[str, pygame.Surface | None] = {}
        # Запасные спрайты, нарисованные кодом: {"house_small": Surface}
        self._generated: dict[str, pygame.Surface] = {}
        # Растянутые копии: {(id картинки, (ширина, высота), прозрачность, тонировка): Surface}
        self._scaled: dict[tuple, pygame.Surface] = {}

    # --- Загрузка файлов ---

    def load(self, relative_path: str, warn_if_missing: bool = False) -> pygame.Surface | None:
        """Загрузить картинку из assets/ (один раз, дальше — из кэша). Нет файла — None."""
        if relative_path in self._originals:
            return self._originals[relative_path]

        full_path = self.assets_dir / relative_path
        image = None
        if full_path.is_file():
            try:
                # convert_alpha() переводит картинку в формат экрана с прозрачностью.
                # Без него отрисовка в разы медленнее. Работает только ПОСЛЕ
                # создания окна (pygame.display.set_mode), поэтому ImageLibrary
                # создаётся в Game после окна.
                image = pygame.image.load(str(full_path)).convert_alpha()
            except pygame.error as error:
                print(f"Не удалось загрузить картинку {full_path}: {error}")
        elif warn_if_missing:
            # Путь указан в shop.json явно, но файла нет — вероятно, опечатка
            print(f"Картинка не найдена: {full_path} — вместо неё будет простой спрайт")

        self._originals[relative_path] = image
        return image

    def for_item(self, item: ShopItem) -> pygame.Surface | None:
        """PNG-картинка товара или None (без запасного варианта)."""
        if item.image:
            return self.load(item.image, warn_if_missing=True)
        return self.load(f"buildings/{item.id}.png")

    def for_category(self, category: Category) -> pygame.Surface | None:
        """PNG-картинка категории магазина или None."""
        if category.image:
            return self.load(category.image, warn_if_missing=True)
        return self.load(f"categories/{category.id}.png")

    # --- Спрайты с запасным вариантом ---

    def sprite(self, item: ShopItem) -> pygame.Surface:
        """Спрайт здания: PNG из assets/, а если его нет — нарисованная коробка."""
        image = self.for_item(item)
        if image is not None:
            return image
        if item.id not in self._generated:
            width, height = item.size
            flat = item.category in FLAT_CATEGORIES or item.floors == 0
            surface = iso_sprites.simple_building_sprite(width, height, item.floors, item.color, flat)
            self._generated[item.id] = surface.convert_alpha()
        return self._generated[item.id]

    def terrain(self, name: str) -> pygame.Surface:
        """Ромб местности ("grass", "water"): PNG из assets/terrain/ или ровный ромб цвета."""
        image = self.load(f"terrain/{name}.png")
        if image is not None:
            return image
        key = f"terrain:{name}"
        if key not in self._generated:
            self._generated[key] = iso_sprites.flat_tile(TILE_COLORS[name], noise=0.3).convert_alpha()
        return self._generated[key]

    # --- Масштабирование ---

    def scaled(self, image: pygame.Surface, size: tuple[int, int],
               alpha: int = 255, tint: Color | None = None) -> pygame.Surface:
        """Картинка, растянутая до size.

        alpha — прозрачность всей картинки (255 — непрозрачная; для «призрака» здания);
        tint  — тонировка цветом (например, красным — здание выбрано для сноса).
        """
        width, height = max(1, size[0]), max(1, size[1])
        # id(image) — уникальный номер объекта в памяти. Оригиналы живут в кэше
        # всю игру, поэтому номер не меняется.
        key = (id(image), (width, height), alpha, tint)
        cached = self._scaled.get(key)
        if cached is None:
            if len(self._scaled) >= IMAGE_CACHE_LIMIT:
                self._scaled.clear()  # кэш разросся (много разных масштабов) — начинаем заново
            scale = pygame.transform.smoothscale if IMAGE_SMOOTH_SCALING else pygame.transform.scale
            cached = scale(image, (width, height))
            if tint is not None:
                # Умножение цветов «окрашивает» картинку, прозрачность при этом не трогается
                # (флаг BLEND_RGB_... меняет только R, G, B, но не альфа-канал)
                cached.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
            if alpha < 255:
                cached.set_alpha(alpha)
            self._scaled[key] = cached
        return cached

    def fit(self, image: pygame.Surface, max_size: tuple[int, int]) -> pygame.Surface:
        """Картинка, вписанная в max_size с сохранением пропорций (для карточек магазина)."""
        max_w, max_h = max_size
        img_w, img_h = image.get_size()
        factor = min(max_w / img_w, max_h / img_h)
        return self.scaled(image, (round(img_w * factor), round(img_h * factor)))
