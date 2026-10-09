"""Обработка клавиатуры и мыши.

В pygame есть два способа узнать о вводе:

1. События (handle_event) — разовые действия: «клавишу нажали»,
   «колесо прокрутили», «окно закрыли». Каждое событие приходит один раз.

2. Состояние (update) — «что зажато прямо сейчас». Опрашиваем каждый кадр.
   Подходит для плавного движения: пока стрелка зажата — камера едет.
"""

import math

import pygame

from city_builder.config import CAMERA_SPEED, TILE_SIZE, ZOOM_STEP
from city_builder.render.camera import Camera
from city_builder.world.grid import Grid
from city_builder.world.tile import Tile

# Номера кнопок мыши в pygame: 1 — левая, 2 — средняя (колесо), 3 — правая
MIDDLE_BUTTON = 2


class InputHandler:
    def __init__(self, camera: Camera, grid: Grid) -> None:
        self.camera = camera  # чтобы двигать и масштабировать камеру
        self.grid = grid      # чтобы узнать, какая клетка под курсором
        self.quit_requested = False  # Game проверяет этот флаг и завершает игру
        self.dragging = False        # зажата ли сейчас средняя кнопка мыши
        self.mouse_pos = (0, 0)      # позиция курсора в пикселях окна
        self.hovered_tile: Tile | None = None  # клетка под курсором (None — курсор вне карты)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Разовые события. Вызывается из GameLoop для каждого события."""
        if event.type == pygame.QUIT:
            # Нажали крестик окна
            self.quit_requested = True
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            # Нажали Esc
            self.quit_requested = True
        elif event.type == pygame.MOUSEWHEEL:
            # Колесо мыши: event.y = +1 при прокрутке вверх, -1 вниз.
            # ZOOM_STEP ** 1 = 1.1 (приблизить), ZOOM_STEP ** -1 ≈ 0.91 (отдалить).
            self.camera.zoom_at(ZOOM_STEP ** event.y, pygame.mouse.get_pos())
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == MIDDLE_BUTTON:
            # Нажали среднюю кнопку — начинаем перетаскивание карты
            self.dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == MIDDLE_BUTTON:
            # Отпустили — заканчиваем перетаскивание
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            # Мышь сдвинулась, пока кнопка зажата.
            # event.rel — насколько пикселей сдвинулся курсор с прошлого события.
            # Минус: тянем мышь вправо — камера едет влево, и карта «следует за рукой».
            dx, dy = event.rel
            self.camera.move(-dx, -dy)

    def update(self, dt: float) -> None:
        """Опрос зажатых клавиш и положения курсора — каждый кадр.

        dt — сколько секунд прошло с прошлого кадра (обычно ~0.016 при 60 FPS).
        """
        # --- Движение камеры с клавиатуры ---
        # get_pressed() — состояние всех клавиш: True, если зажата.
        keys = pygame.key.get_pressed()
        # True/False в Python ведут себя как 1/0, поэтому:
        # вправо зажато -> dx = 1, влево -> dx = -1, оба или ни одной -> 0
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
        if dx or dy:
            # При движении по диагонали вектор (1, 1) длиннее единицы (≈1.41),
            # и камера ехала бы быстрее. Делим на длину — скорость одинакова в любую сторону.
            length = math.hypot(dx, dy)
            # Умножаем на dt, чтобы скорость не зависела от FPS:
            # 600 px/сек * 0.016 сек = ~10 px за кадр при 60 FPS.
            step = CAMERA_SPEED * dt / length
            self.camera.move(dx * step, dy * step)

        # --- Какая клетка под курсором ---
        self.mouse_pos = pygame.mouse.get_pos()
        # Пиксели экрана -> координаты мира
        wx, wy = self.camera.screen_to_world(*self.mouse_pos)
        # Координаты мира -> номер клетки (делим на размер клетки и округляем вниз).
        # floor, а не int: int(-0.5) = 0, а нам нужно -1 (клетка за картой).
        # grid.get вернёт None, если курсор вне карты.
        self.hovered_tile = self.grid.get(math.floor(wx / TILE_SIZE), math.floor(wy / TILE_SIZE))
