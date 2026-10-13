"""Рисование изометрических спрайтов средствами pygame: здания, крыши, окна, деревья, дороги.

Используется в двух местах:
  * tools/make_placeholder_images.py — подробные текстуры всех зданий (PNG в assets/);
  * в игре — запасной спрайт, если PNG нет (simple_building_sprite, road_tile).

Единицы чертежа
---------------
Всё чертится в «единицах чертежа»: ромб клетки 128×64, этаж — FLOOR_HEIGHT (18).
Готовая картинка получается крупнее: ромб TEXTURE_TILE_WIDTH (192) пикселей.
Так числа в чертежах остаются простыми, а разрешение текстур можно менять в config.

Гладкие края (суперсэмплинг)
----------------------------
pygame рисует многоугольники «лесенкой». Поэтому холст создаётся ещё в
TEXTURE_SUPERSAMPLE раз крупнее, а в конце (result) плавно уменьшается —
лесенка усредняется и края становятся гладкими. Так же делают в настоящих играх.

Как устроен спрайт здания размером w × h клеток
-----------------------------------------------
Картинка шириной (w + h) × TW/2. Внизу — «основание»: ромб, который ровно
ложится на клетки здания. Над ним — свободное место под высоту здания (top_space).

Точки задаются в координатах основания (cx, cy, z):
  cx — от 0 до w (вдоль оси x карты), cy — от 0 до h (вдоль оси y),
  z  — высота над землёй в единицах чертежа.

Стороны ромба (где «соседи» у клетки):
  y = 0 — верх-право («север»),  x = w — низ-право («восток»),
  y = h — низ-лево («юг»),       x = 0 — верх-лево («запад»).
Видны зрителю две стены: «левая» (вдоль y = h) и «правая» (вдоль x = w).

Освещение: свет слева-сверху. Крыша светлее всего, левая стена — средняя,
правая — темнее. Тени падают вправо-вниз.
"""

import math
import random

import pygame

from city_builder.config import (
    FLOOR_HEIGHT,
    TEXTURE_SUPERSAMPLE,
    TEXTURE_TILE_HEIGHT,
    TEXTURE_TILE_WIDTH,
)

# Ромб клетки в единицах чертежа
DTW = 128
DTH = 64

Color = tuple[int, int, int]
Point = tuple[float, float]

# Яркость граней (множитель цвета)
SHADE_TOP = 1.10
SHADE_LEFT = 0.88
SHADE_RIGHT = 0.66

# Часто используемые цвета
GLASS = (120, 170, 215)
GLASS_DARK = (70, 105, 145)
WINDOW_LIGHT = (255, 222, 140)
FRAME = (235, 235, 230)
CONCRETE = (182, 182, 186)
ASPHALT = (74, 76, 82)
SIDEWALK = (196, 194, 188)
GRASS = (98, 166, 82)


def shade(color: Color, factor: float) -> Color:
    """Светлее (factor > 1) или темнее (factor < 1), с ограничением 0..255."""
    return tuple(max(0, min(255, int(c * factor))) for c in color)  # type: ignore[return-value]


def mix(a: Color, b: Color, t: float) -> Color:
    """Смесь двух цветов: t = 0 — первый, t = 1 — второй."""
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


