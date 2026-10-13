"""Подсказка о здании при наведении курсора (когда ничего не строим и не сносим).

    ┌─────────────────────────────────┐
    │ Завод                           │
    │ Не работает: нет электричества  │  <- или «Работает» (зелёным)
    │ Эффективность: 0%               │
    │ Древесина: −6 → Товары: +12     │
    │ Энергия: −25 · Вода: −10        │
    │ Загрязнение: −25 (радиус 4)     │
    └─────────────────────────────────┘

Так игрок видит, ПОЧЕМУ здание не работает и что ему нужно.
"""

import pygame

from city_builder.config import (
    COLOR_MENU_PANEL,
    COLOR_MONEY_NEGATIVE,
    COLOR_MONEY_POSITIVE,
    COLOR_POWER,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_UI_BORDER,
    COLOR_WARNING,
    COLOR_WATER,
    RESOURCE_NAMES,
    UI_BORDER_RADIUS,
)
from city_builder.economy.networks import Infrastructure
from city_builder.world.building import Building

PADDING = 10
PROBLEM_TEXTS = {
    "road": "нет дороги",
    "power": "нет электричества",
    "water": "нет воды",
}

Color = tuple[int, int, int]


def _problem_text(b: Building, problem: str, networks: Infrastructure | None) -> str:
    """Точная причина: нет подключения к сети вообще или сети не хватает мощности."""
    if problem == "power" and networks is not None:
        net = networks.power.get(b.power_net) if b.power_net is not None else None
        return "в электросети не хватает энергии" if net and net.supply else "нет линии электропередач рядом"
    if problem == "water" and networks is not None:
        return "в водопроводе не хватает воды" if b.water_net is not None else "нет водопровода рядом"
    return PROBLEM_TEXTS[problem]


def building_lines(b: Building, networks: Infrastructure | None = None) -> list[tuple[str, Color]]:
    """Строки подсказки о здании: (текст, цвет)."""
    item = b.item
    lines: list[tuple[str, Color]] = [(item.name, COLOR_TEXT)]

    # --- Работает или нет и почему ---
    blocking = [_problem_text(b, p, networks) for p in b.problems if p in PROBLEM_TEXTS]
    if blocking:
        lines.append(("Не работает: " + ", ".join(blocking), COLOR_MONEY_NEGATIVE))
    elif item.workers or item.consumes or item.produces:
        color = COLOR_MONEY_POSITIVE if b.efficiency > 0.95 else COLOR_WARNING
        lines.append((f"Работает на {round(b.efficiency * 100)}%", color))
        if "inputs" in b.problems:
            missing = ", ".join(RESOURCE_NAMES[r] for r in item.consumes)
            lines.append((f"Не хватает сырья: {missing}", COLOR_WARNING))
    else:
        lines.append(("Работает", COLOR_MONEY_POSITIVE))

    # --- Что даёт ---
    if item.housing:
        lines.append((f"Жильё: {item.housing} · Счастье: {round(b.happiness)}%", COLOR_TEXT_DIM))
        if b.congestion > 1:
            lines.append((f"Пробки по дороге на работу: ×{b.congestion:.1f}", COLOR_MONEY_NEGATIVE))
        elif b.congestion > 0.6:
            lines.append(("Дорога на работу загружена", COLOR_WARNING))
    if item.workers:
        lines.append((f"Рабочих мест: {item.workers}", COLOR_TEXT_DIM))
    if item.consumes or item.produces:
        parts = [f"{RESOURCE_NAMES[r]} −{n}" for r, n in item.consumes.items()]
        made = [f"{RESOURCE_NAMES[r]} +{n}" for r, n in item.produces.items()]
        lines.append((" → ".join(filter(None, [", ".join(parts), ", ".join(made)])) + " за тик", COLOR_TEXT_DIM))
    if item.storage:
        lines.append((f"Склад: +{item.storage} каждого ресурса", COLOR_TEXT_DIM))

    # --- Энергия и вода ---
    if item.power_output:
        lines.append((f"Даёт энергию: {item.power_output}", COLOR_POWER))
    if item.water_output:
        lines.append((f"Даёт воду: {item.water_output}", COLOR_WATER))
    utilities = []
    if item.power_use:
        utilities.append(f"энергия {item.power_use}")
    if item.water_use:
        utilities.append(f"вода {item.water_use}")
    if utilities:
        lines.append(("Потребляет: " + ", ".join(utilities), COLOR_TEXT_DIM))

    # --- Влияние на счастье соседей ---
    if item.happiness > 0:
        lines.append((f"Счастье вокруг: +{item.happiness} (радиус {item.radius})", COLOR_MONEY_POSITIVE))
    elif item.happiness < 0:
        lines.append((f"Загрязнение: {item.happiness} (радиус {item.radius})", COLOR_MONEY_NEGATIVE))
    return lines


class BuildingInfo:
    def __init__(self, screen_size: tuple[int, int]) -> None:
        self.screen_size = screen_size
        self.building: Building | None = None
        self.networks: Infrastructure | None = None  # для точных причин «нет света / воды»
        self.mouse_pos = (0, 0)
        self.title_font = pygame.font.SysFont("consolas", 15, bold=True)
        self.font = pygame.font.SysFont("consolas", 14)

    def update(self, building: Building | None, mouse_pos: tuple[int, int]) -> None:
        self.building = building
        self.mouse_pos = mouse_pos

    def draw(self, screen: pygame.Surface) -> None:
        if self.building is None:
            return
        lines = building_lines(self.building, self.networks)
        surfaces = [(self.title_font if i == 0 else self.font).render(text, True, color)
                    for i, (text, color) in enumerate(lines)]
        width = max(s.get_width() for s in surfaces) + 2 * PADDING
        height = sum(s.get_height() + 2 for s in surfaces) + 2 * PADDING
        # Справа-снизу от курсора; если не помещается — с другой стороны
        x, y = self.mouse_pos[0] + 18, self.mouse_pos[1] + 18
        if x + width > self.screen_size[0]:
            x = self.mouse_pos[0] - width - 10
        if y + height > self.screen_size[1]:
            y = self.mouse_pos[1] - height - 10
        box = pygame.Rect(x, y, width, height)
        pygame.draw.rect(screen, COLOR_MENU_PANEL, box, border_radius=UI_BORDER_RADIUS)
        pygame.draw.rect(screen, COLOR_UI_BORDER, box, 1, border_radius=UI_BORDER_RADIUS)
        ty = box.top + PADDING
        for surface in surfaces:
            screen.blit(surface, (box.left + PADDING, ty))
            ty += surface.get_height() + 2
