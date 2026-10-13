"""Отрисовка мира в изометрии (вид под углом).

Renderer только рисует: он читает данные (Grid, Camera, BuildMode, жители),
но ничего в них не меняет. Вся игровая логика живёт в других модулях.

Слои (снизу вверх):
  0. Море вокруг карты (градиент).
  1. Земля: трава нескольких оттенков и вода (анимированная, с песчаными берегами).
  2. Дороги — плоские, лежат на земле, поэтому рисуются сразу после неё.
  3. Здания, деревья, машины и жители — ВПЕРЕМЕШКУ, отсортированные по «глубине»
     (x + y): сначала дальние, потом ближние. Так ближний дом закрывает человечка
     за ним, а человечек перед домом — виден. Это «алгоритм художника»:
     художник тоже пишет сначала задний план, потом передний.
  4. Эффекты: дым и пыль, тени облаков, всплывающие числа (render/effects.py).
  5. Призрак строительства и подсветка сноса — поверх всего (рисуются отдельно).

Сети: столбы ЛЭП с проводами и светофоры стоят «в мире» и сортируются вместе
со зданиями. Водопровод — под землёй: виден только в режиме просмотра «Вода».

Режимы просмотра (view): обычный, «Электричество» (здания без света — красные,
провода светятся), «Вода» (трубы и зона, куда дотягивается вода), «Пробки»
(дороги раскрашены: зелёные — свободно, жёлтые — плотно, красные — пробка).

Как рисует pygame: есть «поверхность» (Surface) окна — по сути картинка
в памяти. Мы рисуем на ней спрайты и текст, а в конце кадра GameLoop
вызывает pygame.display.flip(), и картинка появляется на экране.
"""

import math

import pygame

from city_builder.citizens.citizens import CitizenManager, Walker
from city_builder.citizens.vehicles import Car, TrafficManager, signal_state
from city_builder.config import (
    COLOR_SEA_BOTTOM,
    COLOR_SEA_TOP,
    COLOR_TRAFFIC,
    POWER_POLE_HEIGHT,
    VIEW_NORMAL,
    VIEW_POWER,
    VIEW_TRAFFIC,
    VIEW_WATER,
    COLOR_DEMOLISH,
    COLOR_GHOST_BAD,
    COLOR_GHOST_OK,
    COLOR_GHOST_PENDING,
    COLOR_HOVER,
    COLOR_TEXT,
    DEMOLISH_HOVER_TINT,
    DEMOLISH_TARGET_TINT,
    FLAT_CATEGORIES,
    FLOAT_TEXT_TIME,
    GHOST_ALPHA,
    ISO_TILE_HEIGHT,
    ISO_TILE_WIDTH,
    NO_ROAD_TINT,
    PROBLEM_COLORS,
    TILE_COLORS,
    WATER_FRAME_TIME,
    WORLD_SCALE,
)
from city_builder.construction.build_mode import BuildMode, BuildState
from city_builder.construction.demolish_mode import DemolishMode, DemolishState
from city_builder.data.catalog import ShopItem
from city_builder.economy.economy import Economy
from city_builder.render import iso
from city_builder.render.camera import Camera
from city_builder.render.effects import Effects
from city_builder.render.images import ImageLibrary
from city_builder.render.iso_sprites import DTW, road_mask
from city_builder.world.building import Building
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile, TileType

# Высота в единицах чертежа -> пиксели мира (ромб чертежа 128 px = клетка мира)
DESIGN_TO_WORLD = ISO_TILE_WIDTH / DTW

SKIN = (240, 200, 160)  # цвет лица человечков
CLOUD_BASE = (128, 56)  # маленькая заготовка тени облака (размывается один раз)
POLE_SPOT = (0.2, 0.2)    # где на клетке стоит столб ЛЭП (у дальнего угла — не мешает дороге)
SIGNAL_SPOT = (0.85, 0.15)  # где на перекрёстке стоит светофор (у правого угла)
WIRE = (40, 40, 46)       # цвет проводов
WIRE_LIT = (255, 215, 70)  # провода в режиме «Электричество»
PIPE = (70, 150, 230)
LAMP = {"red": (235, 55, 45), "yellow": (250, 200, 50), "green": (70, 225, 95)}
# Тонировка зданий в режимах просмотра (цвет умножается на этот)
TINT_PROBLEM = (255, 110, 110)   # нет света / нет воды
TINT_OK = (200, 255, 200)        # всё есть
TINT_NEUTRAL = (150, 150, 160)   # зданию это не нужно — приглушаем


def is_flat(building: Building) -> bool:
    """Плоские объекты (дороги) лежат на земле и рисуются отдельным слоем."""
    return building.item.category in FLAT_CATEGORIES