class SpriteCanvas:
    """Холст под спрайт здания w × h клеток с запасом высоты top_space (в единицах чертежа)."""

    def __init__(self, width: int, height: int, top_space: float) -> None:
        self.w = width
        self.h = height
        self.top_space = top_space
        self.out_scale = TEXTURE_TILE_WIDTH / DTW            # чертёж -> готовая картинка
        self.k = self.out_scale * TEXTURE_SUPERSAMPLE        # чертёж -> большой холст
        base_h = (width + height) * DTH / 2
        size = (round((width + height) * DTW / 2 * self.k), round((base_h + top_space) * self.k))
        self.surface = pygame.Surface(size, pygame.SRCALPHA)
        self.final_size = ((width + height) * TEXTURE_TILE_WIDTH // 2,
                           round((base_h + top_space) * self.out_scale))

    # --- Основа: координаты и размеры ---

    def point(self, cx: float, cy: float, z: float = 0) -> Point:
        """Точка основания (cx, cy) на высоте z -> пиксель большого холста."""
        x = self.h * DTW / 2 + (cx - cy) * DTW / 2
        y = self.top_space + (cx + cy) * DTH / 2 - z
        return x * self.k, y * self.k

    def px(self, length: float) -> int:
        """Длина в единицах чертежа -> пиксели большого холста (не меньше 1)."""
        return max(1, round(length * self.k))

    def result(self) -> pygame.Surface:
        """Готовая картинка: плавно уменьшенный холст (гладкие края)."""
        return pygame.transform.smoothscale(self.surface, self.final_size)

    # --- Простые фигуры ---

    def poly(self, points: list[Point], color, width: float = 0) -> None:
        pygame.draw.polygon(self.surface, color, points, self.px(width) if width else 0)

    def line(self, a: Point, b: Point, color, width: float = 1) -> None:
        pygame.draw.line(self.surface, color, a, b, self.px(width))

    def circle(self, center: Point, radius: float, color, width: float = 0) -> None:
        pygame.draw.circle(self.surface, color, center, radius * self.k, self.px(width) if width else 0)

    def quad(self, x0: float, y0: float, x1: float, y1: float, z: float, color, width: float = 0) -> None:
        """Горизонтальный прямоугольник карты [x0..x1] × [y0..y1] на высоте z (на экране — ромб)."""
        p = self.point
        self.poly([p(x0, y0, z), p(x1, y0, z), p(x1, y1, z), p(x0, y1, z)], color, width)

    def ground_ellipse(self, cx: float, cy: float, radius: float, z: float, color, width: float = 0) -> None:
        """Круг, лежащий на земле (в изометрии — эллипс вдвое ниже). radius — в единицах чертежа."""
        x, y = self.point(cx, cy, z)
        r = radius * self.k
        rect = pygame.Rect(0, 0, round(r * 2), round(r))
        rect.center = (round(x), round(y))
        pygame.draw.ellipse(self.surface, color, rect, self.px(width) if width else 0)

    # --- Земля под зданием ---

    def lot(self, x0: float, y0: float, x1: float, y1: float, color: Color, border: Color | None = None) -> None:
        """Участок под зданием: газон, плитка или асфальт, с бордюром по краю."""
        self.quad(x0, y0, x1, y1, 0, color)
        self.quad(x0, y0, x1, y1, 0, border or shade(color, 0.8), 1.2)

    def soft_shadow(self, x0: float, y0: float, x1: float, y1: float, height: float, strength: int = 90) -> None:
        """Мягкая тень от коробки высотой height: падает вправо-вниз и размыта по краям.

        Рисуем «вытянутый» силуэт основания на отдельном прозрачном слое,
        размываем его (gaussian_blur) и накладываем на холст.
        """
        length = min(1.2, height / 90)  # чем выше здание, тем длиннее тень (в клетках)
        layer = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        p = self.point
        dx, dy = length, length * 0.35
        hull = [p(x0, y1), p(x0 + dx, y1 + dy), p(x1 + dx, y1 + dy), p(x1 + dx, y0 + dy), p(x1, y0)]
        pygame.draw.polygon(layer, (0, 0, 0, strength), hull)
        pygame.draw.polygon(layer, (0, 0, 0, strength),
                            [p(x0, y0), p(x1, y0), p(x1, y1), p(x0, y1)])
        layer = pygame.transform.gaussian_blur(layer, self.px(5))
        # Тень не должна выходить за участок здания — иначе её обрежет край картинки
        # и на карте будет виден «срез». Оставляем тень только внутри ромба участка.
        self._clip_to_footprint(layer)
        self.surface.blit(layer, (0, 0))

    def _clip_to_footprint(self, layer: pygame.Surface) -> None:
        """Стереть всё, что на слое лежит за пределами ромба основания (участка здания)."""
        mask = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
        p = self.point
        pygame.draw.polygon(mask, (255, 255, 255, 255),
                            [p(0, 0), p(self.w, 0), p(self.w, self.h), p(0, self.h)])
        # BLEND_RGBA_MIN: в каждом пикселе берётся меньшее — за ромбом маска прозрачная,
        # поэтому и слой там становится прозрачным
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    # --- Стены и коробки ---

    def _face(self, face: str, a0: float, a1: float, fixed: float, za: float, zb: float) -> list[Point]:
        """Прямоугольник на видимой стене.
        face="left"  — стена вдоль x на линии y = fixed (a — координата x);
        face="right" — стена вдоль y на линии x = fixed (a — координата y)."""
        p = self.point
        if face == "left":
            return [p(a0, fixed, za), p(a1, fixed, za), p(a1, fixed, zb), p(a0, fixed, zb)]
        return [p(fixed, a0, za), p(fixed, a1, za), p(fixed, a1, zb), p(fixed, a0, zb)]

    def wall(self, face: str, a0: float, a1: float, fixed: float, z0: float, z1: float,
             color: Color, bands: int = 10) -> None:
        """Стена с плавным переходом света: внизу темнее (там тень от земли), вверху светлее."""
        for i in range(bands):
            za = z0 + (z1 - z0) * i / bands
            zb = z0 + (z1 - z0) * (i + 1) / bands
            factor = 0.86 + 0.2 * (i + 0.5) / bands
            if i == 0:
                factor -= 0.07  # затемнение у самой земли
            self.poly(self._face(face, a0, a1, fixed, za, zb + 0.4), shade(color, factor))

    def face_rect(self, face: str, a0: float, a1: float, fixed: float, za: float, zb: float,
                  color, width: float = 0) -> None:
        """Прямоугольник на стене: дверь, вывеска, полоса."""
        self.poly(self._face(face, a0, a1, fixed, za, zb), color, width)

    def box(self, x0: float, y0: float, x1: float, y1: float, z0: float, z1: float,
            color: Color, top: Color | None = None, outline: bool = True) -> None:
        """Коробка: левая стена (вдоль y = y1), правая (вдоль x = x1) и плоский верх."""
        p = self.point
        self.wall("left", x0, x1, y1, z0, z1, shade(color, SHADE_LEFT))
        self.wall("right", y0, y1, x1, z0, z1, shade(color, SHADE_RIGHT))
        self.quad(x0, y0, x1, y1, z1, top or shade(color, SHADE_TOP))
        if outline:
            edge = shade(color, 0.5)
            self.line(p(x0, y1, z1), p(x1, y1, z1), edge, 0.7)
            self.line(p(x1, y1, z1), p(x1, y0, z1), edge, 0.7)
            # Светлое ребро на ближнем углу — подчёркивает объём
            self.line(p(x1, y1, z0), p(x1, y1, z1), shade(color, 1.25), 0.8)

    def flat_roof(self, x0: float, y0: float, x1: float, y1: float, z: float,
                  color: Color, parapet: float = 0.05) -> None:
        """Плоская крыша с бортиком: светлая кромка по краю, внутри — чуть ниже и темнее."""
        self.quad(x0, y0, x1, y1, z, shade(color, 1.15))
        self.quad(x0 + parapet, y0 + parapet, x1 - parapet, y1 - parapet, z, shade(color, 0.92))
        # Внутренняя тень от бортика с «дальних» сторон
        p = self.point
        a, b = x0 + parapet, y0 + parapet
        self.line(p(a, b, z), p(x1 - parapet, b, z), shade(color, 0.7), 0.8)
        self.line(p(a, b, z), p(a, y1 - parapet, z), shade(color, 0.7), 0.8)

    # --- Окна и двери ---

    def window(self, face: str, a0: float, a1: float, fixed: float, za: float, zb: float,
               glass: Color = GLASS, frame: Color = FRAME, lit: bool = False) -> None:
        """Окно: рама, стекло (или свет внутри), блик и подоконник."""
        self.face_rect(face, a0, a1, fixed, za, zb, frame)
        inset_a = (a1 - a0) * 0.12
        inset_z = (zb - za) * 0.12
        pane = WINDOW_LIGHT if lit else glass
        if face == "right":
            pane = shade(pane, 0.85)  # правая стена в тени
        self.face_rect(face, a0 + inset_a, a1 - inset_a, fixed, za + inset_z, zb - inset_z, pane)
        if not lit:
            # Блик — светлая диагональ по стеклу
            pts = self._face(face, a0 + inset_a, a1 - inset_a, fixed, za + inset_z, zb - inset_z)
            self.line(pts[0], pts[2], shade(pane, 1.25), 0.6)
        # Подоконник
        sill = self._face(face, a0 - 0.01, a1 + 0.01, fixed, za - 1.2, za)
        self.poly(sill, shade(frame, 0.8))

    def window_rows(self, x0: float, y0: float, x1: float, y1: float, z0: float, floors: int,
                    per_tile: float = 2, lit: float = 0.2, seed: int = 0, glass: Color = GLASS,
                    frame: Color = FRAME, width: float = 0.5, height: float = 0.5,
                    skip_floors: int = 0) -> None:
        """Ряды окон на обеих видимых стенах: по per_tile окон на клетку стены, по ряду на этаж."""
        rng = random.Random(seed)
        for floor in range(skip_floors, floors):
            za = z0 + floor * FLOOR_HEIGHT + FLOOR_HEIGHT * (1 - height) / 2
            zb = za + FLOOR_HEIGHT * height
            for face, a0, a1, fixed in (("left", x0, x1, y1), ("right", y0, y1, x1)):
                count = max(1, round((a1 - a0) * per_tile))
                step = (a1 - a0) / count
                for i in range(count):
                    mid = a0 + step * (i + 0.5)
                    half = step * width / 2
                    self.window(face, mid - half, mid + half, fixed, za, zb,
                                glass, frame, lit=rng.random() < lit)

    def door(self, face: str, a0: float, a1: float, fixed: float, height: float = 12,
             color: Color = (110, 75, 50)) -> None:
        """Дверь с рамкой и маленьким козырьком."""
        self.face_rect(face, a0 - 0.01, a1 + 0.01, fixed, 0, height + 1, shade(color, 0.7))
        self.face_rect(face, a0, a1, fixed, 0, height, color)
        mid = (a0 + a1) / 2
        pts = self._face(face, mid + (a1 - a0) * 0.25, mid + (a1 - a0) * 0.32, fixed, height * 0.45, height * 0.55)
        self.poly(pts, (230, 200, 120))  # ручка

    # --- Крыши ---

    def gable_roof(self, x0: float, y0: float, x1: float, y1: float, z: float, height: float,
                   color: Color, wall: Color, ridge: str = "x", overhang: float = 0.05) -> None:
        """Двускатная крыша с черепицей и свесами.

        ridge="x" — конёк вдоль оси x (скаты смотрят на «север» и «юг»),
        ridge="y" — конёк вдоль оси y (скаты на «запад» и «восток»).
        Видимый торец (фронтон) закрашивается цветом стены.
        """
        p = self.point
        o = overhang
        if ridge == "x":
            ym = (y0 + y1) / 2
            back = [p(x0 - o, y0 - o, z), p(x1 + o, y0 - o, z), p(x1 + o, ym, z + height), p(x0 - o, ym, z + height)]
            front = [p(x0 - o, y1 + o, z), p(x1 + o, y1 + o, z), p(x1 + o, ym, z + height), p(x0 - o, ym, z + height)]
            gable = [p(x1, y0, z), p(x1, y1, z), p(x1, ym, z + height)]  # торец на правой стене
            self.poly(back, shade(color, 1.05))
            self.poly(gable, shade(wall, SHADE_RIGHT))
            self.poly(front, shade(color, 0.92))
            # Ряды черепицы на переднем скате — линии параллельно коньку
            for i in range(1, 5):
                t = i / 5
                a = (p(x0 - o, y1 + o - (y1 + o - ym) * t, z + height * t))
                b = (p(x1 + o, y1 + o - (y1 + o - ym) * t, z + height * t))
                self.line(a, b, shade(color, 0.75), 0.6)
            self.line(p(x0 - o, ym, z + height), p(x1 + o, ym, z + height), shade(color, 1.25), 1.0)
            self.poly(front, shade(color, 0.55), 0.6)
        else:
            xm = (x0 + x1) / 2
            back = [p(x0 - o, y0 - o, z), p(x0 - o, y1 + o, z), p(xm, y1 + o, z + height), p(xm, y0 - o, z + height)]
            front = [p(x1 + o, y0 - o, z), p(x1 + o, y1 + o, z), p(xm, y1 + o, z + height), p(xm, y0 - o, z + height)]
            gable = [p(x0, y1, z), p(x1, y1, z), p(xm, y1, z + height)]  # торец на левой стене
            self.poly(back, shade(color, 1.08))
            self.poly(gable, shade(wall, SHADE_LEFT))
            self.poly(front, shade(color, 0.72))
            for i in range(1, 5):
                t = i / 5
                a = p(x1 + o - (x1 + o - xm) * t, y0 - o, z + height * t)
                b = p(x1 + o - (x1 + o - xm) * t, y1 + o, z + height * t)
                self.line(a, b, shade(color, 0.58), 0.6)
            self.line(p(xm, y0 - o, z + height), p(xm, y1 + o, z + height), shade(color, 1.25), 1.0)
            self.poly(front, shade(color, 0.45), 0.6)

    def hip_roof(self, x0: float, y0: float, x1: float, y1: float, z: float, height: float,
                 color: Color, overhang: float = 0.05) -> None:
        """Четырёхскатная (шатровая) крыша: сначала дальние скаты, потом ближние."""
        p = self.point
        o = overhang
        apex = p((x0 + x1) / 2, (y0 + y1) / 2, z + height)
        t, r = p(x0 - o, y0 - o, z), p(x1 + o, y0 - o, z)
        b, l = p(x1 + o, y1 + o, z), p(x0 - o, y1 + o, z)
        for pts, factor in (([l, t, apex], 1.1), ([t, r, apex], 0.82),
                            ([l, b, apex], 0.95), ([b, r, apex], 0.7)):
            self.poly(pts, shade(color, factor))
            self.poly(pts, shade(color, 0.5), 0.5)

    # --- Круглые формы ---

    def _bottom_y(self, x: float, cx: float, cy_base: float, radius_px: float) -> float:
        """y нижней дуги эллипса основания для точки x (для цилиндров)."""
        d = (x - cx) / radius_px
        return cy_base + radius_px / 2 * math.sqrt(max(0.0, 1 - d * d))

    def cylinder(self, cx: float, cy: float, radius: float, z0: float, z1: float,
                 color: Color, top: Color | None = None, strips: int = 16) -> None:
        """Вертикальный цилиндр (труба, бак): слева светлее, справа темнее, сверху — крышка."""
        x, yb = self.point(cx, cy, z0)
        _, yt = self.point(cx, cy, z1)
        r = radius * self.k
        for i in range(strips):
            xa = x - r + 2 * r * i / strips
            xb = x - r + 2 * r * (i + 1) / strips
            factor = 1.15 - 0.6 * (i + 0.5) / strips  # плавное затенение слева направо
            pts = [(xa, yt), (xb + 0.5, yt), (xb + 0.5, self._bottom_y(xb, x, yb, r)), (xa, self._bottom_y(xa, x, yb, r))]
            pygame.draw.polygon(self.surface, shade(color, factor), pts)
        rect = pygame.Rect(0, 0, round(2 * r), round(r))
        rect.center = (round(x), round(yt))
        pygame.draw.ellipse(self.surface, top or shade(color, 1.2), rect)
        pygame.draw.ellipse(self.surface, shade(color, 0.6), rect, self.px(0.6))

    def cooling_tower(self, cx: float, cy: float, r_bottom: float, r_waist: float, r_top: float,
                      height: float, color: Color) -> None:
        """Градирня: «талия» посередине (гиперболоид), тёмное жерло сверху."""
        x, yb = self.point(cx, cy, 0)
        _, yt = self.point(cx, cy, height)
        levels = 24
        left, right = [], []
        for i in range(levels + 1):
            t = i / levels
            # Радиус: от низа сужается к «талии» (на 65% высоты), потом немного расширяется
            if t < 0.65:
                rr = r_bottom + (r_waist - r_bottom) * (t / 0.65) ** 0.8
            else:
                rr = r_waist + (r_top - r_waist) * ((t - 0.65) / 0.35) ** 1.6
            y = yb + (yt - yb) * t
            left.append((x - rr * self.k, y))
            right.append((x + rr * self.k, y))
        pygame.draw.polygon(self.surface, shade(color, 0.95), left + right[::-1])
        # Правая половина в тени, левый край — с бликом
        pygame.draw.polygon(self.surface, shade(color, 0.72), [(x, p[1]) for p in right] + right[::-1])
        pygame.draw.lines(self.surface, shade(color, 1.15), False, [(p[0] + self.px(2), p[1]) for p in left], self.px(1.5))
        # Нижняя дуга основания
        rb = r_bottom * self.k
        rect = pygame.Rect(0, 0, round(2 * rb), round(rb))
        rect.center = (round(x), round(yb))
        pygame.draw.arc(self.surface, shade(color, 0.6), rect, math.pi, 2 * math.pi, self.px(1))
        # Жерло сверху
        rt = r_top * self.k
        rect = pygame.Rect(0, 0, round(2 * rt), round(rt))
        rect.center = (round(x), round(yt))
        pygame.draw.ellipse(self.surface, shade(color, 1.1), rect)
        inner = rect.inflate(-self.px(4), -self.px(2))
        pygame.draw.ellipse(self.surface, (45, 45, 50), inner)

    def cone(self, cx: float, cy: float, radius: float, z: float, height: float, color: Color) -> None:
        """Конусная крыша (бак водонапорной башни): левая половина светлее."""
        x, yb = self.point(cx, cy, z)
        apex = (x, yb - height * self.k)
        r = radius * self.k
        arc_left = [(x - r + r * i / 8, self._bottom_y(x - r + r * i / 8, x, yb, r)) for i in range(9)]
        arc_right = [(x + r * i / 8, self._bottom_y(x + r * i / 8, x, yb, r)) for i in range(9)]
        pygame.draw.polygon(self.surface, shade(color, 1.1), [apex] + arc_left)
        pygame.draw.polygon(self.surface, shade(color, 0.72), [apex] + arc_right)

    def steam(self, cx: float, cy: float, z: float, scale: float = 1.0) -> None:
        """Клубы пара или дыма — размытые полупрозрачные круги."""
        layer = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        x, y = self.point(cx, cy, z)
        for i, (dx, dy, r) in enumerate(((0, -6, 9), (6, -18, 12), (14, -32, 15), (24, -46, 17))):
            pygame.draw.circle(layer, (235, 235, 240, 200 - i * 35),
                               (x + dx * self.k * scale, y + dy * self.k * scale), r * self.k * scale)
        layer = pygame.transform.gaussian_blur(layer, self.px(3))
        self.surface.blit(layer, (0, 0))

    # --- Детали окружения ---

    def tree(self, cx: float, cy: float, size: float = 1.0, kind: str = "round",
             color: Color = (70, 140, 60)) -> None:
        """Дерево: тень, ствол и крона (круглая или ёлка)."""
        s = 10 * size
        x, y = self.point(cx, cy)
        k = self.k
        shadow = pygame.Rect(0, 0, round(s * 2.2 * k), round(s * 0.9 * k))
        shadow.center = (round(x + s * 0.5 * k), round(y))
        pygame.draw.ellipse(self.surface, (0, 0, 0, 55), shadow)
        pygame.draw.line(self.surface, (105, 75, 45), (x, y), (x, y - s * 1.3 * k), self.px(2.2 * size))
        if kind == "pine":
            for i, w in enumerate((1.0, 0.75, 0.5)):
                base = y - s * (1.0 + i * 0.9) * k
                top = base - s * 1.4 * k
                pygame.draw.polygon(self.surface, shade(color, 0.8 + i * 0.1),
                                    [(x - s * w * k, base), (x + s * w * k, base), (x, top)])
                pygame.draw.polygon(self.surface, shade(color, 0.6),
                                    [(x, base), (x + s * w * k, base), (x, top)])
        else:
            cy_ = y - s * 2.0 * k
            pygame.draw.circle(self.surface, shade(color, 0.75), (x + s * 0.15 * k, cy_ + s * 0.1 * k), s * k)
            pygame.draw.circle(self.surface, color, (x - s * 0.1 * k, cy_ - s * 0.05 * k), s * 0.85 * k)
            pygame.draw.circle(self.surface, shade(color, 1.25), (x - s * 0.35 * k, cy_ - s * 0.35 * k), s * 0.4 * k)

    def car(self, cx: float, cy: float, color: Color, along: str = "x") -> None:
        """Маленькая машина: кузов, кабина со стёклами."""
        hx, hy = (0.16, 0.08) if along == "x" else (0.08, 0.16)
        self.box(cx - hx, cy - hy, cx + hx, cy + hy, 0.5, 5, color, outline=False)
        if along == "x":
            self.box(cx - hx * 0.45, cy - hy * 0.8, cx + hx * 0.35, cy + hy * 0.8, 5, 9, (170, 200, 220), outline=False)
        else:
            self.box(cx - hx * 0.8, cy - hy * 0.45, cx + hx * 0.8, cy + hy * 0.35, 5, 9, (170, 200, 220), outline=False)

    def bench(self, cx: float, cy: float) -> None:
        self.box(cx - 0.08, cy - 0.025, cx + 0.08, cy + 0.025, 2, 4, (140, 100, 60), outline=False)


