"""Экономика: деньги, жители и то, как они меняются каждый тик.

Тик — это «шаг» симуляции (по умолчанию раз в 2 секунды, см. GameClock).
За один тик происходит:

  1. Заселение. Жители въезжают в свободное жильё (housing) работающих
     жилых зданий: каждый тик заселяется POPULATION_GROWTH (25%) свободных мест,
     но не меньше одного жителя. Жильё исчезло (снос) — лишние жители уезжают.

  2. Работа. Рабочих мест (workers) у предприятий и служб.
         работающие = min(жители, рабочие места)
     Укомплектованность = работающие / рабочие места (от 0 до 1).

  3. Деньги:
       + налоги  = работающие × TAX_PER_WORKER
       + доход   = сумма income всех предприятий × укомплектованность
                   (половина работников — половина дохода)
       − содержание = сумма upkeep ВСЕХ зданий (даже неработающих)

Здание работает, только если рядом есть дорога (или если дорога ему не нужна,
как самой дороге). Неработающее здание не даёт жилья, работы и дохода,
но содержание за него всё равно платится.

Получается замкнутый круг: жильё -> жители -> работники -> налоги и доход
-> деньги -> новые здания. Строить нужно и жильё, и рабочие места.
"""

from dataclasses import dataclass

from city_builder.config import (
    DEMOLISH_REFUND,
    POPULATION_GROWTH,
    STARTING_MONEY,
    TAX_PER_WORKER,
)
from city_builder.data.catalog import ShopItem
from city_builder.world.grid import Grid


@dataclass
class CityStats:
    """Сводка по всем зданиям города. Пересчитывается после постройки/сноса."""
    housing: int = 0          # всего мест для жителей (только в работающих зданиях)
    jobs: int = 0             # всего рабочих мест (только в работающих зданиях)
    max_income: int = 0       # доход предприятий, если бы все места были заняты
    upkeep: int = 0           # содержание всех зданий за тик
    no_road: int = 0          # сколько зданий не работает из-за отсутствия дороги


@dataclass
class TickReport:
    """Из чего складывается изменение денег за тик — для подсказки на панели."""
    taxes: int = 0
    income: int = 0
    upkeep: int = 0

    @property
    def net(self) -> int:
        """Итого за тик: плюс доходы, минус расходы."""
        return self.taxes + self.income - self.upkeep


class Economy:
    def __init__(self, grid: Grid, money: int = STARTING_MONEY) -> None:
        self.grid = grid
        self.money = money
        self.population = 0
        self.day = 0  # сколько тиков прошло («дни» города)

        self.stats = CityStats()
        self._stats_version = -1  # версия карты, для которой посчитаны stats
        self.refresh()

    # --- Производные величины ---

    @property
    def employed(self) -> int:
        """Сколько жителей работает: не больше, чем есть рабочих мест."""
        return min(self.population, self.stats.jobs)

    @property
    def staffing(self) -> float:
        """Укомплектованность предприятий: 1.0 — все места заняты, 0.5 — половина."""
        if self.stats.jobs == 0:
            return 0.0
        return self.employed / self.stats.jobs

    def forecast(self) -> TickReport:
        """Сколько денег прибавится/убавится на следующем тике при текущих жителях.
        Показывается на панели («+35 за тик»)."""
        return TickReport(
            taxes=self.employed * TAX_PER_WORKER,
            income=round(self.stats.max_income * self.staffing),
            upkeep=self.stats.upkeep,
        )

    # --- Пересчёт статистики ---

    def refresh(self) -> None:
        """Пересчитать статистику, если карта изменилась с прошлого раза.

        Вызывается каждый кадр, но реальная работа идёт только после
        постройки или сноса (когда меняется grid.version).
        """
        if self._stats_version == self.grid.version:
            return  # ничего не строили и не сносили — статистика актуальна
        self._stats_version = self.grid.version

        stats = CityStats()
        for building in self.grid.buildings:
            item = building.item
            # Сначала узнаём, есть ли рядом дорога, — от этого зависит, работает ли здание
            building.connected = self.grid.has_road_access(building)
            stats.upkeep += item.upkeep  # содержание платится всегда
            if not building.working:
                stats.no_road += 1
                continue  # неработающее здание не даёт ни жилья, ни работы, ни дохода
            stats.housing += item.housing
            stats.jobs += item.workers
            stats.max_income += item.income
        self.stats = stats

        # Снесли жильё — лишние жители уезжают сразу
        self.population = min(self.population, stats.housing)

    # --- Тик ---

    def tick(self) -> TickReport:
        """Один шаг симуляции. Вызывается из Game столько раз, сколько насчитал GameClock."""
        self.refresh()

        # 1. Заселение свободного жилья
        free = self.stats.housing - self.population
        if free > 0:
            # round() — округление; max(1, ...) — хотя бы один житель за тик
            self.population += min(free, max(1, round(free * POPULATION_GROWTH)))

        # 2–3. Работа и деньги
        report = self.forecast()
        self.money += report.net
        self.day += 1
        return report

    # --- Покупка и снос ---

    def can_afford(self, price: int) -> bool:
        return self.money >= price

    def spend(self, price: int) -> bool:
        """Заплатить. Возвращает False (и ничего не списывает), если денег не хватает."""
        if not self.can_afford(price):
            return False
        self.money -= price
        return True

    @staticmethod
    def refund_for(item: ShopItem) -> int:
        """Сколько денег вернётся при сносе здания. staticmethod — метод,
        которому не нужен self: результат зависит только от товара."""
        return int(item.price * DEMOLISH_REFUND)

    def refund(self, item: ShopItem) -> int:
        amount = self.refund_for(item)
        self.money += amount
        return amount