class Renderer:
    def __init__(self, screen: pygame.Surface, images: ImageLibrary) -> None:
        self.screen = screen  # поверхность окна, на которой рисуем
        self.images = images  # спрайты зданий и местности (с кэшем)
        # Шрифт загружаем один раз здесь, а не каждый кадр — это медленно.
        self.font = pygame.font.SysFont("consolas", 16)
        # Что где нарисовано в последнем кадре: (прямоугольник, картинка, здание).
        # По этому списку pick_building() узнаёт, на какое здание указывает курсор.
        self._hits: list[tuple[pygame.Rect, pygame.Surface, Building]] = []
        self._shadow_cache: dict[int, pygame.Surface] = {}
        # Маски соседей дорог: пересчитываем только после постройки/сноса (grid.version)
        self._road_masks: dict[Building, int] = {}
        self._road_masks_version = -1
        # Берега: для каждой клетки воды — с каких сторон суша (считаем один раз на карту)
        self._shore_masks: dict[tuple[int, int], int] = {}
        self._shore_grid_id = -1
        self._sea: pygame.Surface | None = None             # фон-море (градиент)
        self._puffs: dict[tuple[int, tuple], pygame.Surface] = {}   # мягкие круги дыма
        self._clouds: dict[tuple[int, int], pygame.Surface] = {}    # тени облаков
        self._puffs_misc: dict[str, pygame.Surface] = {}             # заготовка облака
        self.effects: Effects | None = None  # эффекты текущей партии (передаются в draw)
        self.view = VIEW_NORMAL               # режим просмотра (передаётся в draw)
        self.economy: Economy | None = None
        self.traffic: TrafficManager | None = None
        self._diamonds: dict[tuple, pygame.Surface] = {}  # полупрозрачные ромбы для режимов

    # --- Геометрия: где на экране клетка и спрайт ---

    def screen_point(self, camera: Camera, tx: float, ty: float) -> tuple[float, float]:
        """Точка клетки (может быть дробной) -> пиксель экрана."""
        return camera.world_to_screen(*iso.tile_to_world(tx, ty))

    def footprint_points(self, camera: Camera, x: float, y: float,
                         width: float, height: float) -> list[tuple[float, float]]:
        """Четыре угла ромба области клеток на экране (для рамок)."""
        return [camera.world_to_screen(wx, wy) for wx, wy in iso.footprint_corners(x, y, width, height)]

    def sprite_rect(self, camera: Camera, x: int, y: int, width: int, height: int,
                    sprite: pygame.Surface) -> pygame.Rect:
        """Где на экране нарисовать спрайт здания w × h, стоящего в клетке (x, y).

        Ширина спрайта = ширине ромба основания; нижний край спрайта = нижний
        угол ромба. Высота — пропорционально картинке (высокие здания — выше).
        """
        left, top, box_w, box_h = iso.footprint_box(x, y, width, height)
        sl, sb = camera.world_to_screen(left, top + box_h)
        sr, _ = camera.world_to_screen(left + box_w, top + box_h)
        rect_w = max(1, round(sr) - round(sl))
        rect_h = max(1, round(sprite.get_height() * rect_w / sprite.get_width()))
        return pygame.Rect(round(sl), round(sb) - rect_h, rect_w, rect_h)

    def item_sprite_rect(self, camera: Camera, item: ShopItem, x: int, y: int) -> tuple[pygame.Surface, pygame.Rect]:
        sprite = self.images.sprite(item)
        width, height = item.size
        return sprite, self.sprite_rect(camera, x, y, width, height, sprite)

    # --- Главная отрисовка ---

    def draw(self, grid: Grid, camera: Camera, citizens: CitizenManager | None = None,
             traffic: TrafficManager | None = None, effects: Effects | None = None,
             economy: Economy | None = None, view: str = VIEW_NORMAL) -> None:
        """Нарисовать всё: море, землю, дороги, сети, здания, природу, машины, жителей, эффекты."""
        self.screen.blit(self._sea_background(), (0, 0))  # стираем прошлый кадр — морем
        self._hits = []
        self.effects, self.economy, self.traffic, self.view = effects, economy, traffic, view
        decor, poles, signals, visible = self._draw_terrain(grid, camera)
        self._draw_roads(grid, camera)
        if view == VIEW_TRAFFIC and economy:
            self._draw_congestion(grid, camera, economy)
        if view == VIEW_WATER and economy:
            self._draw_water_cover(camera, economy, visible)
        self._draw_buildings_and_walkers(grid, camera, citizens, traffic, decor, poles, signals)
        if view == VIEW_WATER:
            self._draw_pipes(grid, camera, visible)  # трубы под землёй — показываем поверх всего
        if effects:
            self._draw_effects(effects, camera)

    def _sea_background(self) -> pygame.Surface:
        """Море вокруг карты: вертикальный градиент. Рисуем один раз под размер окна."""
        size = self.screen.get_size()
        if self._sea is None or self._sea.get_size() != size:
            self._sea = pygame.Surface(size)
            for y in range(size[1]):
                t = y / max(1, size[1] - 1)
                color = tuple(int(a + (b - a) * t) for a, b in zip(COLOR_SEA_TOP, COLOR_SEA_BOTTOM))
                pygame.draw.line(self._sea, color, (0, y), (size[0], y))
        return self._sea

    def _visible_tile_range(self, grid: Grid, camera: Camera) -> tuple[range, range]:
        """Какие клетки могут попасть на экран: переводим углы экрана в клетки.

        В изометрии видимая часть карты — «ромб» в координатах клеток, поэтому
        берём описанный вокруг него прямоугольник (несколько лишних клеток — не страшно).
        """
        width, height = self.screen.get_size()
        corners = [iso.world_to_tile(*camera.screen_to_world(sx, sy))
                   for sx, sy in ((0, 0), (width, 0), (0, height), (width, height))]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        x0 = max(0, math.floor(min(xs)) - 1)
        x1 = min(grid.width, math.ceil(max(xs)) + 1)
        y0 = max(0, math.floor(min(ys)) - 1)
        y1 = min(grid.height, math.ceil(max(ys)) + 1)
        return range(x0, x1), range(y0, y1)

    def _shore_mask(self, grid: Grid, x: int, y: int) -> int:
        """С каких сторон у клетки воды суша (маска как у дорог). Край карты — не берег."""
        def land(dx: int, dy: int) -> bool:
            tile = grid.get(x + dx, y + dy)
            return tile is not None and tile.type != TileType.WATER
        return road_mask(land)

    def _draw_terrain(self, grid: Grid, camera: Camera) -> tuple[list[Tile], list[Tile], list[Tile], list[Tile]]:
        """Слой 1: трава и вода. Возвращает видимые клетки: с природой, со столбами ЛЭП,
        со светофорами и все видимые — их нарисуем потом (вместе со зданиями или поверх)."""
        if self._shore_grid_id != id(grid):  # новая карта — пересчитываем берега
            self._shore_grid_id = id(grid)
            self._shore_masks = {(t.x, t.y): self._shore_mask(grid, t.x, t.y)
                                 for t in grid if t.type == TileType.WATER}
        # Подложка всей карты цветом травы — чтобы между ромбами не было щелей
        pygame.draw.polygon(self.screen, TILE_COLORS["grass"],
                            self.footprint_points(camera, 0, 0, grid.width, grid.height))

        # Размер ромба на экране и шаги: сдвиг на клетку по x и по y.
        # Считаем один раз на кадр, а не для каждой клетки — так в разы быстрее.
        hw = ISO_TILE_WIDTH / 2 * camera.zoom
        hh = ISO_TILE_HEIGHT / 2 * camera.zoom
        tile_size = (math.ceil(hw * 2) + 1, math.ceil(hh * 2) + 1)  # +1 — небольшой нахлёст, без щелей
        grass = [self.images.scaled(self.images.grass(v), tile_size) for v in range(4)]
        # Кадр анимации воды. Каждой клетке — свой сдвиг (x·3 + y·5), чтобы блики
        # «бежали» по воде волной, а не мигали все разом.
        frame = int(pygame.time.get_ticks() / 1000 / WATER_FRAME_TIME)
        ox, oy = camera.world_to_screen(0, 0)  # верхний угол клетки (0, 0) на экране
        screen_w, screen_h = self.screen.get_size()

        # blits() рисует много картинок одним вызовом — быстрее, чем blit() в цикле
        batch = []
        decor: list[Tile] = []
        poles: list[Tile] = []
        signals: list[Tile] = []
        visible: list[Tile] = []
        xs, ys = self._visible_tile_range(grid, camera)
        for y in ys:
            row = grid.tiles[y]
            for x in xs:
                sx = ox + (x - y) * hw - hw
                sy = oy + (x + y) * hh
                tile = row[x]
                # Деревья, столбы и светофоры видны и чуть за краем ромба — собираем до отсечения
                if tile.decor:
                    decor.append(tile)
                if tile.power_line is not None:
                    poles.append(tile)
                if tile.signal is not None:
                    signals.append(tile)
                if sx > screen_w or sy > screen_h or sx + tile_size[0] < 0 or sy + tile_size[1] < 0:
                    continue  # ромб целиком за краем экрана
                if tile.type == TileType.WATER:
                    sprite = self.images.scaled(
                        self.images.water(self._shore_masks.get((x, y), 0), (frame + x * 3 + y * 5) % 4), tile_size)
                else:
                    sprite = grass[tile.variant % 4]
                batch.append((sprite, (round(sx), round(sy))))
                visible.append(tile)
        self.screen.blits(batch, doreturn=False)
        return decor, poles, signals, visible

    def _draw_roads(self, grid: Grid, camera: Camera) -> None:
        """Слой 2: плоские дороги.

        У каждой дороги 16 вариантов картинки — по тому, с каких сторон есть
        соседние дороги (маска соседей, см. iso_sprites.road_mask). Так тротуары
        идут только по краям улицы, а разметка поворачивает на перекрёстках.
        """
        if self._road_masks_version != grid.version:
            self._road_masks_version = grid.version
            self._road_masks = {
                b: road_mask(lambda dx, dy, b=b: grid.is_road(b.x + dx, b.y + dy))
                for b in grid.buildings if is_flat(b)
            }
        screen_rect = self.screen.get_rect()
        for building, mask in self._road_masks.items():
            sprite = self.images.road_sprite(building.item, mask)
            rect = self.sprite_rect(camera, building.x, building.y, 1, 1, sprite)
            if rect.colliderect(screen_rect):
                scaled = self.images.scaled(sprite, rect.size)
                self.screen.blit(scaled, rect)
                self._hits.append((rect, scaled, building))

    def _draw_buildings_and_walkers(self, grid: Grid, camera: Camera, citizens: CitizenManager | None,
                                    traffic: TrafficManager | None, decor: list[Tile],
                                    poles: list[Tile], signals: list[Tile]) -> None:
        """Слой 3: здания, природа, столбы, светофоры, машины и жители — от дальних к ближним."""
        # Список (глубина, порядок, объект). Порядок нужен, чтобы при равной глубине
        # здание рисовалось раньше человечка, — и чтобы Python не пытался сравнивать
        # сами объекты (это вызвало бы ошибку).
        drawables: list[tuple[float, int, object]] = []
        for building in grid.buildings:
            if not is_flat(building):
                # Глубина здания — по его самой ближней клетке (передний угол)
                depth = iso.depth(building.x + building.width - 0.5, building.y + building.height - 0.5)
                drawables.append((depth, 0, building))
        for tile in decor:
            drawables.append((iso.depth(tile.x + 0.5, tile.y + 0.5), 0, tile))
        # Столбы и светофоры — кортежи («что», клетка), чтобы отличить их от деревьев
        for tile in poles:
            drawables.append((iso.depth(tile.x + POLE_SPOT[0], tile.y + POLE_SPOT[1]), 0, ("pole", tile)))
        for tile in signals:
            drawables.append((iso.depth(tile.x + SIGNAL_SPOT[0], tile.y + SIGNAL_SPOT[1]), 1, ("signal", tile)))
        if traffic:
            for car in traffic.cars:
                drawables.append((iso.depth(car.x, car.y), 1, car))
        if citizens:
            for walker in citizens.visible_walkers():
                drawables.append((iso.depth(walker.x, walker.y), 1, walker))
        drawables.sort(key=lambda d: (d[0], d[1]))  # сортировка по глубине

        screen_rect = self.screen.get_rect()
        for _, _, obj in drawables:
            if isinstance(obj, Building):
                self._draw_building(obj, camera, screen_rect)
            elif isinstance(obj, Tile):
                self._draw_decor(obj, camera, screen_rect)
            elif isinstance(obj, Car):
                self._draw_car(obj, camera, screen_rect)
            elif isinstance(obj, tuple):
                kind, tile = obj
                if kind == "pole":
                    self._draw_pole(grid, tile, camera)
                else:
                    self._draw_signal(tile, camera)
            else:
                self._draw_walker(obj, camera)

    def _draw_decor(self, tile: Tile, camera: Camera, screen_rect: pygame.Rect) -> None:
        """Дерево, ёлка, куст, цветы или камень на клетке."""
        assert tile.decor is not None
        sprite = self.images.decor(tile.decor, tile.variant % 3)
        rect = self.sprite_rect(camera, tile.x, tile.y, 1, 1, sprite)
        if rect.colliderect(screen_rect):
            self.screen.blit(self.images.scaled(sprite, rect.size), rect)

    def _draw_car(self, car: Car, camera: Camera, screen_rect: pygame.Rect) -> None:
        """Машина: спрайт клетки с машиной в центре — ставим его центром в точку машины."""
        sprite = self.images.car(car.color, car.along)
        rect = self.sprite_rect(camera, car.x - 0.5, car.y - 0.5, 1, 1, sprite)  # type: ignore[arg-type]
        if rect.colliderect(screen_rect):
            self.screen.blit(self.images.scaled(sprite, rect.size), rect)

    def _draw_building(self, building: Building, camera: Camera, screen_rect: pygame.Rect) -> None:
        sprite, rect = self.item_sprite_rect(camera, building.item, building.x, building.y)
        if not rect.colliderect(screen_rect):
            return  # здание за краем экрана
        # Только что построенное здание «вырастает» из земли: тянем картинку по высоте,
        # нижний край остаётся на месте
        grow = self.effects.build_scale(building) if self.effects else 1.0
        if grow != 1.0:
            height = max(1, round(rect.height * grow))
            rect = pygame.Rect(rect.left, rect.bottom - height, rect.width, height)
        tint = self._view_tint(building)
        scaled = self.images.scaled(sprite, rect.size, tint=tint)
        self.screen.blit(scaled, rect)
        self._hits.append((rect, scaled, building))
        if building.problems:
            # Значок первой (главной) проблемы над зданием
            self._draw_problem_badge(rect, building.problems[0], camera)

    def _view_tint(self, building: Building) -> tuple[int, int, int] | None:
        """Тонировка здания: в режимах «Электричество» и «Вода» — есть или нет,
        в обычном — неработающее здание темнее."""
        item = building.item
        if self.view == VIEW_POWER:
            if not item.power_use and not item.power_output:
                return TINT_NEUTRAL
            return TINT_OK if building.powered else TINT_PROBLEM
        if self.view == VIEW_WATER:
            if not item.water_use and not item.water_output:
                return TINT_NEUTRAL
            return TINT_OK if building.watered else TINT_PROBLEM
        return None if building.working else NO_ROAD_TINT

    def _draw_problem_badge(self, rect: pygame.Rect, problem: str, camera: Camera) -> None:
        """Цветной кружок со значком над зданием:
        «!» — нет дороги, молния — нет света, капля — нет воды, ящик — нет сырья."""
        r = max(6, round(8 * camera.zoom * WORLD_SCALE))
        cx, cy = rect.centerx, rect.top + r
        white = (255, 255, 255)
        pygame.draw.circle(self.screen, PROBLEM_COLORS[problem], (cx, cy), r)
        pygame.draw.circle(self.screen, white, (cx, cy), r, 1)
        u = r / 8  # «единица» — все размеры значка в долях радиуса
        if problem == "road":
            # Восклицательный знак: чёрточка и точка
            pygame.draw.line(self.screen, white, (cx, cy - 4 * u), (cx, cy + 1 * u), max(2, round(2 * u)))
            pygame.draw.circle(self.screen, white, (cx, cy + 4 * u), max(1, round(1.2 * u)))
        elif problem == "power":
            # Молния — ломаная из шести точек
            bolt = [(cx + 1 * u, cy - 6 * u), (cx - 3 * u, cy + 1 * u), (cx, cy + 1 * u),
                    (cx - 1 * u, cy + 6 * u), (cx + 3 * u, cy - 1 * u), (cx, cy - 1 * u)]
            pygame.draw.polygon(self.screen, white, bolt)
        elif problem == "water":
            # Капля — круг снизу и треугольник сверху
            pygame.draw.circle(self.screen, white, (cx, cy + 1.5 * u), 3 * u)
            pygame.draw.polygon(self.screen, white, [(cx, cy - 5.5 * u), (cx - 2.8 * u, cy + 0.5 * u),
                                                     (cx + 2.8 * u, cy + 0.5 * u)])
        else:
            # Ящик — квадрат с полосой посередине
            box = pygame.Rect(0, 0, round(8 * u), round(7 * u))
            box.center = (cx, cy)
            pygame.draw.rect(self.screen, white, box, max(1, round(1.4 * u)))
            pygame.draw.line(self.screen, white, (box.left, box.top + box.height // 3),
                             (box.right - 1, box.top + box.height // 3), max(1, round(u)))

    # --- Жители ---

    def _draw_walker(self, walker: Walker, camera: Camera) -> None:
        """Человечек: тень, туловище цвета одежды и голова. Чуть подпрыгивает при ходьбе."""
        sx, sy = self.screen_point(camera, walker.x, walker.y)
        s = camera.zoom * WORLD_SCALE  # все размеры растут вместе с масштабом и размером клетки
        width, height = self.screen.get_size()
        if not (-20 < sx < width + 20 and -40 < sy < height + 20):
            return  # за краем экрана
        lift = CitizenManager.bob(walker) * 1.5 * s
        # Тень — полупрозрачный эллипс (готовая картинка из кэша по размеру)
        shadow = self._walker_shadow(max(5, round(11 * s)))
        self.screen.blit(shadow, shadow.get_rect(center=(sx, sy)))
        body = pygame.Rect(0, 0, max(2, round(5 * s)), max(4, round(9 * s)))
        body.midbottom = (round(sx), round(sy - lift))
        pygame.draw.rect(self.screen, walker.color, body, border_radius=max(1, round(s)))
        head_r = max(2, round(2.8 * s))
        pygame.draw.circle(self.screen, SKIN, (body.centerx, body.top - head_r + 1), head_r)

    def _walker_shadow(self, width: int) -> pygame.Surface:
        if width not in self._shadow_cache:
            surface = pygame.Surface((width, max(2, width // 2)), pygame.SRCALPHA)
            pygame.draw.ellipse(surface, (0, 0, 0, 70), surface.get_rect())
            self._shadow_cache[width] = surface
        return self._shadow_cache[width]

    # --- Сети: столбы, провода, светофоры, трубы ---

    def _draw_pole(self, grid: Grid, tile: Tile, camera: Camera) -> None:
        """Столб ЛЭП с перекладиной и провода к соседним столбам «сзади» (север и запад).
        Провода к соседям «спереди» нарисует их столб — так каждый провод рисуется один раз,
        вместе с более близким к зрителю столбом."""
        u = camera.zoom * WORLD_SCALE
        height = POWER_POLE_HEIGHT * DESIGN_TO_WORLD * camera.zoom
        bx, by = self.screen_point(camera, tile.x + POLE_SPOT[0], tile.y + POLE_SPOT[1])
        top = (bx, by - height)
        lit = self.view == VIEW_POWER
        pygame.draw.line(self.screen, (110, 80, 50), (bx, by), top, max(1, round(1.6 * u)))
        pygame.draw.line(self.screen, (90, 65, 40), (bx - 5 * u, top[1] + 2 * u), (bx + 5 * u, top[1] + 2 * u),
                         max(1, round(1.2 * u)))
        for dx, dy in ((0, -1), (-1, 0)):
            other = grid.get(tile.x + dx, tile.y + dy)
            if other is None or other.power_line is None:
                continue
            ox, oy = self.screen_point(camera, other.x + POLE_SPOT[0], other.y + POLE_SPOT[1])
            end = (ox, oy - height)
            # Провисание провода — парабола: середина ниже концов
            points = []
            for i in range(7):
                t = i / 6
                sag = 4 * t * (1 - t) * height * 0.12
                points.append((top[0] + (end[0] - top[0]) * t, top[1] + 2 * u + (end[1] - top[1]) * t + sag))
            pygame.draw.lines(self.screen, WIRE_LIT if lit else WIRE, False, points, max(1, round((1.4 if lit else 0.8) * u)))

    def _draw_signal(self, tile: Tile, camera: Camera) -> None:
        """Светофор на перекрёстке: столб и коробка с двумя огнями.
        Верхний огонь — для едущих вдоль оси x, нижний — вдоль оси y."""
        u = camera.zoom * WORLD_SCALE
        bx, by = self.screen_point(camera, tile.x + SIGNAL_SPOT[0], tile.y + SIGNAL_SPOT[1])
        height = 26 * DESIGN_TO_WORLD * camera.zoom
        pygame.draw.line(self.screen, (70, 70, 76), (bx, by), (bx, by - height), max(1, round(1.4 * u)))
        box = pygame.Rect(0, 0, max(3, round(6 * u)), max(6, round(13 * u)))
        box.midbottom = (round(bx), round(by - height + 2 * u))
        pygame.draw.rect(self.screen, (35, 35, 40), box, border_radius=max(1, round(u)))
        state = signal_state(self.traffic.time if self.traffic else 0.0, tile.x, tile.y)
        r = max(1, round(2 * u))
        for i, axis in enumerate(("x", "y")):
            color = LAMP["yellow"] if state == "yellow" else (LAMP["green"] if state == axis else LAMP["red"])
            pygame.draw.circle(self.screen, color, (box.centerx, box.top + box.height * (0.28 + 0.44 * i)), r)

    def _diamond(self, size: tuple[int, int], color: tuple[int, int, int], alpha: int) -> pygame.Surface:
        """Полупрозрачный ромб клетки нужного размера и цвета (для режимов просмотра)."""
        key = (size, color, alpha)
        if key not in self._diamonds:
            if len(self._diamonds) > 200:
                self._diamonds.clear()
            w, h = size
            surface = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.polygon(surface, (*color, alpha), [(w / 2, 0), (w, h / 2), (w / 2, h), (0, h / 2)])
            self._diamonds[key] = surface
        return self._diamonds[key]

    def _tile_topleft(self, camera: Camera, x: int, y: int) -> tuple[int, int]:
        sx, sy = camera.world_to_screen(*iso.tile_to_world(x, y))
        return round(sx - ISO_TILE_WIDTH / 2 * camera.zoom), round(sy)

    def _tile_size(self, camera: Camera) -> tuple[int, int]:
        return round(ISO_TILE_WIDTH * camera.zoom), round(ISO_TILE_HEIGHT * camera.zoom)

    def _draw_congestion(self, grid: Grid, camera: Camera, economy: Economy) -> None:
        """Режим «Пробки»: дороги — зелёные (свободно), жёлтые (плотно), красные (пробка)."""
        size = self._tile_size(camera)
        screen_rect = self.screen.get_rect()
        ratios = economy.traffic.ratio
        batch = []
        for building in self._road_masks:
            ratio = ratios.get((building.x, building.y), 0.0)
            color = COLOR_TRAFFIC[0] if ratio < 0.6 else (COLOR_TRAFFIC[1] if ratio < 1.0 else COLOR_TRAFFIC[2])
            pos = self._tile_topleft(camera, building.x, building.y)
            if screen_rect.collidepoint(pos[0] + size[0] // 2, pos[1] + size[1] // 2):
                batch.append((self._diamond(size, color, 160 if ratio else 90), pos))
        self.screen.blits(batch, doreturn=False)

    def _draw_water_cover(self, camera: Camera, economy: Economy, visible: list[Tile]) -> None:
        """Режим «Вода»: клетки, куда дотягивается водопровод, — голубоватые."""
        size = self._tile_size(camera)
        cover = self._diamond(size, (80, 170, 255), 70)
        infra = economy.infrastructure
        batch = [(cover, self._tile_topleft(camera, t.x, t.y)) for t in visible if infra.is_watered_tile(t.x, t.y)]
        self.screen.blits(batch, doreturn=False)

    def _draw_pipes(self, grid: Grid, camera: Camera, visible: list[Tile]) -> None:
        """Водопровод: толстые синие линии между центрами соседних клеток с трубами."""
        u = camera.zoom * WORLD_SCALE
        width = max(2, round(3.5 * u))
        for tile in visible:
            if tile.pipe is None:
                continue
            a = self.screen_point(camera, tile.x + 0.5, tile.y + 0.5)
            for dx, dy in ((1, 0), (0, 1)):
                other = grid.get(tile.x + dx, tile.y + dy)
                if other is not None and other.pipe is not None:
                    b = self.screen_point(camera, other.x + 0.5, other.y + 0.5)
                    pygame.draw.line(self.screen, (30, 70, 120), a, b, width + 2)
                    pygame.draw.line(self.screen, PIPE, a, b, width)
            pygame.draw.circle(self.screen, (30, 70, 120), a, width * 0.9)
            pygame.draw.circle(self.screen, (150, 205, 255), a, width * 0.55)

    # --- Эффекты: дым, пыль, облака, всплывающие числа ---

    def _puff(self, radius: int, color: tuple[int, int, int]) -> pygame.Surface:
        """Мягкий круг (клуб дыма) нужного радиуса — рисуем один раз и запоминаем."""
        key = (radius, color)
        if key not in self._puffs:
            size = radius * 2 + 8
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surface, (*color, 255), (size // 2, size // 2), radius)
            self._puffs[key] = pygame.transform.gaussian_blur(surface, max(1, radius // 3))
        return self._puffs[key]

    def _cloud(self, width: int, height: int) -> pygame.Surface:
        """Тень облака — размытый тёмный эллипс нужного размера.

        Размывать большую картинку — очень медленно (секунды!). Поэтому размываем
        один раз маленькую «заготовку» (CLOUD_BASE), а под нужный размер её только
        плавно растягиваем — это быстро, а при растягивании края становятся ещё мягче.
        Размеры округляем до 16 px, чтобы кэш не разрастался при плавном зуме.
        """
        key = (max(16, width // 16 * 16), max(16, height // 16 * 16))
        if key not in self._clouds:
            if len(self._clouds) > 64:
                self._clouds.clear()
            self._clouds[key] = pygame.transform.smoothscale(self._cloud_base(), key)
        return self._clouds[key]

    def _cloud_base(self) -> pygame.Surface:
        if "base" not in self._puffs_misc:
            w, h = CLOUD_BASE
            surface = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(surface, (10, 20, 30, 38), surface.get_rect().inflate(-w // 5, -h // 5))
            self._puffs_misc["base"] = pygame.transform.gaussian_blur(surface, min(w, h) // 8)
        return self._puffs_misc["base"]

    def _draw_effects(self, effects: Effects, camera: Camera) -> None:
        screen_rect = self.screen.get_rect()
        up = DESIGN_TO_WORLD * camera.zoom  # единица чертежа по высоте -> пиксели экрана
        # Дым и пыль
        for p in effects.particles:
            radius, alpha = Effects.particle_state(p)
            if alpha <= 3:
                continue
            sx, sy = self.screen_point(camera, p.x, p.y)
            r = max(2, round(radius * up))
            puff = self._puff(r, p.color)
            puff.set_alpha(alpha)
            rect = puff.get_rect(center=(round(sx), round(sy - p.z * up)))
            if rect.colliderect(screen_rect):
                self.screen.blit(puff, rect)
        # Тени облаков
        for cloud in effects.clouds:
            sx, sy = camera.world_to_screen(cloud.x, cloud.y)
            shadow = self._cloud(round(cloud.width * camera.zoom), round(cloud.height * camera.zoom))
            rect = shadow.get_rect(center=(round(sx), round(sy)))
            if rect.colliderect(screen_rect):
                self.screen.blit(shadow, rect)
        # Всплывающие числа: поднимаются и тают
        for text in effects.texts:
            t = text.age / FLOAT_TEXT_TIME
            sx, sy = self.screen_point(camera, text.x, text.y)
            sy -= text.z * up + 40 * t * WORLD_SCALE
            text.surface.set_alpha(int(255 * min(1.0, (1 - t) * 2.5)))
            self.screen.blit(text.surface, text.surface.get_rect(center=(round(sx), round(sy))))

    # --- Выбор здания мышью ---

    def pick_building(self, pos: tuple[int, int]) -> Building | None:
        """Какое здание нарисовано в точке экрана pos (самое ближнее к зрителю).

        Проверяем не просто прямоугольник картинки, а её пиксель: у спрайта
        прозрачные углы, и клик «мимо стены» не должен выбирать здание.
        """
        for rect, surface, building in reversed(self._hits):  # с конца — ближние первыми
            if rect.collidepoint(pos):
                local = (pos[0] - rect.left, pos[1] - rect.top)
                if surface.get_at(local).a > 40:  # .a — непрозрачность пикселя
                    return building
        return None

    # --- Строительство и снос (поверх всего) ---

    def _draw_outline(self, camera: Camera, x: int, y: int, width: int, height: int,
                      color: tuple[int, int, int], thickness: int = 2) -> None:
        pygame.draw.polygon(self.screen, color, self.footprint_points(camera, x, y, width, height), thickness)

    def _draw_ghost(self, camera: Camera, item: ShopItem, site: tuple[int, int],
                    frame: tuple[int, int, int]) -> None:
        """Полупрозрачное здание на месте site + рамка основания цвета frame."""
        sprite, rect = self.item_sprite_rect(camera, item, *site)
        self.screen.blit(self.images.scaled(sprite, rect.size, GHOST_ALPHA), rect)
        width, height = item.size
        self._draw_outline(camera, site[0], site[1], width, height, frame)

    def draw_build_preview(self, build: BuildMode, camera: Camera) -> None:
        """«Призрак» строительства.

        PLACING    — у курсора; зелёная рамка — можно строить, красная — нельзя.
        DRAGGING   — протягиваем дорогу: зелёные клетки построим, красные — нельзя.
        CONFIRMING — выбранные места с жёлтой рамкой, ждём подтверждения.
        """
        item = build.item
        if item is None:
            return
        if build.state == BuildState.DRAGGING:
            frame = COLOR_GHOST_BAD if build.confirm_error else COLOR_GHOST_OK
            for site in build.drag_ok:
                self._draw_ghost(camera, item, site, frame)
            for site in build.drag_bad:
                self._draw_outline(camera, site[0], site[1], 1, 1, COLOR_GHOST_BAD)
            return
        if build.state == BuildState.CONFIRMING:
            for site in build.targets:
                self._draw_ghost(camera, item, site, COLOR_GHOST_PENDING)
            return
        if build.cursor_pos is not None:
            frame = COLOR_GHOST_BAD if build.cursor_error else COLOR_GHOST_OK
            self._draw_ghost(camera, item, build.cursor_pos, frame)

    def draw_demolish_preview(self, demolish: DemolishMode, camera: Camera) -> None:
        """Подсветка при сносе: здание под курсором — красноватое, выбранное — красное."""
        if demolish.state == DemolishState.CONFIRMING and demolish.target:
            building, tint = demolish.target, DEMOLISH_TARGET_TINT
        elif demolish.hovered:
            building, tint = demolish.hovered, DEMOLISH_HOVER_TINT
        else:
            self.draw_hover(demolish.hovered_tile, camera)
            return
        if not isinstance(building, Building):  # элемент сети (линия, труба, светофор) — рамка клетки
            self._draw_outline(camera, building.x, building.y, 1, 1, COLOR_DEMOLISH, 3)
            return
        sprite, rect = self.item_sprite_rect(camera, building.item, building.x, building.y)
        self.screen.blit(self.images.scaled(sprite, rect.size, tint=tint), rect)
        self._draw_outline(camera, building.x, building.y, building.width, building.height, COLOR_DEMOLISH)

    def draw_hover(self, tile: Tile | None, camera: Camera) -> None:
        """Белая рамка-ромб вокруг клетки под курсором."""
        if tile is None:  # курсор вне карты — рисовать нечего
            return
        self._draw_outline(camera, tile.x, tile.y, 1, 1, COLOR_HOVER)

    def draw_debug(self, lines: list[str], top: int = 8) -> None:
        """Отладочный текст слева, начиная с высоты top, — по строке на элемент списка."""
        y = top
        for line in lines:
            # render() превращает текст в картинку (Surface). True — сглаживание краёв букв.
            surface = self.font.render(line, True, COLOR_TEXT)
            self.screen.blit(surface, (8, y))
            y += surface.get_height() + 2  # следующая строка ниже