# ---------------------------------------------------------------------------
# Клетки земли
# ---------------------------------------------------------------------------

def terrain_tile(base: Color, seed: int, kind: str, flowers: int = 0) -> pygame.Surface:
    """Ромб земли: трава (пятна оттенков, травинки, flowers цветочков) или вода (блики волн)."""
    c = SpriteCanvas(1, 1, 0)
    rng = random.Random(seed)
    c.quad(0, 0, 1, 1, 0, base)
    layer = pygame.Surface(c.surface.get_size(), pygame.SRCALPHA)
    if kind == "grass":
        for _ in range(18):  # мягкие пятна чуть другого оттенка
            x, y = c.point(rng.random(), rng.random())
            color = shade(base, rng.choice((0.94, 0.97, 1.03, 1.06)))
            pygame.draw.circle(layer, (*color, 120), (x, y), rng.uniform(10, 18) * c.k)
        layer = pygame.transform.gaussian_blur(layer, c.px(5))
        for _ in range(35):  # редкие травинки
            x, y = c.point(rng.random(), rng.random())
            color = shade(base, rng.choice((0.85, 1.12)))
            pygame.draw.line(layer, (*color, 150), (x, y), (x + rng.uniform(-1, 1) * c.k, y - 2.5 * c.k), c.px(0.5))
    else:
        for _ in range(7):  # блики волн
            x, y = c.point(rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9))
            w = rng.uniform(6, 12) * c.k
            pygame.draw.arc(layer, (210, 230, 255, 170), (x - w, y - w / 4, w * 2, w / 2), 0.3, 2.8, c.px(0.8))
    for _ in range(flowers):  # цветочки
        x, y = c.point(rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85))
        color = rng.choice(((250, 240, 120), (250, 250, 250), (240, 140, 170), (190, 160, 240)))
        pygame.draw.circle(layer, color, (x, y), c.px(1.3))
    # Обрезаем узоры по форме ромба (см. SpriteCanvas._clip_to_footprint)
    c._clip_to_footprint(layer)
    c.surface.blit(layer, (0, 0))
    c.quad(0, 0, 1, 1, 0, (*shade(base, 0.7), 70), 0.6)  # тонкая сетка клеток
    return c.result()


