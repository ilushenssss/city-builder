"""Цель игры, победа и поражение.

  Победа:    население достигло GOAL_POPULATION (500 жителей).
  Поражение: деньги в минусе BANKRUPTCY_TICKS тиков подряд (банкротство).
             Как только деньги снова >= 0, счётчик долга обнуляется.

Проверка идёт после каждого тика экономики (Game вызывает on_tick).

После победы можно «продолжить» — играть дальше без цели (свободная игра).
Тогда победа и поражение больше не проверяются.
"""

from enum import Enum, auto

from city_builder.config import BANKRUPTCY_TICKS, GOAL_POPULATION
from city_builder.economy.economy import Economy


class Outcome(Enum):
    PLAYING = auto()  # игра идёт
    WON = auto()      # победа
    LOST = auto()     # поражение (банкротство)


class GoalTracker:
    def __init__(self, economy: Economy) -> None:
        self.economy = economy
        self.target = GOAL_POPULATION
        self.outcome = Outcome.PLAYING
        self.debt_ticks = 0        # сколько тиков подряд деньги в минусе
        self.continued = False     # игрок выбрал «Продолжить» после победы

    # --- Состояние ---

    @property
    def progress(self) -> float:
        """Доля выполнения цели: 0.0 — ничего, 1.0 — выполнено."""
        return min(1.0, self.economy.population / self.target)

    @property
    def in_debt(self) -> bool:
        return self.economy.money < 0

    @property
    def ticks_until_bankruptcy(self) -> int:
        """Сколько тиков (дней) осталось до банкротства, если долг не погасить."""
        return BANKRUPTCY_TICKS - self.debt_ticks

    @property
    def finished(self) -> bool:
        """Игра закончилась и показывается экран итогов.
        Пока True, время стоит, а карта не реагирует на мышь."""
        return self.outcome != Outcome.PLAYING and not self.continued

    @property
    def active(self) -> bool:
        """Проверяется ли ещё цель (после «Продолжить» — нет)."""
        return self.outcome == Outcome.PLAYING

    # --- Проверка после тика ---

    def on_tick(self) -> None:
        if not self.active:
            return

        if self.economy.population >= self.target:
            self.outcome = Outcome.WON
            return

        if self.in_debt:
            self.debt_ticks += 1
            if self.debt_ticks >= BANKRUPTCY_TICKS:
                self.outcome = Outcome.LOST
        else:
            self.debt_ticks = 0  # долг погашен — отсчёт начинается заново

    # --- Действия игрока на экране итогов ---

    def continue_playing(self) -> None:
        """«Продолжить» после победы: экран итогов закрывается, цель больше не проверяется."""
        if self.outcome == Outcome.WON:
            self.continued = True
