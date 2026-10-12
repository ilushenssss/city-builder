"""Игровое время: пауза, скорость ×1/×2/×3 и «фиксированный тик».

Кадры идут неравномерно (то 16 мс, то 20 мс), а экономика должна шагать
ровно: один тик = TICK_SECONDS секунд игрового времени. Поэтому время
копится в «накопителе»:

    кадр 1: накоплено 0.016 с  -> тиков 0
    ...
    кадр 125: накоплено 2.000 с -> тик! накопитель -= 2.0

На скорости ×2 время копится вдвое быстрее, на паузе — не копится вовсе.
Так экономика работает одинаково при любом FPS.
"""

from city_builder.config import GAME_SPEEDS, MAX_TICKS_PER_FRAME, TICK_SECONDS


class GameClock:
    def __init__(self) -> None:
        self.speed = GAME_SPEEDS[0]  # 0 — пауза, иначе одна из GAME_SPEEDS
        self._speed_before_pause = self.speed  # чтобы снять паузу на той же скорости
        self._accumulator = 0.0  # сколько игровых секунд накопилось с прошлого тика

    @property
    def paused(self) -> bool:
        return self.speed == 0

    @property
    def progress(self) -> float:
        """Сколько прошло до следующего тика: 0.0 — только что был, 1.0 — вот-вот.
        Для полоски на панели."""
        return self._accumulator / TICK_SECONDS

    def set_speed(self, speed: int) -> None:
        """Установить скорость (одну из GAME_SPEEDS). Снимает паузу."""
        if speed in GAME_SPEEDS:
            self.speed = speed

    def toggle_pause(self) -> None:
        """Пробел: пауза <-> продолжить на прежней скорости."""
        if self.paused:
            self.speed = self._speed_before_pause
        else:
            self._speed_before_pause = self.speed
            self.speed = 0

    def update(self, dt: float) -> int:
        """Добавить dt реальных секунд. Возвращает, сколько тиков нужно выполнить сейчас."""
        if self.paused:
            return 0
        self._accumulator += dt * self.speed
        ticks = int(self._accumulator // TICK_SECONDS)  # // — деление нацело
        self._accumulator -= ticks * TICK_SECONDS
        # Если игра долго висела, тиков могло накопиться много — не выполняем их все разом
        return min(ticks, MAX_TICKS_PER_FRAME)