def grass_tile(base: Color, variant: int) -> pygame.Surface:
    """Вариант травы: чуть другой оттенок, а в некоторых — мелкие цветы.
    Клетки с разными вариантами вперемешку — и карта не выглядит «сеткой»."""
    tint = (1.0, 0.96, 1.04, 0.92)[variant % 4]
    flowers = 9 if variant % 2 == 1 else 0
    return terrain_tile(shade(base, tint), seed=variant * 17 + 3, kind="grass", flowers=flowers)


def water_tile(land_mask: int, frame: int) -> pygame.Surface:
    """Клетка воды: блики волн (frame — кадр анимации) и берег с тех сторон, где суша.

    land_mask — маска соседей-суши (как у дорог: север 1, восток 2, юг 4, запад 8).
    С этих сторон — песчаная полоса и пена у кромки, вода там светлее (мелководье).
    """
    from city_builder.config import SAND, TILE_COLORS
    base = TILE_COLORS["water"]
    c = SpriteCanvas(1, 1, 0)
    p = c.point
    c.quad(0, 0, 1, 1, 0, base)
    sides = [s for s in (NORTH, EAST, SOUTH, WEST) if land_mask & s]
    for side in sides:  # мелководье — светлая полоса у берега
        c.quad(*_side_strip(side, 0.32), 0, shade(base, 1.18))
    # Блики волн: позиции фиксированы для клетки, а кадр сдвигает их по кругу
    rng = random.Random(11)
    layer = pygame.Surface(c.surface.get_size(), pygame.SRCALPHA)
    phase = frame / 4 * 2 * math.pi
    for i in range(7):
        bx, by = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        shift = 0.05 * math.sin(phase + i)
        x, y = p(bx + shift, by - shift)
        w = rng.uniform(5, 10) * c.k
        alpha = int(120 + 100 * (0.5 + 0.5 * math.sin(phase + i * 1.7)))
        pygame.draw.arc(layer, (225, 240, 255, alpha), (x - w, y - w / 4, w * 2, w / 2), 0.4, 2.7, c.px(0.9))
    c._clip_to_footprint(layer)
    c.surface.blit(layer, (0, 0))
    for side in sides:  # песок и пена
        c.quad(*_side_strip(side, 0.14), 0, SAND)
        x0, y0, x1, y1 = _side_strip(side, 0.14 + 0.03 * (1 + math.sin(phase)))
        edge = {NORTH: (p(0, y1), p(1, y1)), SOUTH: (p(0, y0), p(1, y0)),
                WEST: (p(x1, 0), p(x1, 1)), EAST: (p(x0, 0), p(x0, 1))}[side]
        c.line(*edge, (245, 250, 255), 1.4)
    return c.result()


