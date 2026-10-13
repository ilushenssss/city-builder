"""Отрисовка мира в изометрии (вид под углом).

Renderer только рисует: он читает данные (Grid, Camera, BuildMode, жители),
но ничего в них не меняет. Вся игровая логика живёт в других модулях.

Слои (снизу вверх):
  1. Земля: трава и вода — ромбы клеток.
  2. Дороги — плоские, лежат на земле, поэтому рисуются сразу после неё.
  3. Здания и жители — ВПЕРЕМЕШКУ, отсортированные по «глубине» (x + y):
     сначала дальние, потом ближние. Так ближний дом закрывает человечка
     за ним, а человечек перед домом — виден. Это «алгоритм художника»:
     художник тоже пишет сначала задний план, потом передний.
  4. Призрак строительства и подсветка сноса — поверх всего (рисуются отдельно).

Как рисует pygame: есть «поверхность» (Surface) окна — по сути картинка
в памяти. Мы рисуем на ней спрайты и текст, а в конце кадра GameLoop
вызывает pygame.display.flip(), и картинка появляется на экране.
"""

import math

import pygame

from city_builder.citizens.citizens import CitizenManager, Walker
from city_builder.config import (
    COLOR_BACKGROUND,
    COLOR_DEMOLISH,
    COLOR_GHOST_BAD,
    COLOR_GHOST_OK,
    COLOR_GHOST_PENDING,
    COLOR_HOVER,
    COLOR_TEXT,
    DEMOLISH_HOVER_TINT,
    DEMOLISH_TARGET_TINT,
    FLAT_CATEGORIES,
    GHOST_ALPHA,
    ISO_TILE_HEIGHT,
    ISO_TILE_WIDTH,
    NO_ROAD_TINT,
    PROBLEM_COLORS,
    TILE_COLORS,
)
from city_builder.construction.build_mode import BuildMode, BuildState
from city_builder.construction.demolish_mode import DemolishMode, DemolishState
from city_builder.data.catalog import ShopItem
from city_builder.render import iso
from city_builder.render.camera import Camera
from city_builder.render.images import ImageLibrary
from city_builder.world.building import Building
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile

SKIN = (240, 200, 160)  # цвет лица человечков


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

    def draw(self, grid: Grid, camera: Camera, citizens: CitizenManager | None = None) -> None:
        """Нарисовать карту, здания и жителей. Вызывается каждый кадр."""
        self.screen.fill(COLOR_BACKGROUND)  # стираем прошлый кадр
        self._hits = []
        self._draw_terrain(grid, camera)
        self._draw_roads(grid, camera)
        self._draw_buildings_and_walkers(grid, camera, citizens)

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

    def _draw_terrain(self, grid: Grid, camera: Camera) -> None:
        """Слой 1: трава и вода."""
        # Подложка всей карты цветом травы — чтобы между ромбами не было щелей
        pygame.draw.polygon(self.screen, TILE_COLORS["grass"],
                            self.footprint_points(camera, 0, 0, grid.width, grid.height))

        # Размер ромба на экране и шаги: сдвиг на клетку по x и по y.
        # Считаем один раз на кадр, а не для каждой клетки — так в разы быстрее.
        hw = ISO_TILE_WIDTH / 2 * camera.zoom
        hh = ISO_TILE_HEIGHT / 2 * camera.zoom
        tile_size = (math.ceil(hw * 2) + 1, math.ceil(hh * 2) + 1)  # +1 — небольшой нахлёст, без щелей
        sprites = {name: self.images.scaled(self.images.terrain(name), tile_size) for name in TILE_COLORS}
        ox, oy = camera.world_to_screen(0, 0)  # верхний угол клетки (0, 0) на экране
        screen_w, screen_h = self.screen.get_size()

        # blits() рисует много картинок одним вызовом — быстрее, чем blit() в цикле
        batch = []
        xs, ys = self._visible_tile_range(grid, camera)
        for y in ys:
            row = grid.tiles[y]
            for x in xs:
                sx = ox + (x - y) * hw - hw
                sy = oy + (x + y) * hh
                if sx > screen_w or sy > screen_h or sx + tile_size[0] < 0 or sy + tile_size[1] < 0:
                    continue  # ромб целиком за краем экрана
                batch.append((sprites[row[x].type.value], (round(sx), round(sy))))
        self.screen.blits(batch, doreturn=False)

    def _draw_roads(self, grid: Grid, camera: Camera) -> None:
        """Слой 2: плоские дороги."""
        screen_rect = self.screen.get_rect()
        for building in grid.buildings:
            if not is_flat(building):
                continue
            sprite, rect = self.item_sprite_rect(camera, building.item, building.x, building.y)
            if rect.colliderect(screen_rect):
                scaled = self.images.scaled(sprite, rect.size)
                self.screen.blit(scaled, rect)
                self._hits.append((rect, scaled, building))

    def _draw_buildings_and_walkers(self, grid: Grid, camera: Camera,
                                    citizens: CitizenManager | None) -> None:
        """Слой 3: здания и жители вперемешку, от дальних к ближним."""
        # Список (глубина, порядок, объект). Порядок нужен, чтобы при равной глубине
        # здание рисовалось раньше человечка, — и чтобы Python не пытался сравнивать
        # сами объекты (это вызвало бы ошибку).
        drawables: list[tuple[float, int, object]] = []
        for building in grid.buildings:
            if not is_flat(building):
                # Глубина здания — по его самой ближней клетке (передний угол)
                depth = iso.depth(building.x + building.width - 0.5, building.y + building.height - 0.5)
                drawables.append((depth, 0, building))
        if citizens:
            for walker in citizens.visible_walkers():
                drawables.append((iso.depth(walker.x, walker.y), 1, walker))
        drawables.sort(key=lambda d: (d[0], d[1]))  # сортировка по глубине

        screen_rect = self.screen.get_rect()
        for _, _, obj in drawables:
            if isinstance(obj, Building):
                self._draw_building(obj, camera, screen_rect)
            else:
                self._draw_walker(obj, camera)

    def _draw_building(self, building: Building, camera: Camera, screen_rect: pygame.Rect) -> None:
        sprite, rect = self.item_sprite_rect(camera, building.item, building.x, building.y)
        if not rect.colliderect(screen_rect):
            return  # здание за краем экрана
        # Неработающее здание (нет дороги, света или воды) — темнее
        tint = None if building.working else NO_ROAD_TINT
        scaled = self.images.scaled(sprite, rect.size, tint=tint)
        self.screen.blit(scaled, rect)
        self._hits.append((rect, scaled, building))
        if building.problems:
            # Значок первой (главной) проблемы над зданием
            self._draw_problem_badge(rect, building.problems[0], camera)

    def _draw_problem_badge(self, rect: pygame.Rect, problem: str, camera: Camera) -> None:
        """Цветной кружок со значком над зданием:
        «!» — нет дороги, молния — нет света, капля — нет воды, ящик — нет сырья."""
        r = max(6, round(8 * camera.zoom))
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
        s = camera.zoom  # все размеры растут вместе с масштабом
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
