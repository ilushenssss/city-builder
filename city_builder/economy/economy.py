"""Экономика: деньги, жители, ресурсы и то, как они меняются каждый тик.

Тик — это «шаг» симуляции (по умолчанию раз в 2 секунды, см. GameClock).

Сначала — что вообще РАБОТАЕТ (пересчитывается после постройки и сноса, refresh):
  * дорога рядом (если нужна);
  * электричество и вода в районе (economy/networks.py) — без них здание стоит;
  * счастье домов (economy/happiness.py).

Потом за каждый тик (tick):

  1. Работа. Работающих жителей = min(жители, рабочие места).
     Укомплектованность = работающие / рабочие места (0..1).

  2. Производство по цепочкам (склад общий на весь город):
       ферма -> еда;  лесопилка -> древесина -> завод -> товары -> магазины.
     Эффективность здания = укомплектованность × доля сырья, которое нашлось.
     Сначала работают те, кому сырьё не нужно (ферма, лесопилка), потом
     перерабатывающие (завод), потом потребители (магазины) — чтобы товары,
     сделанные в этом тике, сразу можно было продать.
     Магазин без товаров — эффективность 0, дохода нет.

  3. Еда. Жители съедают FOOD_PER_RESIDENT еды на человека.
     Еды не хватило — голод: часть жителей уезжает.

  4. Жители. Если сыты и счастливы — заселяют свободное жильё
     (быстрее при высоком счастье). Если счастье города ниже UNHAPPY_LEVEL — уезжают.

  5. Деньги:
       + налоги  = работающие × TAX_PER_WORKER
       + доход   = сумма (income × эффективность) предприятий
       − содержание = сумма upkeep ВСЕХ зданий (даже неработающих)
"""

from dataclasses import dataclass, field

from city_builder.config import (
    BASE_HAPPINESS,
    BASE_STORAGE,
    DEMOLISH_REFUND,
    FOOD_PER_RESIDENT,
    HUNGER_LEAVE,
    POPULATION_GROWTH,
    RESOURCE_NAMES,
    STARTING_MONEY,
    TAX_PER_WORKER,
    UNHAPPY_LEAVE,
    UNHAPPY_LEVEL,
)
from city_builder.data.catalog import ShopItem
from city_builder.economy.happiness import compute_happiness
from city_builder.economy.networks import Infrastructure
from city_builder.world.building import Building
from city_builder.world.grid import Grid


@dataclass
class CityStats:
    """Сводка по всем зданиям города. Пересчитывается после постройки/сноса."""
    housing: int = 0          # мест для жителей (только в работающих зданиях)
    jobs: int = 0             # рабочих мест (только в работающих зданиях)
    upkeep: int = 0           # содержание всех зданий за тик
    storage: int = BASE_STORAGE  # вместимость склада для каждого ресурса
    happiness: float = BASE_HAPPINESS  # счастье города (0–100)


@dataclass
class TickReport:
    """Что произошло за последний тик — для панели и подсказок."""
    taxes: int = 0
    income: int = 0
    upkeep: int = 0
    # Ресурсы за тик: сколько произведено и потреблено (включая еду жителей)
    produced: dict[str, float] = field(default_factory=dict)
    consumed: dict[str, float] = field(default_factory=dict)
    hungry: bool = False      # не хватило еды
    unhappy: bool = False     # жители уезжают из-за низкого счастья

    @property
    def net(self) -> int:
        """Итого за тик: плюс доходы, минус расходы."""
        return self.taxes + self.income - self.upkeep


def production_stage(item: ShopItem) -> int:
    """Очерёдность в тике: 0 — добывают сырьё, 1 — перерабатывают, 2 — только потребляют."""
    if item.produces and not item.consumes:
        return 0
    if item.produces:
        return 1
    return 2


