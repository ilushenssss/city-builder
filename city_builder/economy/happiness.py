"""Счастье жителей.

У каждого жилого дома своё счастье от 0 до 100:

    счастье = BASE_HAPPINESS (50)
            + сумма «happiness» всех работающих зданий, в радиус которых попадает дом
    (парк +10, школа +15, больница +20 ... завод −25, электростанция −20)

Результат обрезается до 0–100. Счастье города — среднее по домам
(большие дома весят больше: в многоэтажке больше жителей, чем в домике).

На что влияет (см. Economy.tick):
  * скорость заселения: при счастье 100 — вдвое быстрее, при 25 — вдвое медленнее;
  * если счастье города ниже UNHAPPY_LEVEL — жители уезжают.

Поэтому завод лучше ставить подальше от домов, а парк и школу — поближе.
"""

from city_builder.config import BASE_HAPPINESS
from city_builder.world.building import Building


def distance(a: Building, b: Building) -> int:
    """Расстояние в клетках между краями двух зданий (0 — стоят вплотную).

    Считаем «по-шахматному» (как ходит король): по x и по y отдельно,
    берём большее. Так радиус действия — квадрат вокруг здания.
    """
    dx = max(0, b.x - (a.x + a.width - 1), a.x - (b.x + b.width - 1))
    dy = max(0, b.y - (a.y + a.height - 1), a.y - (b.y + b.height - 1))
    return max(dx, dy)


def compute_happiness(buildings: list[Building]) -> float:
    """Посчитать счастье каждого дома (building.happiness) и вернуть счастье города."""
    sources = [b for b in buildings if b.item.happiness and b.working]
    homes = [b for b in buildings if b.item.housing > 0]

    total, weight = 0.0, 0
    for home in homes:
        value = BASE_HAPPINESS
        for source in sources:
            if distance(home, source) <= source.item.radius:
                value += source.item.happiness
        home.happiness = max(0, min(100, value))
        if home.working:
            total += home.happiness * home.item.housing
            weight += home.item.housing
    return total / weight if weight else BASE_HAPPINESS
