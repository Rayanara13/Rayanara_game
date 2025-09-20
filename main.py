from ursina import *
import random, math

app = Ursina()
camera.background_color = color.rgb(255, 165, 0)

def _vec3(value):
    """Утилита для гарантии, что позиция камеры хранится как Vec3."""
    if isinstance(value, Vec3):
        return value
    return Vec3(*value)


CAMERA_MODES = {
    "global": {
        "position": _vec3((0, 40, -20)),
        "rotation_x": 60,
        "orthographic": True,
        "fov": 40,
    },
    "local": {
        "position": _vec3((0, 18, -12)),
        "rotation_x": 45,
        "orthographic": False,
        "fov": 65,
    },
}

CAMERA_INTERPOLATION_SPEED = 3.5

camera_mode = "global"
camera_target_params = CAMERA_MODES[camera_mode].copy()

camera.position = Vec3(camera_target_params["position"])
camera.rotation_x = camera_target_params["rotation_x"]
camera.orthographic = camera_target_params["orthographic"]
camera.fov = camera_target_params["fov"]


def set_camera_mode(mode_name):
    """Изменяет целевые параметры камеры в зависимости от выбранного режима."""
    global camera_mode, camera_target_params
    if mode_name not in CAMERA_MODES or mode_name == camera_mode:
        return

    camera_mode = mode_name
    camera_target_params = CAMERA_MODES[mode_name].copy()


def _lerp(a, b, t):
    return a + (b - a) * t


def _update_camera(dt):
    """Плавно приближает параметры камеры к целевым."""
    if not camera_target_params:
        return

    factor = min(1, CAMERA_INTERPOLATION_SPEED * dt)
    target_pos = camera_target_params["position"]
    camera.position = camera.position + (target_pos - camera.position) * factor
    camera.rotation_x = _lerp(camera.rotation_x, camera_target_params["rotation_x"], factor)
    camera.fov = _lerp(camera.fov, camera_target_params["fov"], factor)
    camera.orthographic = camera_target_params["orthographic"]

# поле
ground = Entity(model='plane', scale=30, color=color.yellow)


REGION_COLORS = {
    "plains": color.rgb(240, 220, 150),
    "forest": color.rgb(90, 160, 90),
    "mountain": color.rgb(160, 160, 170),
}


def _get_region_type(world_x, world_z):
    """Возвращает тип региона для мировых координат плитки."""
    # Используем комбинацию тригонометрических функций для получения плавных зон.
    noise = (
        math.sin(world_x * 0.35)
        + math.cos(world_z * 0.35)
        + math.sin((world_x + world_z) * 0.2)
    ) / 3

    if noise > 0.3:
        return "mountain"
    if noise < -0.2:
        return "forest"
    return "plains"

def generate_world(tile_shape, size):
    """Подготавливает плитки мира и создаёт визуальные объекты."""
    tiles = []
    half = size // 2

    if tile_shape == "hex":
        radius = half
        for q in range(-radius, radius + 1):
            for r in range(-radius, radius + 1):
                s = -q - r
                if abs(s) > radius:
                    continue
                world_x = math.sqrt(3) * (q + r / 2)
                world_z = 1.5 * r
                region_type = _get_region_type(world_x, world_z)
                tile_entity = Entity(
                    model='quad',
                    rotation_x=90,
                    color=REGION_COLORS[region_type],
                    position=Vec3(world_x, 0.01, world_z),
                    scale=(1.05, 1.05, 1),
                )
                tiles.append({
                    "shape": tile_shape,
                    "grid_coords": (q, r, s),
                    "world_pos": Vec3(world_x, 0, world_z),
                    "entity": tile_entity,
                    "occupied": False,
                    "region": region_type,
                })
    else:
        for x in range(-half, half + 1):
            for z in range(-half, half + 1):
                region_type = _get_region_type(x, z)
                tile_entity = Entity(
                    model='quad',
                    rotation_x=90,
                    color=REGION_COLORS[region_type],
                    position=Vec3(x, 0.01, z),
                    scale=1.05,
                )
                tiles.append({
                    "shape": tile_shape,
                    "grid_coords": (x, z),
                    "world_pos": Vec3(x, 0, z),
                    "entity": tile_entity,
                    "occupied": False,
                    "region": region_type,
                })

    return tiles

# ====== настройки ======
FIELD_SIZE = 30
HALF = FIELD_SIZE // 2
MAX_RADIUS = 15
TILE_SHAPE = "square"
world_tiles = generate_world(TILE_SHAPE, FIELD_SIZE)

VISIBLE_LIMIT = 300  # максимум видимых жителей
update_index = 0     # для батч-обновления


def get_free_tile(village_pos):
    """Находит свободную клетку на поле в пределах радиуса"""
    candidates = []
    for tile in world_tiles:
        if tile["occupied"] or tile["region"] != "plains":
            continue
        pos = tile["world_pos"]
        dist = math.sqrt((pos.x - village_pos[0]) ** 2 + (pos.z - village_pos[2]) ** 2)
        if dist <= MAX_RADIUS:
            candidates.append(tile)

    if not candidates:
        return None

    return random.choice(candidates)


