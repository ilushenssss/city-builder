"""Картинки зданий и категорий: загрузка из папки assets/, кэш, масштабирование.

Где ищется картинка:
  * если в shop.json у товара есть поле "image" — по этому пути внутри assets/;
  * иначе — assets/buildings/<id товара>.png (для категорий — assets/categories/<id>.png).
Если файла нет, методы возвращают None, и вместо картинки рисуется цвет.
Поэтому картинки можно добавлять по одной — игра не сломается.

Зачем кэш:
  1. Чтение файла с диска — медленно. Каждую картинку читаем один раз.
  2. Растягивание (scale) — тоже медленно. Картинку 64×64 при масштабе 1.5
     нужно растянуть до 48×48, и делать это каждый кадр для каждого из сотен
     зданий нельзя. Растянутую копию запоминаем по ключу (картинка, размер)
     и в следующих кадрах берём готовую.
"""

from pathlib import Path

import pygame

from city_builder.config import ASSETS_DIR, IMAGE_CACHE_LIMIT, IMAGE_SMOOTH_SCALING
from city_builder.data.catalog import Category, ShopItem


class ImageLibrary:
    def __init__(self, assets_dir: Path = ASSETS_DIR) -> None:
        self.assets_dir = assets_dir
        # Оригиналы: {"buildings/house_small.png": Surface или None}.
        # None тоже запоминаем — чтобы не проверять отсутствующий файл каждый кадр.
        self._originals: dict[str, pygame.Surface | None] = {}
        # Растянутые копии: {(id картинки, (ширина, высота), прозрачность): Surface}
        self._scaled: dict[tuple[int, tuple[int, int], int], pygame.Surface] = {}

    # --- Загрузка ---

    def load(self, relative_path: str, warn_if_missing: bool = False) -> pygame.Surface | None:
        """Загрузить картинку из assets/ (один раз, дальше — из кэша)."""
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
            print(f"Картинка не найдена: {full_path} — вместо неё будет цвет")

        self._originals[relative_path] = image
        return image

    def for_item(self, item: ShopItem) -> pygame.Surface | None:
        """Картинка товара (здания) или None."""
        if item.image:
            return self.load(item.image, warn_if_missing=True)
        return self.load(f"buildings/{item.id}.png")

    def for_category(self, category: Category) -> pygame.Surface | None:
        """Картинка категории магазина или None."""
        if category.image:
            return self.load(category.image, warn_if_missing=True)
        return self.load(f"categories/{category.id}.png")

    # --- Масштабирование ---

    def scaled(self, image: pygame.Surface, size: tuple[int, int],
               alpha: int = 255) -> pygame.Surface:
        """Картинка, растянутая до size, с прозрачностью alpha (255 — непрозрачная).

        Пропорции не сохраняются: картинка заполняет весь прямоугольник.
        Для зданий так и нужно — картинка 2×2 должна ровно лечь на 2×2 клетки.
        """
        width, height = max(1, size[0]), max(1, size[1])
        # id(image) — уникальный номер объекта в памяти. Оригиналы живут
        # в self._originals всю игру, поэтому номер не меняется.
        key = (id(image), (width, height), alpha)
        cached = self._scaled.get(key)
        if cached is None:
            if len(self._scaled) >= IMAGE_CACHE_LIMIT:
                self._scaled.clear()  # кэш разросся (много разных масштабов) — начинаем заново
            scale = pygame.transform.smoothscale if IMAGE_SMOOTH_SCALING else pygame.transform.scale
            cached = scale(image, (width, height))
            if alpha < 255:
                cached.set_alpha(alpha)  # прозрачность всей картинки (для призрака)
            self._scaled[key] = cached
        return cached

    def fit(self, image: pygame.Surface, max_size: tuple[int, int]) -> pygame.Surface:
        """Картинка, уменьшенная (или увеличенная) так, чтобы влезть в max_size
        с сохранением пропорций. Для карточек магазина: квадратная картинка
        в широкой области не должна сплющиться."""
        max_w, max_h = max_size
        img_w, img_h = image.get_size()
        # Во сколько раз можно растянуть, чтобы влезло и по ширине, и по высоте
        factor = min(max_w / img_w, max_h / img_h)
        return self.scaled(image, (round(img_w * factor), round(img_h * factor)))
