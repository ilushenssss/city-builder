"""Точка входа в игру. Запуск: python main.py"""

from __future__ import annotations

import sys

from city_builder.core.game import Game
from city_builder.data.catalog import CatalogError

# Этот блок выполняется только при прямом запуске файла (python main.py),
# но не при импорте main.py из другого модуля.
if __name__ == "__main__":
    try:
        # Создаём игру (окно, карту, камеру...) и запускаем бесконечный цикл.
        # Управление вернётся сюда только после закрытия окна.
        Game().run()
    except CatalogError as error:
        # Ошибка в data/shop.json — показываем понятное сообщение
        # вместо длинного списка вызовов (traceback)
        print(f"Ошибка в базе товаров: {error}")
        sys.exit(1)  # код 1 — «программа завершилась с ошибкой»
