"""Камера: перевод координат мира в координаты экрана и обратно.

В игре есть две системы координат:

* Мир — «настоящие» координаты на карте, в пикселях при zoom = 1.
  Клетка (x, y) начинается в точке (x * TILE_SIZE, y * TILE_SIZE).
  Карта 30x30 клеток по 32 px = мир размером 960x960.

* Экран — пиксели окна. (0, 0) — левый верхний угол окна.

Камера — это «окошко», через которое мы смотрим на мир:
  (self.x, self.y) — какая точка мира сейчас в левом верхнем углу экрана;
  self.zoom        — во сколько раз мир увеличен (2.0 = всё вдвое крупнее).

Двигая камеру, мы не трогаем карту — меняем только эти три числа,
а Renderer по ним пересчитывает, где что рисовать.
"""

from city_builder.config import ZOOM_MAX, ZOOM_MIN


class Camera:
    def __init__(self, screen_width: int, screen_height: int,
                 world_width: float, world_height: float) -> None:
        # Размеры окна и мира нужны для центрирования и ограничения камеры
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.world_width = world_width
        self.world_height = world_height
        # Точка мира, которая находится в левом верхнем углу экрана
        self.x = 0.0
        self.y = 0.0
        self.zoom = 1.0  # масштаб: 1.0 — клетка 32 px, 2.0 — 64 px и т.д.

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        """Мир -> экран. Нужно для отрисовки: где на экране нарисовать точку мира.

        Сначала вычитаем позицию камеры (сдвиг), потом умножаем на zoom (масштаб).
        """
        return (wx - self.x) * self.zoom, (wy - self.y) * self.zoom

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Экран -> мир. Обратная формула. Нужна, чтобы понять,
        на какую точку карты указывает курсор мыши."""
        return sx / self.zoom + self.x, sy / self.zoom + self.y

    def move(self, dx: float, dy: float) -> None:
        """Сдвинуть камеру на (dx, dy) пикселей ЭКРАНА.

        Делим на zoom: при сильном приближении один пиксель экрана —
        это меньше пикселя мира. Так карта при перетаскивании мышью
        двигается ровно вслед за курсором при любом масштабе.
        """
        self.x += dx / self.zoom
        self.y += dy / self.zoom

    def center_on(self, wx: float, wy: float) -> None:
        """Поставить камеру так, чтобы точка мира (wx, wy) была в центре экрана."""
        # Половина экрана в единицах мира = половина экрана в пикселях / zoom
        self.x = wx - self.screen_width / (2 * self.zoom)
        self.y = wy - self.screen_height / (2 * self.zoom)

    def zoom_at(self, factor: float, screen_pos: tuple[float, float]) -> None:
        """Изменить масштаб так, чтобы точка под курсором осталась на месте.

        Как в картах Google: крутишь колесо — приближается то место,
        куда указывает мышь, а не центр экрана.

        factor > 1 — приблизить, factor < 1 — отдалить.
        """
        sx, sy = screen_pos
        # 1. Запоминаем, какая точка мира сейчас под курсором
        wx, wy = self.screen_to_world(sx, sy)
        # 2. Меняем масштаб, не выходя за пределы ZOOM_MIN..ZOOM_MAX
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))
        # 3. Сдвигаем камеру, чтобы та же точка мира снова оказалась под курсором
        #    (это формула screen_to_world, решённая относительно self.x / self.y)
        self.x = wx - sx / self.zoom
        self.y = wy - sy / self.zoom

    def clamp(self) -> None:
        """Не даёт центру экрана уйти за пределы мира.

        Иначе можно «улететь» в пустоту и потерять карту.
        Вызывается каждый кадр после всех перемещений камеры.
        """
        # Половина экрана в единицах мира
        half_w = self.screen_width / (2 * self.zoom)
        half_h = self.screen_height / (2 * self.zoom)
        # Текущий центр экрана в мире, зажатый в границы [0, размер мира]
        center_x = max(0.0, min(self.world_width, self.x + half_w))
        center_y = max(0.0, min(self.world_height, self.y + half_h))
        # Пересчитываем левый верхний угол из исправленного центра
        self.x = center_x - half_w
        self.y = center_y - half_h