def decor_sprite(kind: str, variant: int) -> pygame.Surface:
    """Природа на пустой клетке: деревья, ёлки, кусты, цветы, камни (по 3 варианта)."""
    # sum(ord) — «номер» строки, одинаковый при каждом запуске (в отличие от hash())
    rng = random.Random(sum(map(ord, kind)) + variant * 31)
    c = SpriteCanvas(1, 1, 80)
    greens = [(70, 150, 60), (60, 130, 55), (95, 165, 70)]
    if kind == "tree":
        autumn = [(220, 140, 50), (200, 90, 50), (235, 190, 70)]
        for _ in range(rng.choice((1, 2, 2))):
            color = rng.choice(autumn) if rng.random() < 0.18 else rng.choice(greens)
            c.tree(rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7), rng.uniform(1.5, 2.0), "round", color)
    elif kind == "pine":
        spots = sorted([(rng.uniform(0.25, 0.75), rng.uniform(0.25, 0.75)) for _ in range(rng.choice((1, 2, 3)))],
                       key=lambda s: s[0] + s[1])  # дальние раньше ближних
        for x, y in spots:
            c.tree(x, y, rng.uniform(1.4, 1.9), "pine", rng.choice(((50, 120, 70), (40, 105, 60))))
    elif kind == "bush":
        for _ in range(rng.choice((2, 3))):
            x, y = c.point(rng.uniform(0.25, 0.75), rng.uniform(0.25, 0.75))
            r = rng.uniform(8, 12) * c.k
            color = rng.choice(greens)
            pygame.draw.ellipse(c.surface, (0, 0, 0, 50), (x - r, y - r * 0.3, r * 2.2, r * 0.8))
            pygame.draw.circle(c.surface, shade(color, 0.8), (x, y - r * 0.6), r)
            pygame.draw.circle(c.surface, shade(color, 1.15), (x - r * 0.3, y - r * 0.9), r * 0.45)
    elif kind == "flowers":
        for _ in range(26):
            x, y = c.point(rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85))
            color = rng.choice(((245, 90, 110), (250, 220, 70), (250, 250, 250), (170, 120, 240), (250, 150, 60)))
            pygame.draw.line(c.surface, (60, 120, 50), (x, y), (x, y - 3 * c.k), c.px(0.5))
            pygame.draw.circle(c.surface, color, (x, y - 3.5 * c.k), c.px(2.0))
    else:  # rock
        for _ in range(rng.choice((1, 2))):
            x, y = c.point(rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7))
            r = rng.uniform(8, 13) * c.k
            pts = [(x - r, y), (x - r * 0.6, y - r * 0.8), (x + r * 0.1, y - r * 1.0),
                   (x + r * 0.8, y - r * 0.5), (x + r, y), (x, y + r * 0.35)]
            pygame.draw.polygon(c.surface, (0, 0, 0, 45), [(px + r * 0.3, py + r * 0.2) for px, py in pts])
            pygame.draw.polygon(c.surface, (150, 150, 155), pts)
            pygame.draw.polygon(c.surface, (185, 185, 190), [pts[0], pts[1], pts[2], (x, y - r * 0.2)])
    return c.result()