class Economy:
    def __init__(self, grid: Grid, money: int = STARTING_MONEY) -> None:
        self.grid = grid
        self.money = money
        self.population = 0
        self.day = 0  # сколько тиков прошло («дни» города)
        # Склад: сколько каждого ресурса есть сейчас (дробные — производство бывает частичным)
        self.stock: dict[str, float] = {resource: 0.0 for resource in RESOURCE_NAMES}
        self.infrastructure = Infrastructure(grid)
        self.last_report = TickReport()

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

    @property
    def problem_count(self) -> int:
        """Сколько зданий с проблемами (нет дороги, света, воды, сырья)."""
        return sum(1 for b in self.grid.buildings if b.problems)

    def forecast(self) -> TickReport:
        """Итоги последнего тика — на следующем будет примерно так же.
        Показывается на панели («+35 за тик»)."""
        return self.last_report

    # --- Пересчёт после постройки и сноса ---

    def refresh(self) -> None:
        """Пересчитать, что работает, если карта изменилась с прошлого раза.

        Вызывается каждый кадр, но реальная работа идёт только после
        постройки или сноса (когда меняется grid.version).
        """
        if self._stats_version == self.grid.version:
            return  # ничего не строили и не сносили — всё актуально
        self._stats_version = self.grid.version

        buildings = self.grid.buildings
        # 1. Дороги: есть ли дорога рядом с каждым зданием
        for b in buildings:
            b.connected = self.grid.has_road_access(b)
        # 2. Районы, электричество, вода
        self.infrastructure.recompute()
        # 3. Проблемы для значков (сырьё добавит tick)
        for b in buildings:
            b.problems = self._infrastructure_problems(b)
        # 4. Сводка
        stats = CityStats()
        for b in buildings:
            stats.upkeep += b.item.upkeep  # содержание платится всегда
            if not b.working:
                continue  # неработающее здание не даёт ни жилья, ни работы
            stats.housing += b.item.housing
            stats.jobs += b.item.workers
            stats.storage += b.item.storage
        stats.happiness = compute_happiness(buildings)
        self.stats = stats

        # Снесли жильё (или оно осталось без света) — лишние жители уезжают сразу
        self.population = min(self.population, stats.housing)
        for resource in self.stock:  # снесли склад — лишнее пропадает
            self.stock[resource] = min(self.stock[resource], stats.storage)

    @staticmethod
    def _infrastructure_problems(b: Building) -> list[str]:
        problems = []
        if b.item.needs_road and not b.connected:
            problems.append("road")
        if not b.powered:
            problems.append("power")
        if not b.watered:
            problems.append("water")
        return problems

    # --- Тик ---

    def tick(self) -> TickReport:
        """Один шаг симуляции. Вызывается из Game столько раз, сколько насчитал GameClock."""
        self.refresh()
        report = TickReport(upkeep=self.stats.upkeep,
                            produced={r: 0.0 for r in RESOURCE_NAMES},
                            consumed={r: 0.0 for r in RESOURCE_NAMES})
        staffing = self.staffing
        employed = self.employed

        # --- 2. Производство по цепочкам ---
        income = 0.0
        active = [b for b in self.grid.buildings if b.working]
        for b in self.grid.buildings:
            b.problems = [p for p in b.problems if p != "inputs"]  # сырьё проверим заново
            if not b.working:
                b.efficiency = 0.0
        # sorted с ключом — сначала стадия 0, потом 1, потом 2 (порядок постройки сохраняется)
        for b in sorted(active, key=lambda b: production_stage(b.item)):
            income += self._run_building(b, staffing, report)
        report.income = round(income)

        # --- 3. Еда ---
        need = self.population * FOOD_PER_RESIDENT
        eaten = min(self.stock["food"], need)
        self.stock["food"] -= eaten
        report.consumed["food"] += eaten
        report.hungry = eaten < need - 1e-9  # 1e-9 — запас на неточность дробных чисел

        # --- 4. Жители ---
        report.unhappy = self.stats.happiness < UNHAPPY_LEVEL
        if report.hungry or report.unhappy:
            share = HUNGER_LEAVE if report.hungry else UNHAPPY_LEAVE
            leave = max(1, round(self.population * share)) if self.population else 0
            self.population -= leave
        else:
            free = self.stats.housing - self.population
            if free > 0:
                # Счастье ускоряет заселение: при 50 — обычная скорость, при 100 — вдвое быстрее
                speed = POPULATION_GROWTH * self.stats.happiness / BASE_HAPPINESS
                self.population += min(free, max(1, round(free * speed)))

        # --- 5. Деньги ---
        report.taxes = employed * TAX_PER_WORKER
        self.money += report.net
        self.last_report = report
        self.day += 1
        return report

    def _run_building(self, b: Building, staffing: float, report: TickReport) -> float:
        """Один тик одного работающего здания: берёт сырьё, производит, приносит доход.
        Возвращает доход здания за тик."""
        item = b.item
        # Без работников здание работает настолько, насколько укомплектован город
        efficiency = staffing if item.workers else 1.0

        # Сырьё: берём со склада сколько нужно (с учётом эффективности).
        # Если чего-то не хватает — работаем на ту долю, на которую хватило.
        if item.consumes and efficiency > 0:
            ratio = 1.0
            for resource, amount in item.consumes.items():
                need = amount * efficiency
                ratio = min(ratio, self.stock[resource] / need)
            for resource, amount in item.consumes.items():
                taken = amount * efficiency * ratio
                self.stock[resource] -= taken
                report.consumed[resource] += taken
            efficiency *= ratio
            if ratio < 0.999:
                b.problems.append("inputs")  # не хватает сырья — значок «ящик»

        # Продукция — на склад, но не больше его вместимости
        for resource, amount in item.produces.items():
            made = amount * efficiency
            self.stock[resource] = min(self.stats.storage, self.stock[resource] + made)
            report.produced[resource] += made

        b.efficiency = efficiency
        return item.income * efficiency

    # --- Подсказки для строительства ---

    def site_warning(self, item: ShopItem, x: int, y: int) -> str | None:
        """Хватит ли зданию света и воды, если поставить его в (x, y)? None — хватит."""
        width, height = item.size
        districts = self.infrastructure.districts_near(x, y, width, height)
        if item.power_use:
            spare = max((d.power_spare for d in districts), default=0)
            if spare < item.power_use:
                return f"В районе не хватает электричества: нужно {item.power_use}, свободно {max(0, spare)}"
        if item.water_use:
            spare = max((d.water_spare for d in districts), default=0)
            if spare < item.water_use:
                return f"В районе не хватает воды: нужно {item.water_use}, свободно {max(0, spare)}"
        return None

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

