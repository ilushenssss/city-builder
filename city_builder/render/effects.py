"""Визуальные эффекты: дым из труб, пыль, «вырастающие» здания, всплывающие числа, тени облаков.

Всё это — только для красоты и «отклика» игры на действия игрока:
  * построили здание — оно «вырастает» из земли с подпрыгиванием, поднимается пыль,
    всплывает «−50» (сколько заплатили);
  * снесли — облако пыли и «+25» (сколько вернулось);
  * у завода и электростанции из труб идёт дым и пар;
  * на каждом тике над магазинами и предприятиями всплывают монетки дохода;
  * по городу медленно ползут тени облаков.

Как модуль узнаёт о постройке и сносе: сравнивает список зданий сейчас и раньше
(когда меняется grid.version). Поэтому строительству и сносу не нужно ничего
сообщать эффектам — модули не связаны между собой.

Время: дым, пыль и облака живут в игровом времени (на паузе замирают),
а анимация постройки и всплывающие числа — в реальном (видны и на паузе).
"""

from __future__ import annotations

from typing import Tuple

import math
import random
from dataclasses import dataclass

import pygame

from city_builder.config import (
    BUILD_ANIMATION,
    CLOUD_COUNT,
    CLOUD_SPEED,
    COLOR_MONEY_NEGATIVE,
    COLOR_MONEY_POSITIVE,
    COLOR_PRICE,
    FLOAT_TEXT_TIME,
    FLOOR_HEIGHT,
    INCOME_POPUPS_PER_TICK,
    SMOKE_EMITTERS,
    SMOKE_INTERVAL,
)
from city_builder.economy.economy import Economy
from city_builder.render import iso
from city_builder.world.building import Building
from city_builder.world.grid import Grid

Color = Tuple[int, int, int]


@dataclass
class Particle:
    """Клуб дыма или пыли. x, y — клетки карты; z — высота в единицах чертежа."""
    x: float
    y: float
    z: float
    vx: float           # скорость по x (клеток в секунду) — ветер
    vz: float           # скорость подъёма (единиц чертежа в секунду)
    r0: float           # радиус в начале и в конце жизни (единицы чертежа)
    r1: float
    life: float         # сколько секунд живёт
    color: Color
    alpha: int          # начальная непрозрачность
    age: float = 0.0


@dataclass
class FloatText:
    """Всплывающее число («+25»): поднимается и тает."""
    x: float
    y: float
    z: float
    surface: pygame.Surface
    age: float = 0.0


@dataclass
class Cloud:
    """Тень облака: эллипс в координатах мира (пиксели при zoom = 1)."""
    x: float
    y: float
    width: float
    height: float