def car_sprite(color: Color, along: str) -> pygame.Surface:
    """Машина в центре клетки, едет вдоль оси x или y. Рисуется крупнее, чем на парковке."""
    c = SpriteCanvas(1, 1, 16)
    hx, hy = (0.2, 0.1) if along == "x" else (0.1, 0.2)
    cx = cy = 0.5
    layer = pygame.Surface(c.surface.get_size(), pygame.SRCALPHA)
    p = c.point
    pygame.draw.polygon(layer, (0, 0, 0, 80), [p(cx - hx + 0.04, cy - hy + 0.04), p(cx + hx + 0.06, cy - hy + 0.04),
                                               p(cx + hx + 0.06, cy + hy + 0.06), p(cx - hx + 0.04, cy + hy + 0.06)])
    c.surface.blit(pygame.transform.gaussian_blur(layer, c.px(2)), (0, 0))
    c.box(cx - hx, cy - hy, cx + hx, cy + hy, 1, 7, color)
    if along == "x":
        c.box(cx - hx * 0.5, cy - hy * 0.85, cx + hx * 0.35, cy + hy * 0.85, 7, 12, (170, 205, 230))
        c.box(cx - hx * 0.5, cy - hy * 0.85, cx + hx * 0.35, cy + hy * 0.85, 12, 12.5, shade(color, 1.1), outline=False)
    else:
        c.box(cx - hx * 0.85, cy - hy * 0.5, cx + hx * 0.85, cy + hy * 0.35, 7, 12, (170, 205, 230))
        c.box(cx - hx * 0.85, cy - hy * 0.5, cx + hx * 0.85, cy + hy * 0.35, 12, 12.5, shade(color, 1.1), outline=False)
    return c.result()


