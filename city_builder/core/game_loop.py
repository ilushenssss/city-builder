"""Игровой цикл: события -> обновление -> отрисовка.

Любая игра — это бесконечный цикл, который много раз в секунду делает:
  1. Читает ввод (клавиатура, мышь, закрытие окна).
  2. Обновляет состояние мира (камера, позже — экономика, жители).
  3. Рисует новый кадр.
Один проход цикла = один кадр. При FPS = 60 — 60 проходов в секунду.
"""

# Позволяет писать подсказки типов (Game) без реального импорта — см. ниже
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

# Game импортирует GameLoop, а GameLoop ссылается на Game — круговой импорт.
# TYPE_CHECKING равен True только для редактора/проверки типов, при запуске — False,
# поэтому реального импорта не происходит и ошибки нет.
if TYPE_CHECKING:
    from city_builder.core.game import Game

# Если окно «подвисло» (например, его перетаскивали), dt может оказаться
# огромным, и камера резко прыгнет. Ограничиваем dt десятой долей секунды.
MAX_DT = 0.1


class GameLoop:
    def __init__(self, game: Game, fps: int) -> None:
        self.game = game
        self.fps = fps
        # Clock следит за временем между кадрами и ограничивает FPS
        self.clock = pygame.time.Clock()

    @property
    def current_fps(self) -> float:
        """Реальный FPS (усреднённый по последним кадрам) — для отладки."""
        return self.clock.get_fps()

    def run(self) -> None:
        """Крутится, пока game.running == True."""
        while self.game.running:
            # tick() ждёт, чтобы кадров было не больше self.fps в секунду,
            # и возвращает, сколько миллисекунд прошло с прошлого кадра.
            # Делим на 1000 — получаем секунды (dt, «дельта времени»).
            dt = min(self.clock.tick(self.fps) / 1000, MAX_DT)

            # 1. Ввод: забираем все события, накопившиеся с прошлого кадра
            for event in pygame.event.get():
                self.game.handle_event(event)

            # 2. Обновление состояния
            self.game.update(dt)

            # 3. Отрисовка: рисуем кадр в памяти...
            self.game.draw()
            # ...и показываем его на экране целиком (без мерцания)
            pygame.display.flip()
