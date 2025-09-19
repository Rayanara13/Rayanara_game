from ursina import *
import random


app = Ursina()
camera.background_color = color.orange

# камера сверху
camera.orthographic = True
camera.position = (0, 40, -20)
camera.rotation_x = 60

# пол
ground = Entity(model='plane', scale=30, color=color.lime)


class Bush(Entity):
    def __init__(self, pos, ready=False):
        super().__init__(model='sphere', color=color.blue if ready else color.brown, scale=0.6, position=pos)
        self.food = 5 if ready else 0
        self.grow_timer = 0 if ready else 2  # через 2 дня даст урожай

    def tick(self):
        if self.food == 0 and self.grow_timer > 0:
            self.grow_timer -= 1
            if self.grow_timer <= 0:
                self.food = 5
                self.color = color.green


class Citizen(Entity):
    def __init__(self, name, village, role="collector"):
        super().__init__(model='cube', color=color.orange, scale=0.4,
                         position=(village.x + random.uniform(-2, 2), 0.2, village.z + random.uniform(-2, 2)))
        self.name = name
        self.village = village
        self.role = role  # collector / farmer
        self.target = None
        self.carrying = 0
        self.harvest_timer = 0
        self.speed = 10
        self.alive = True
        self.label = Text(text=f"{self.name} ({self.role})", scale=1, world_parent=self, y=1.2)

    def logic(self):
        if not self.alive:
            return

        if self.role == "collector":
            self.collector_logic()
        else:
            self.farmer_logic()

    def collector_logic(self):
        if self.carrying == 0 and not self.target:
            bushes_with_food = [b for b in bushes if b.food > 0]
            if bushes_with_food:
                self.target = random.choice(bushes_with_food)

        if self.target:
            if isinstance(self.target, Bush) and self.target.food <= 0:
                self.target = None
            else:
                direction = Vec3(self.target.x - self.x, 0, self.target.z - self.z)
                if direction.length() > 0:
                    direction = direction.normalized()
                    self.position += direction * self.speed * time.dt

        if isinstance(self.target, Bush) and self.carrying == 0:
            if distance_xz(self, self.target) < 0.6:
                self.harvest_timer += time.dt
                if self.harvest_timer > 2:
                    if self.target.food > 0:
                        self.carrying = 2
                        self.target.food -= 1
                        self.color = color.yellow
                        self.target = self.village
                    else:
                        self.target = None
                    self.harvest_timer = 0

        elif self.carrying > 0 and self.target == self.village:
            if distance_xz(self, self.village) < 1:
                self.village.food += self.carrying
                self.carrying = 0
                self.color = color.orange
                self.target = None

        # подпись
        state = "несёт" if self.carrying > 0 else "ищет" if self.target else "ждёт"
        self.label.text = f"{self.name} (собир., {state})"

    def farmer_logic(self):
        # садовод работает только рядом с деревней
        if distance_xz(self, self.village) < 2:
            # проверяем лимит и запас еды
            if self.village.food > 5 and self.village.bushes_planted_today < max(1, len(self.village.citizens) // 3):
                self.village.food -= 1
                self.village.bushes_planted_today += 1
                new_bush = Bush((self.village.x + random.randint(-6, 6),
                                 0.3,
                                 self.village.z + random.randint(-6, 6)), ready=False)
                bushes.append(new_bush)
        self.label.text = f"{self.name} (садит)"


class Village(Entity):
    def __init__(self, pos=(0, 0.5, 0)):
        super().__init__(model='cube', color=color.azure, scale=1.5, position=pos)
        self.food = 50
        self.citizens = []
        self.day = 0
        self.next_id = 0
        self.bushes_planted_today = 0   # <── добавили счётчик
        self.add_starting_population()

    def add_starting_population(self):
        for i in range(4):  # старт 4 жителя
            role = "collector" if i % 2 == 0 else "farmer"
            citizen = Citizen(f'Житель {self.next_id}', self, role)
            self.citizens.append(citizen)
            self.next_id += 1

    def tick(self):
        self.day += 1
        self.bushes_planted_today = 0   # <── обнуляем каждый новый день

        # кусты растут
        for b in bushes:
            b.tick()

        # жители едят
        for c in list(self.citizens):
            if c.alive:
                if self.food > 0:
                    self.food -= 1
                else:
                    c.alive = False
                    c.disable()
                    c.label.disable()
                    self.citizens.remove(c)

        # прирост населения
        if self.food >= 10:
            self.food -= 5
            role = "collector" if self.next_id % 2 == 0 else "farmer"
            new_citizen = Citizen(f'Житель {self.next_id}', self, role)
            self.citizens.append(new_citizen)
            self.next_id += 1

        # удаляем пустые кусты
        for b in list(bushes):
            if b.food <= 0 and b.grow_timer <= 0:
                bushes.remove(b)
                destroy(b)



def distance_xz(a, b):
    return ((a.x - b.x) ** 2 + (a.z - b.z) ** 2) ** 0.5


# деревня
village = Village()

# начальные кусты
bushes = [Bush((random.randint(-10, 10), 0.3, random.randint(-10, 10)), ready=True) for _ in range(3)]

info = Text(text='', position=(-.5, .45), scale=2)
day_timer = 0


def update():
    global day_timer
    for c in village.citizens:
        c.logic()

    day_timer += time.dt
    if day_timer > 5:  # день = 5 сек
        day_timer = 0
        village.tick()

    alive = len(village.citizens)
    info.text = f'День: {village.day} | Еда: {village.food} | Живые: {alive} | Кустов: {len(bushes)}'


app.run()