# ---------------------------------------------------------------------------
# Дороги: 16 вариантов по соседям
# ---------------------------------------------------------------------------
# Маска соседей — 4 бита: какие соседние клетки тоже дорога.
NORTH, EAST, SOUTH, WEST = 1, 2, 4, 8   # y−1, x+1, y+1, x−1


def road_mask(has_road) -> int:
    """has_road(dx, dy) -> bool. Возвращает маску 0..15 для клетки дороги."""
    mask = 0
    if has_road(0, -1):
        mask |= NORTH
    if has_road(1, 0):
        mask |= EAST
    if has_road(0, 1):
        mask |= SOUTH
    if has_road(-1, 0):
        mask |= WEST
    return mask


# Середины сторон ромба и «кромки» для тротуаров: (сторона, точка на краю, направление внутрь)
_SIDES = {
    NORTH: ((0.5, 0.0), (0, 1)),
    EAST: ((1.0, 0.5), (-1, 0)),
    SOUTH: ((0.5, 1.0), (0, -1)),
    WEST: ((0.0, 0.5), (1, 0)),
}


def _side_strip(side: int, depth: float) -> tuple[float, float, float, float]:
    """Полоса вдоль стороны клетки шириной depth: (x0, y0, x1, y1)."""
    return {
        NORTH: (0, 0, 1, depth),
        SOUTH: (0, 1 - depth, 1, 1),
        WEST: (0, 0, depth, 1),
        EAST: (1 - depth, 0, 1, 1),
    }[side]