class Effects:
    def __init__(self, grid: Grid, economy: Economy, seed: int | None = None) -> None:
        self.grid = grid
        self.economy = economy
        self.rng = random.Random(seed)
        self.particles: list[Particle] = []
        self.texts: list[FloatText] = []
        self.growing: dict[Building, float] = {}  # здание -> сколько секунд «растёт»
        self._known: set[Building] = set(grid.buildings)
        self._version = grid.version
        self._smoke_timer = 0.0
        self.font = pygame.font.SysFont("consolas", 18, bold=True)
        # Тени облаков — разбрасываем над картой
        left, top, right, bottom = iso.map_bounds(grid.width, grid.height)
        self._bounds = (left, top, right, bottom)
        self.clouds = [Cloud(self.rng.uniform(left, right), self.rng.uniform(top, bottom),
                             self.rng.uniform(500, 900), self.rng.uniform(220, 380))
                       for _ in range(CLOUD_COUNT)]

    # --- Каждый кадр ---

    def update(self, real_dt: float, game_dt: float) -> None:
        if self._version != self.grid.version:
            self._version = self.grid.version
            self._detect_changes()

        # Анимация постройки и всплывающие числа — в реальном времени
        for building in list(self.growing):
            self.growing[building] += real_dt
            if self.growing[building] >= BUILD_ANIMATION:
                del self.growing[building]
        for text in self.texts:
            text.age += real_dt
        self.texts = [t for t in self.texts if t.age < FLOAT_TEXT_TIME]

        if game_dt <= 0:
            return  # пауза: дым и облака замирают
        self._emit_smoke(game_dt)
        for p in self.particles:
            p.age += game_dt
            p.x += p.vx * game_dt
            p.z += p.vz * game_dt
        self.particles = [p for p in self.particles if p.age < p.life]
        left, _, right, _ = self._bounds
        for cloud in self.clouds:
            cloud.x += CLOUD_SPEED * game_dt
            if cloud.x - cloud.width / 2 > right:  # улетело за край — возвращаем слева
                cloud.x = left - cloud.width / 2

    # --- Постройка и снос ---

    def _detect_changes(self) -> None:
        current = set(self.grid.buildings)
        for building in current - self._known:  # построили
            self.growing[building] = 0.0
            self._dust(building, count=8)
            self._float_text(building, f"−{building.item.price}", COLOR_MONEY_NEGATIVE)
        for building in self._known - current:  # снесли
            self.growing.pop(building, None)
            self._dust(building, count=16, big=True)
            self._float_text(building, f"+{Economy.refund_for(building.item)}", COLOR_MONEY_POSITIVE)
        self._known = current

    def build_scale(self, building: Building) -> float:
        """Во сколько раз «вытянуть» здание по высоте прямо сейчас: от ~0 до 1,
        с небольшим «перелётом» (1.08) — так постройка выглядит упругой."""
        if building not in self.growing:
            return 1.0
        t = min(1.0, self.growing[building] / BUILD_ANIMATION)
        # «easeOutBack» — быстрый рост с перелётом и возвратом к 1
        c = 1.6
        return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

    def _dust(self, building: Building, count: int, big: bool = False) -> None:
        for _ in range(count):
            self.particles.append(Particle(
                x=building.x + self.rng.uniform(0, building.width),
                y=building.y + self.rng.uniform(0, building.height),
                z=self.rng.uniform(0, 6), vx=self.rng.uniform(-0.15, 0.15),
                vz=self.rng.uniform(10, 25), r0=self.rng.uniform(5, 9),
                r1=self.rng.uniform(16, 26) * (1.5 if big else 1), life=self.rng.uniform(0.8, 1.4),
                color=(200, 185, 160), alpha=170))

    def _float_text(self, building: Building, text: str, color: Color) -> None:
        z = building.item.floors * FLOOR_HEIGHT + 20
        surface = self._render_text(text, color)
        self.texts.append(FloatText(building.x + building.width / 2, building.y + building.height / 2, z, surface))

    def _render_text(self, text: str, color: Color) -> pygame.Surface:
        """Текст с тёмной обводкой — читается и на светлой крыше, и на траве."""
        main = self.font.render(text, True, color)
        outline = self.font.render(text, True, (25, 25, 30))
        surface = pygame.Surface((main.get_width() + 2, main.get_height() + 2), pygame.SRCALPHA)
        for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
            surface.blit(outline, (dx, dy))
        surface.blit(main, (1, 1))
        return surface

    # --- Дым ---

    def _emit_smoke(self, dt: float) -> None:
        self._smoke_timer += dt
        if self._smoke_timer < SMOKE_INTERVAL:
            return
        self._smoke_timer = 0.0
        for building in self.grid.buildings:
            emitters = SMOKE_EMITTERS.get(building.item.id)
            if not emitters or not building.working or building.efficiency <= 0:
                continue  # труба дымит, только когда здание работает
            for cx, cy, z in emitters:
                steam = building.item.id == "power_plant"  # градирни — белый пар, завод — серый дым
                self.particles.append(Particle(
                    x=building.x + cx, y=building.y + cy, z=z,
                    vx=self.rng.uniform(0.08, 0.18), vz=self.rng.uniform(16, 24),
                    r0=self.rng.uniform(6, 9), r1=self.rng.uniform(22, 30), life=self.rng.uniform(2.5, 3.5),
                    color=(240, 240, 245) if steam else (150, 150, 155), alpha=200 if steam else 170))

    # --- Доход ---

    def on_tick(self) -> None:
        """После тика экономики: над работающими предприятиями всплывают монетки дохода."""
        earners = [b for b in self.grid.buildings if b.item.income and b.working and b.efficiency > 0.05]
        for building in self.rng.sample(earners, min(len(earners), INCOME_POPUPS_PER_TICK)):
            amount = round(building.item.income * building.efficiency)
            if amount > 0:
                self._float_text(building, f"+{amount}", COLOR_PRICE)

    # --- Для отрисовки ---

    @staticmethod
    def particle_state(p: Particle) -> tuple[float, int]:
        """(радиус в единицах чертежа, непрозрачность) частицы в текущий момент."""
        t = p.age / p.life
        radius = p.r0 + (p.r1 - p.r0) * math.sqrt(t)
        alpha = int(p.alpha * (1 - t) ** 1.5)
        return radius, alpha