class Farm(Entity):
    def __init__(self, pos):
        super().__init__(model='cube', color=color.brown, scale=(1, 0.2, 1), position=pos)
        self.grow_stage = 0
        self.food_per_day = 2
        self.worker = None
        self.label = Text(text="Ферма (0)", scale=1, parent=self, y=1, color=color.black)

    def tick(self):
        if self.grow_stage < 3:
            self.grow_stage += 1
            if self.grow_stage == 1:
                self.color = color.rgb(139, 69, 19)
                self.food_per_day = 2
            elif self.grow_stage == 2:
                self.color = color.green
                self.food_per_day = 4
            elif self.grow_stage == 3:
                self.color = color.violet
                self.food_per_day = 6

        self.label.text = f"Ферма (ур.{self.grow_stage}, +{self.food_per_day}/д)"


class Citizen(Entity):
    def __init__(self, name, village):
        super().__init__(model='cube', color=color.orange, scale=0.4,
                         position=(village.x + random.uniform(-2, 2), 0.2, village.z + random.uniform(-2, 2)))
        self.name = name
        self.village = village
        self.role = "collector"
        self.quality = random.choice(["normal", "strong", "lazy", "fast"])
        self.farm = None
        self.target = None
        self.carrying = 0
        self.harvest_timer = 0
        self.speed = 10 if self.quality == "fast" else 7
        self.alive = True
        self.work_animation = 0

    def logic(self):
        if not self.alive:
            return
        if self.role == "farmworker":
            self.farmworker_logic()

    def farmworker_logic(self):
        if self.farm and self.farm.enabled:
            dist = distance_xz(self, self.farm)
            if dist > 0.3:  # идёт к ферме
                direction = Vec3(self.farm.x - self.x, 0, self.farm.z - self.z).normalized()
                self.position += direction * self.speed * time.dt
            else:  # работает
                self.work_animation += time.dt * 4
                self.y = 0.2 + math.sin(self.work_animation) * 0.05


class Village(Entity):
    def __init__(self, pos=(0, 0.5, 0)):
        super().__init__(model='cube', color=color.azure, scale=1.5, position=pos)
        self.food = 50
        self.citizens = []
        self.total_population = 0  # включает абстрактных жителей
        self.day = 0
        self.next_id = 0
        self.farms = []
        self.add_starting_population()

    def add_starting_population(self):
        for i in range(6):
            self.spawn_citizen()
        self.total_population = len(self.citizens)

    def spawn_citizen(self):
        """Создание жителя (если не превысили лимит видимых)"""
        if len(self.citizens) < VISIBLE_LIMIT:
            citizen = Citizen(f'Житель {self.next_id}', self)
            self.citizens.append(citizen)
        self.next_id += 1
        self.total_population += 1

    def tick(self):
        self.day += 1

        # фермы
        for farm in self.farms:
            farm.tick()
            if farm.worker and farm.worker.alive:
                self.food += farm.food_per_day

        # жители едят
        deaths = 0
        if self.total_population > 0:
            if self.food >= self.total_population:
                self.food -= self.total_population
            else:
                deaths = self.total_population - self.food
                self.total_population = self.food
                self.food = 0
                # обрезаем видимых жителей
                while len(self.citizens) > self.total_population:
                    c = self.citizens.pop()
                    c.alive = False
                    if c.farm:
                        c.farm.worker = None
                        c.farm = None
                    destroy(c)

        # новые фермы
        workers = [c for c in self.citizens if c.alive and c.role != "farmworker"]
        for farm in self.farms:
            if (not farm.worker or not farm.worker.alive) and workers:
                worker = workers.pop()
                worker.role = "farmworker"
                worker.farm = farm
                farm.worker = worker

        while len(self.farms) < self.total_population and workers:
            tile = get_free_tile(self.position)
            if not tile:
                break
            pos = tile["world_pos"]
            farm_pos = (pos.x, 0.2, pos.z)
            new_farm = Farm(farm_pos)
            self.farms.append(new_farm)
            tile["occupied"] = True
            tile["farm"] = new_farm

            worker = workers.pop()
            worker.role = "farmworker"
            worker.farm = new_farm
            new_farm.worker = worker

        # прирост населения
        max_new = max(1, self.total_population // 2)
        spawned = 0
        while self.food >= 10 and spawned < max_new:
            self.food -= 5
            self.spawn_citizen()
            spawned += 1


def distance_xz(a, b):
    return ((a.x - b.x) ** 2 + (a.z - b.z) ** 2) ** 0.5


# деревня
village = Village()

info = Text(text='', position=(-.5, .45), scale=2, color=color.black)
day_timer = 0

def input(key):
    if key == "g" or key == "scroll down":
        set_camera_mode("global")
    elif key == "l" or key == "scroll up":
        set_camera_mode("local")

def update():
    global day_timer, update_index
    if village.citizens:
        step = max(1, len(village.citizens) // 5)  # обновляем 20% за кадр
        for c in village.citizens[update_index:update_index + step]:
            c.logic()
        update_index = (update_index + step) % len(village.citizens)

    day_timer += time.dt
    if day_timer > 5:  # день = 5 сек
        day_timer = 0
        village.tick()

    info.text = (f'День: {village.day} | Еда: {village.food} | '
                 f'Население: {village.total_population} | Ферм: {len(village.farms)}')

    _update_camera(time.dt)

app.run()