def road_tile(style: str, mask: int, seed: int = 0) -> pygame.Surface:
    """Клетка дороги с учётом соседей.

    style: "asphalt" — асфальт, тротуары, белая прерывистая разметка;
           "avenue"  — проспект: тёмный асфальт, двойная жёлтая линия;
           "dirt"    — грунтовка: колеи, трава по краям;
           "bridge"  — деревянный мост: настил, перила по краям.
    Тротуары (перила, траву) рисуем только с тех сторон, где НЕТ соседней дороги,
    а разметку ведём от центра к тем сторонам, где дорога продолжается.
    """
    rng = random.Random(seed + mask)
    c = SpriteCanvas(1, 1, 22 if style == "bridge" else 0)
    p = c.point
    if style == "bridge":
        wood = (165, 125, 85)
        c.box(0, 0, 1, 1, 0, 5, wood, top=(186, 146, 102), outline=False)
        for i in range(1, 10):  # доски поперёк движения
            t = i / 10
            if mask & (EAST | WEST):
                c.line(p(t, 0, 5), p(t, 1, 5), shade(wood, 0.7), 0.6)
            else:
                c.line(p(0, t, 5), p(1, t, 5), shade(wood, 0.7), 0.6)
        # Перила — с тех сторон, где мост не продолжается (дальние стороны рисуем первыми)
        rails = {NORTH: ((0, 0.04), (1, 0.04)), WEST: ((0.04, 0), (0.04, 1)),
                 SOUTH: ((0, 0.96), (1, 0.96)), EAST: ((0.96, 0), (0.96, 1))}
        for side, ((ax, ay), (bx, by)) in rails.items():
            if mask & side:
                continue
            for t in (0.1, 0.5, 0.9):  # столбики
                px_, py_ = ax + (bx - ax) * t, ay + (by - ay) * t
                c.line(p(px_, py_, 5), p(px_, py_, 14), (95, 70, 45), 1.2)
            c.line(p(ax, ay, 14), p(bx, by, 14), (95, 70, 45), 1.6)  # поручень
        return c.result()

    base = {"asphalt": ASPHALT, "avenue": (58, 60, 66), "dirt": (156, 126, 86)}[style]
    c.quad(0, 0, 1, 1, 0, base)
    for _ in range(160):  # зернистость покрытия
        x, y = p(rng.random(), rng.random())
        pygame.draw.circle(c.surface, shade(base, rng.choice((0.85, 1.15))), (x, y), c.px(0.4))

    # Края без соседей: тротуар (асфальт/проспект) или трава (грунтовка)
    for side in (NORTH, EAST, SOUTH, WEST):
        if mask & side:
            continue
        if style == "dirt":
            c.quad(*_side_strip(side, 0.1), 0, (*GRASS, 255))
        else:
            c.quad(*_side_strip(side, 0.15), 0, SIDEWALK)
            x0, y0, x1, y1 = _side_strip(side, 0.15)
            inner = {NORTH: (p(0, 0.15), p(1, 0.15)), SOUTH: (p(0, 0.85), p(1, 0.85)),
                     WEST: (p(0.15, 0), p(0.15, 1)), EAST: (p(0.85, 0), p(0.85, 1))}[side]
            c.line(*inner, shade(SIDEWALK, 0.7), 0.8)  # бордюр

    # Разметка или колеи от центра к соседям
    connected = [s for s in (NORTH, EAST, SOUTH, WEST) if mask & s]
    centre = (0.5, 0.5)
    for side in connected:
        (ex, ey), _ = _SIDES[side]
        if style == "asphalt":
            start = 0.18 if len(connected) >= 3 else 0.0  # на перекрёстке центр без разметки
            for i in range(3):
                t0 = start + (1 - start) * i / 3
                t1 = t0 + (1 - start) / 6
                a = p(centre[0] + (ex - centre[0]) * t0, centre[1] + (ey - centre[1]) * t0)
                b = p(centre[0] + (ex - centre[0]) * t1, centre[1] + (ey - centre[1]) * t1)
                c.line(a, b, (235, 235, 225), 1.0)
        elif style == "avenue":
            ox, oy = (0.025, 0) if side in (NORTH, SOUTH) else (0, 0.025)
            for sign in (-1, 1):
                a = p(centre[0] + sign * ox, centre[1] + sign * oy)
                b = p(ex + sign * ox, ey + sign * oy)
                c.line(a, b, (235, 195, 60), 0.8)
        else:  # dirt — две колеи
            ox, oy = (0.13, 0) if side in (NORTH, SOUTH) else (0, 0.13)
            for sign in (-1, 1):
                a = p(centre[0] + sign * ox, centre[1] + sign * oy)
                b = p(ex + sign * ox, ey + sign * oy)
                c.line(a, b, shade(base, 0.78), 2.2)
    if style == "asphalt" and len(connected) >= 3:
        # «Зебры» на въездах в перекрёсток
        for side in connected:
            (ex, ey), (ix, iy) = _SIDES[side]
            for k in range(5):
                t = 0.25 + k * 0.125
                if side in (NORTH, SOUTH):
                    c.quad(t, ey + iy * 0.04 - 0.02, t + 0.06, ey + iy * 0.12 - 0.02, 0, (225, 225, 220))
                else:
                    c.quad(ex + ix * 0.04 - 0.02, t, ex + ix * 0.12 - 0.02, t + 0.06, 0, (225, 225, 220))
    return c.result()


# ---------------------------------------------------------------------------
# Простой спрайт здания — запасной вариант, если нет PNG
# ---------------------------------------------------------------------------

def simple_building_sprite(width: int, height: int, floors: int, color: Color, flat: bool) -> pygame.Surface:
    """Аккуратная коробка нужной высоты цвета товара (или плоская клетка для дорог/площадок)."""
    if flat:
        c = SpriteCanvas(width, height, 0)
        c.lot(0.03, 0.03, width - 0.03, height - 0.03, color)
        return c.result()
    z = max(1, floors) * FLOOR_HEIGHT + 4
    c = SpriteCanvas(width, height, z + 8)
    m = 0.14  # отступ от края клеток
    c.lot(0.02, 0.02, width - 0.02, height - 0.02, (172, 172, 168))
    c.soft_shadow(m, m, width - m, height - m, z)
    c.box(m, m, width - m, height - m, 0, z, color)
    c.window_rows(m, m, width - m, height - m, 4, max(1, floors), per_tile=2.5, lit=0.15,
                  glass=shade(color, 0.6), frame=shade(color, 1.2))
    c.flat_roof(m, m, width - m, height - m, z, color)
    return c.result()
