# gradostroi_plus.py
import os
import sys
import json
import math
import random
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Callable, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

# ===== Optional pretty UI =====
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    RICH = True
    console = Console()
except Exception:
    RICH = False
    console = None

# ===== Enums =====
class BiomeHealth(Enum):
    HEALTHY = "Здоровый"
    STABLE = "Стабильный"
    DEGRADED = "Деградирующий"
    CRITICAL = "Критический"

class VictoryType(Enum):
    TECHNOLOGICAL = "Технологическая победа"
    ECONOMIC = "Экономическая победа"
    ECOLOGICAL = "Экологическая победа"
    CULTURAL = "Культурная победа"

class Difficulty(Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"

# ===== Data =====
@dataclass
class Recipe:
    inputs: Dict[str, float]
    outputs: Dict[str, float]
    name: str = ""
    required_tech: Optional[str] = None

@dataclass
class Technology:
    name: str
    description: str
    cost: Dict[str, float]
    required_techs: List[str]
    effects: Dict[str, Any]
    researched: bool = False

@dataclass
class Character:
    name: str
    description: str
    skills: Dict[str, int]
    relationships: Dict[str, int]
    memory: List[str]
    quests_offered: List[str]
    personality_traits: List[str]

    def get_relationship_status(self) -> str:
        score = self.relationships.get('player', 0)
        if score >= 80: return "Обожает"
        if score >= 60: return "Уважает"
        if score >= 40: return "Дружелюбен"
        if score >= 20: return "Нейтрален"
        if score >= 0: return "Осторожен"
        if score >= -20: return "Недоволен"
        if score >= -40: return "Враждебен"
        return "Ненавидит"

    def react_to_action(self, action: str, target: str = None):
        action_impact = {
            'deforestation': -25,
            'build_sawmill': -10,
            'build_herbalist': 15,
            'research_ecology': 20,
            'pollute_river': -30,
            'cleanup_pollution': 25,
            'build_forge': 10
        }
        impact = action_impact.get(action, 0)
        if 'environmentalist' in self.personality_traits and 'deforest' in action:
            impact *= 2
            self.memory.append("player_destroyed_nature")
        if 'blacksmith' in self.personality_traits and 'build_forge' in action:
            impact += 20
            self.memory.append("player_built_forge")
        self.relationships['player'] = max(-100, min(100, self.relationships.get('player', 0) + impact))

# ===== Config / Save =====
@dataclass
class GameConfig:
    difficulty: Difficulty = Difficulty.NORMAL
    base_population: int = 8
    pop_food_per_day: float = 0.4
    happiness_decay: float = 0.25  # per day to neutral
    rng_seed: Optional[int] = None

    def apply_difficulty(self, g: "Gradostroi"):
        if self.difficulty == Difficulty.EASY:
            g.resources['food'] += 25
            g.resources['wood'] += 20
            g.resources['wine'] += 15
            g.eco_industry_penalty = 0.8
            g.happiness += 10
        elif self.difficulty == Difficulty.HARD:
            g.resources['food'] -= 5
            g.eco_industry_penalty = 1.2
            g.happiness -= 5

class SaveManager:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(os.path.expanduser("~"), ".gradostroi", "save.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def save(self, game_state: Dict[str, Any]):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(game_state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def load(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

# ===== Ecosystem / Market / Legacy / Lore =====
class WorldEcosystem:
    def __init__(self, game: "Gradostroi"):
        self.game = game
        self.biome_health = {
            'forest': 5.0,
            'rivers': 0.0,
            'soil': 8.0,
            'air': 2.0
        }
        self.pollution_level = 0.0
        self.biodiversity = 100.0

    def update_ecosystem(self):
        building_impact = {
            'les': {'forest': -0.6, 'air': -0.15},
            'kam': {'soil': -0.4, 'air': -0.25},
            'pes': {'soil': -0.55, 'rivers': -0.35},
            'gli': {'soil': -0.35},
        }
        worker_factor = 0.75 + 0.05 * min(self.game.workers_total(), 10)  # больше рабочих — больше нагрузка
        worker_factor *= self.game.eco_industry_penalty

        for building, impacts in building_impact.items():
            count = self.game.buildings.get(building, 0)
            for biome, impact in impacts.items():
                self.biome_health[biome] += impact * count * worker_factor

        # Естественное восстановление
        for biome in self.biome_health:
            if self.biome_health[biome] < 90:
                self.biome_health[biome] += 0.6  # мягкий реген
            self.biome_health[biome] = max(0.0, min(100.0, self.biome_health[biome]))

        # Загрязнение от совокупной индустрии
        total_industry = sum(self.game.buildings.values())
        self.pollution_level = min(100.0, 0.25 * total_industry * worker_factor)

        avg_health = sum(self.biome_health.values()) / len(self.biome_health)
        self.biodiversity = max(0.0, avg_health - self.pollution_level * 0.25)

    def get_overall_health(self) -> float:
        return sum(self.biome_health.values()) / len(self.biome_health)

    def get_health_status(self) -> BiomeHealth:
        h = self.get_overall_health()
        if h >= 80: return BiomeHealth.HEALTHY
        if h >= 60: return BiomeHealth.STABLE
        if h >= 40: return BiomeHealth.DEGRADED
        return BiomeHealth.CRITICAL

    def get_production_modifier(self) -> float:
        h = self.get_overall_health()
        if h >= 80: return 1.2
        if h >= 60: return 1.0
        if h >= 40: return 0.8
        return 0.6

class DynamicMarket:
    def __init__(self, game: "Gradostroi"):
        self.game = game
        self.price_history = defaultdict(list)
        self.base_prices = {
            'wood': 1.0, 'wine': 2.0, 'rock': 1.5, 'food': 1.0,
            'water': 0.5, 'coal': 3.0, 'steel': 8.0, 'bronze': 6.0,
            'instrument': 12.0, 'sand': 0.8, 'clay': 0.9, 'herbs': 2.5,
            'iron': 3.5, 'tin': 3.0, 'cooper': 3.0, 'nickel': 3.5, 'plumb': 2.5,
            'sulfur': 1.4, 'salt': 0.7, 'sulfur_acid': 5.0, 'clorine': 4.0,
            'ancient_tool': 40.0
        }
        self.trend = 1.0  # ползучая инфляция/дефляция

    def _saturation_modifier(self, resource: str) -> float:
        # wine — валюта, не лимитим складом
        available = self.game.resources[resource]
        capacity = max(1.0, self.game.storage_capacity if resource != 'wine' else self.game.storage_capacity*10)
        sat = available / capacity
        if sat > 0.9: return 0.6
        if sat < 0.15: return 1.9
        if sat < 0.3: return 1.3
        return 1.0

    def _event_modifier(self) -> float:
        d = self.game.day
        if self.game.allah_event <= d <= self.game.allah_event + self.game.event_duration:
            return 1.25
        return 1.0

    def get_current_price(self, resource: str) -> float:
        base = self.base_prices.get(resource, 1.0)
        m = self._saturation_modifier(resource) * self._event_modifier() * self.trend
        # сглаживание волатильности
        noise = 1.0 + random.uniform(-0.04, 0.04)
        price = max(0.1, base * m * noise)
        self.price_history[resource].append(price)
        if len(self.price_history[resource]) > 20:
            self.price_history[resource].pop(0)
        # сглаживание скользящей средней
        avg = sum(self.price_history[resource]) / len(self.price_history[resource])
        return (price + avg) / 2

    def can_trade(self, resource: str, amount: float, is_buying: bool) -> bool:
        price = self.get_current_price(resource)
        total = price * amount
        if is_buying:
            return self.game.resources['wine'] >= total
        return self.game.resources[resource] >= amount

    def execute_trade(self, resource: str, amount: float, is_buying: bool) -> bool:
        price = self.get_current_price(resource)
        total = price * amount
        if amount <= 0: return False
        if is_buying:
            if self.game.resources['wine'] >= total:
                self.game.resources['wine'] -= total  # валюта не капится складом
                self.game.adjust_resource(resource, amount)
                return True
        else:
            if self.game.resources[resource] >= amount:
                # продаём из запаса (запас ограничен складом), но выручка — нет
                self.game.adjust_resource(resource, -amount)
                self.game.resources['wine'] += total
                return True
        return False

class LegacySystem:
    def __init__(self, game: "Gradostroi"):
        self.game = game
        self.achievements = {
            "first_settlement": {"name": "Первое поселение", "unlocked": False, "reward": {"builder_materials": 10}},
            "master_crafter":  {"name": "Мастер-ремесленник", "unlocked": False, "reward": {"craft_speed": 1.2}},
            "ecological_balance":{"name": "Экологический баланс", "unlocked": False, "reward": {"biome_health": 20}},
            "tech_pioneer":     {"name": "Пионер технологий", "unlocked": False, "reward": {"research_bonus": 1.5}}
        }

    def check_achievements(self):
        if not self.achievements["first_settlement"]["unlocked"] and sum(self.game.buildings.values()) >= 3:
            self.unlock_achievement("first_settlement")
        if not self.achievements["master_crafter"]["unlocked"] and self.game.resources['instrument'] >= 20:
            self.unlock_achievement("master_crafter")
        eco = self.game.ecosystem.get_overall_health()
        if not self.achievements["ecological_balance"]["unlocked"] and eco >= 80:
            self.unlock_achievement("ecological_balance")
        if not self.achievements["tech_pioneer"]["unlocked"] and self.game.research_progress >= 50:
            self.unlock_achievement("tech_pioneer")

    def unlock_achievement(self, key: str):
        a = self.achievements[key]; a["unlocked"] = True
        reward = a["reward"]
        print(f"\n🎉 Достижение: {a['name']}")
        for r, amt in reward.items():
            if r in self.game.resources:
                self.game.resources[r] += amt
            elif r == "craft_speed":
                self.game.craft_speed_multiplier = max(self.game.craft_speed_multiplier, float(amt))
            elif r == "research_bonus":
                self.game.research_bonus = max(self.game.research_bonus, float(amt))

    def calculate_final_legacy(self) -> Tuple[VictoryType, str, float]:
        scores = {
            VictoryType.TECHNOLOGICAL: self.game.research_progress,
            VictoryType.ECONOMIC: sum(v for k, v in self.game.resources.items() if k != 'wine') * 0.1 + self.game.resources['wine'] * 0.05,
            VictoryType.ECOLOGICAL: self.game.ecosystem.get_overall_health(),
            VictoryType.CULTURAL: len([a for a in self.achievements.values() if a["unlocked"]]) * 25
        }
        if scores[VictoryType.ECOLOGICAL] > 70:
            scores[VictoryType.ECONOMIC] *= 1.2
            scores[VictoryType.CULTURAL] *= 1.1
        best = max(scores.items(), key=lambda x: x[1])
        titles = {
            VictoryType.TECHNOLOGICAL: [(90, "Великий Инноватор"), (70, "Технологический Лидер"), (50, "Изобретатель")],
            VictoryType.ECONOMIC: [(1000, "Король Торговли"), (500, "Мастер Экономики"), (200, "Успешный Торговец")],
            VictoryType.ECOLOGICAL: [(85, "Мудрый Хранитель"), (70, "Друг Природы"), (50, "Эко-Строитель")],
            VictoryType.CULTURAL: [(80, "Культурный Икон"), (60, "Просветитель"), (40, "Собиратель Знаний")]
        }
        score_value = best[1]
        title = "Выживший"
        for th, t in titles[best[0]]:
            if score_value >= th:
                title = t
                break
        return best[0], title, score_value

class LoreSystem:
    def __init__(self, game: "Gradostroi"):
        self.game = game
        self.ancients_secrets = {
            "seed_of_prosperity": {"name": "Семя Процветания", "description": "Древняя технология улучшения урожая",
                                   "cost": {"food": 50, "research": 10}, "effect": "double_agriculture", "discovered": False},
            "memory_crystal": {"name": "Кристалл Памяти", "description": "Позволяет видеть прошлое местности",
                               "cost": {"rock": 30, "water": 20}, "effect": "reveal_secrets", "discovered": False},
            "forge_of_souls": {"name": "Кузница Душ", "description": "Легендарная технология создания артефактов",
                               "cost": {"steel": 10, "coal": 20, "research": 30}, "effect": "artifact_crafting", "discovered": False},
        }
        self.discovered_lore: List[str] = []

    def discover_secret(self, secret_id: str) -> bool:
        if secret_id not in self.ancients_secrets: return False
        secret = self.ancients_secrets[secret_id]
        if secret["discovered"]: return False
        cost_met = all(self.game.resources[r] >= amt for r, amt in secret["cost"].items() if r != "research")
        if "research" in secret["cost"]:
            cost_met = cost_met and (self.game.research_progress >= secret["cost"]["research"])
        if not cost_met: return False
        # списание
        for r, amt in secret["cost"].items():
            if r != "research":
                self.game.adjust_resource(r, -amt)
        secret["discovered"] = True
        self.discovered_lore.append(secret_id)
        print(f"\n🔮 Тайна открыта: {secret['name']} — {secret['description']}")
        self.apply_secret_effect(secret["effect"])
        return True

    def apply_secret_effect(self, effect: str):
        if effect == "double_agriculture":
            self.game.food_production_multiplier = max(self.game.food_production_multiplier, 2.0)
            print("   ⚡ Урожайность удвоена.")
        elif effect == "reveal_secrets":
            print("   🔍 На карте появляются скрытые ресурсы (флейвор, модификатор цен).")
            self.game.market.trend *= 0.98  # знание → чуть мягче инфляция
        elif effect == "artifact_crafting":
            print("   🛠 Доступен крафт артефактов.")
            # бафф к инструментам
            self.game.craft_speed_multiplier *= 1.1

# ====== Core Game ======
class Gradostroi:
    def __init__(self, config: Optional[GameConfig] = None):
        self.cfg = config or GameConfig()
        if self.cfg.rng_seed is not None:
            random.seed(self.cfg.rng_seed)

        self._init_game_state()
        self._init_constants()
        self._init_economy()
        self._init_buildings()
        self._init_events()
        self._init_advanced_systems()
        self._init_population()
        self.cfg.apply_difficulty(self)

        # autosave machinery
        self.save = SaveManager()
        self.autosave_every = 5  # дней

    # ---- init blocks
    def _init_game_state(self):
        self.day = 0
        self.multiplier_mode = 0
        self.research_progress = 0.0
        self.research_complete = False
        self.victory_achieved = False
        self.craft_speed_multiplier = 1.0
        self.research_bonus = 1.0
        self.food_production_multiplier = 1.0
        self.happiness = 50.0  # 0..100
        self.eco_industry_penalty = 1.0  # модификатор для экоштрафов

    def _init_constants(self):
        self.MULTIPLIERS = [1, 10, 100]
        self.STORAGE_BASE_CAPACITY = 50
        self.STORAGE_PER_BUILDING = 75

        self.mining_actions = {
            '1': {'wood': 5, 'wine': 1},
            '2': {'wood': 1, 'wine': 3},
            '3': {'rock': 3},
            '4': {'food': 3, 'water': 3},
            '5': {'sand': 3},
            '6': {'clay': 3},
        }

        self.recipes: Dict[str, Recipe] = {
            'coal':  Recipe({'wood': 1}, {'coal': 1}, "Уголь"),
            'steel': Recipe({'coal': 1, 'iron': 1}, {'steel': 1.5}, "Сталь"),
            'bronze': Recipe({'cooper': 7, 'tin': 3, 'food': 1}, {'bronze': 10}, "Бронза"),
            'acid':  Recipe({'sulfur': 1, 'water': 1}, {'sulfur_acid': 0.5}, "Серная кислота"),
            'clorine': Recipe({'salt': 1}, {'clorine': 1}, "Хлор"),
            'instr': Recipe({'bronze': 1, 'wood': 1}, {'instrument': 1}, "Инструменты"),
            'ancient_tool': Recipe({'instrument': 2, 'steel': 1, 'research': 20}, {'ancient_tool': 1}, "Древний Инструмент", "forge_of_souls"),
        }

    def _init_economy(self):
        self.storage_count = 1
        self.resources = defaultdict(float, {
            'wood': 10, 'wine': 10, 'rock': 10, 'food': 12, 'water': 0,
            'sand': 0, 'clay': 0, 'iron': 0, 'cooper': 0, 'tin': 0, 'nickel': 0, 'plumb': 0,
            'salt': 0, 'sulfur': 0, 'coal': 0, 'steel': 0, 'bronze': 0, 'sulfur_acid': 0,
            'clorine': 0, 'builder_materials': 0, 'instrument': 0, 'ancient_tool': 0, 'herbs': 0
        })

    def _init_buildings(self):
        self.buildings = defaultdict(int, {'les': 0, 'sob': 0, 'kam': 0, 'pol': 0, 'pes': 0, 'gli': 0})
        self.building_production = {
            'les': {'wood': 2},
            'sob': {'wine': 1, 'herbs': 0.5},
            'kam': {'rock': 2},
            'pol': {'food': 3},
            'pes': {'sand': 2},
            'gli': {'clay': 2}
        }
        self.building_costs = {
            'les': {'wood': 15, 'rock': 5},
            'sob': {'wood': 10, 'rock': 3, 'herbs': 2},
            'kam': {'wood': 8, 'rock': 10},
            'pol': {'wood': 5, 'water': 10},
            'pes': {'wood': 12, 'rock': 8},
            'gli': {'wood': 10, 'rock': 6},
            'store': {'wood': 20, 'rock': 15}
        }

    def _init_events(self):
        self.allah_event = random.randint(20, 60)
        self.globu_event = random.randint(120, 180)
        self.event_duration = random.randint(20, 60)
        self.random_events: List[Tuple[str, Dict[str, float]]] = []

    def _init_advanced_systems(self):
        self.ecosystem = WorldEcosystem(self)
        self.market = DynamicMarket(self)
        self.legacy_system = LegacySystem(self)
        self.lore_system = LoreSystem(self)
        self._init_technology_tree()
        self._init_characters()

    def _init_population(self):
        self.population = self.cfg.base_population
        self.idle_workers = self.population  # свободные
        self.workers: Dict[str, int] = defaultdict(int)  # по зданиям

    def _init_technology_tree(self):
        self.technologies: Dict[str, Technology] = {
            "basic_agriculture": Technology("Базовое сельское хозяйство", "Улучшенные методы выращивания пищи",
                                            {"research": 20}, [], {"food_production": 1.5}),
            "advanced_mining": Technology("Продвинутая добыча", "Эффективные методы добычи ресурсов",
                                          {"research": 40, "instrument": 5}, ["basic_agriculture"], {"mining_efficiency": 1.6}),
            "ecology": Technology("Экология", "Понимание баланса природы",
                                  {"research": 60}, ["basic_agriculture"], {"eco_production_bonus": 1.1}),
            "industrial_revolution": Technology("Промышленная революция", "Массовое производство и автоматизация",
                                                {"research": 100, "steel": 20, "coal": 30}, ["advanced_mining"],
                                                {"production_speed": 1.5, "pollution": 1.2})
        }
        self.researched_techs: List[str] = []

    def _init_characters(self):
        self.characters: List[Character] = [
            Character("Старейшина Леса", "Древний хранитель лесов, чутко реагирующий на экологию",
                      {"wisdom": 8, "ecology": 9, "diplomacy": 7}, {"player": 50}, [],
                      ["Защитить священную рощу", "Восстановить биоразнообразие"], ["environmentalist", "wise", "patient"]),
            Character("Мастер Горных Дел", "Шахтёр и геолог, ценит технологии",
                      {"mining": 9, "crafting": 7, "strength": 8}, {"player": 30}, [],
                      ["Найти редкие руды", "Улучшить инструменты"], ["pragmatic", "blacksmith", "progressive"]),
            Character("Хранительница Знаний", "Хранит секреты древних цивилизаций",
                      {"knowledge": 10, "research": 8, "medicine": 6}, {"player": 40}, [],
                      ["Исследовать древние руины", "Восстановить утраченные знания"], ["scholar", "curious", "traditionalist"])
        ]

    # ---- helpers/properties
    @property
    def current_multiplier(self) -> int:
        return self.MULTIPLIERS[self.multiplier_mode]

    @property
    def storage_capacity(self) -> int:
        return self.STORAGE_BASE_CAPACITY + self.STORAGE_PER_BUILDING * self.storage_count

    def workers_total(self) -> int:
        return sum(self.workers.values())

    def _happiness_mod(self) -> float:
        # 50 → 1.0; каждые +10 счастья = +5% прод, каждые -10 = -5% (ограничим)
        return max(0.8, min(1.2, 1.0 + (self.happiness - 50.0) * 0.005))

    def get_hostility_modifier(self) -> float:
        d = self.day
        if self.allah_event <= d <= self.allah_event + self.event_duration: return 2.0
        if self.globu_event <= d <= self.globu_event + self.event_duration * 2: return 0.1
        if self.globu_event * 2 <= d <= self.globu_event * 2 + self.event_duration * 3: return 0.01
        if self.globu_event * 5 <= d <= self.globu_event * 5 + self.event_duration * 5: return 0.001
        return 1.0

    def get_market_modifier(self) -> float:
        d = self.day
        return 1.5 if self.allah_event <= d <= self.allah_event + self.event_duration else 1.0

    def adjust_resource(self, key: str, delta: float):
        if delta > 0 and key != 'wine':  # валюта не капится складом
            self.resources[key] = min(self.resources[key] + delta, self.storage_capacity)
        else:
            self.resources[key] += delta

    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    # ---- systems
    def process_mining(self, choice: str):
        if choice not in self.mining_actions:
            print("Неизвестное действие добычи."); return
        action = self.mining_actions[choice]
        eco = self.ecosystem.get_production_modifier()
        base = self.current_multiplier * self.get_hostility_modifier() * self._happiness_mod()

        # реакция персонажей
        if choice == '1':
            for c in self.characters:
                if 'environmentalist' in c.personality_traits:
                    c.react_to_action('deforestation')

        for resource, amount in action.items():
            prod = amount * base * eco
            self.adjust_resource(resource, prod)

        # пассивное производство от зданий + рабочие
        for bld, prod_map in self.building_production.items():
            count = self.buildings[bld]
            if count <= 0: continue
            workers_here = self.workers[bld]
            worker_bonus = 1.0 + 0.15 * min(workers_here, 5)  # до +75% на 5 рабов
            for res, base_p in prod_map.items():
                p = base_p * count * eco * worker_bonus
                if res == 'food':
                    p *= self.food_production_multiplier
                self.adjust_resource(res, p)

    def process_crafting(self):
        print("\n📜 Доступные рецепты:")
        available = []
        idx = 0
        for key, r in self.recipes.items():
            # требуется технология?
            if r.required_tech and r.required_tech not in self.lore_system.discovered_lore and r.required_tech not in self.researched_techs:
                continue
            idx += 1; available.append((key, r))
            print(f"  {idx}. {r.name}")
        if not available:
            print("  Нет доступных рецептов."); return

        s = input("→ ").strip()
        if not s.isdigit(): print("Введите номер."); return
        i = int(s) - 1
        if not (0 <= i < len(available)): print("Неверный выбор."); return
        key, r = available[i]

        mult = self.current_multiplier * self.get_hostility_modifier() * self.craft_speed_multiplier
        # проверка
        for res, amt in r.inputs.items():
            need = amt * mult
            if res == 'research':
                if self.research_progress < need: print("Не хватает исследований."); return
            else:
                if self.resources[res] < need: print("Не хватает ресурсов."); return
        # списание
        for res, amt in r.inputs.items():
            need = amt * mult
            if res == 'research':
                self.research_progress -= need
            else:
                self.adjust_resource(res, -need)
        # выпуск
        for res, amt in r.outputs.items():
            self.adjust_resource(res, amt * mult)
        print(f"✅ Создано: {r.name}")

    def process_building(self):
        opts = [
            ("1", "Лесопилка", "les", "Производит дерево"),
            ("2", "Хижина травника", "sob", "Производит вино и травы"),
            ("3", "Каменоломня", "kam", "Производит камень"),
            ("4", "Поле пшеницы", "pol", "Производит еду"),
            ("5", "Песчаный карьер", "pes", "Производит песок"),
            ("6", "Глиняный карьер", "gli", "Производит глину"),
            ("7", "Склад", "store", "+75 к вместимости"),
            ("8", "Распределить рабочих", None, ""),
            ("9", "Отмена", None, "")
        ]
        print("\n🏗️  Доступные постройки:")
        for key, name, btype, desc in opts[:-2]:
            if btype:
                cost = self.building_costs.get(btype, {})
                cost_str = ", ".join(f"{k}:{v}" for k, v in cost.items())
                print(f"  {key}. {name} ({cost_str}) — {desc}")
            else:
                print(f"  {key}. {name}")

        choice = input("→ ").strip()
        if choice == "9": return
        if choice == "8":
            self._assign_workers_menu(); return

        row = next((o for o in opts if o[0] == choice), None)
        if not row: print("Неверный выбор."); return
        _, name, btype, _ = row
        cost = self.building_costs['store'] if btype == 'store' else self.building_costs[btype]
        scaled = {r: v * (1 + self.buildings[btype] * 0.1) for r, v in cost.items()}

        if not all(self.resources[r] >= amt for r, amt in scaled.items()):
            print("Недостаточно материалов."); print(f"Нужно: {scaled}"); return
        for r, amt in scaled.items():
            self.adjust_resource(r, -amt)

        if btype == 'store':
            self.storage_count += 1
        else:
            self.buildings[btype] += 1
            for c in self.characters:
                if btype == 'les' and 'environmentalist' in c.personality_traits:
                    c.react_to_action('build_sawmill')
                elif btype == 'sob' and 'scholar' in c.personality_traits:
                    c.react_to_action('build_herbalist')
        print(f"✅ {name} построено!")

    def _assign_workers_menu(self):
        print("\n👷 Рабочие (ввод: 'имя_здания количество', напр. 'les 2'; 'done' — закончить)")
        print(f"Свободно: {self.idle_workers}, всего: {self.population}")
        for b, cnt in self.buildings.items():
            if cnt > 0:
                print(f"  {b}: здания={cnt}, рабочие={self.workers[b]}")
        while True:
            s = input("→ ").strip().lower()
            if s in ("done", "d", ""):
                break
            parts = s.split()
            if len(parts) != 2: print("Формат: <тип> <число>"); continue
            b, n = parts[0], parts[1]
            if b not in self.buildings or self.buildings[b] <= 0: print("Нет такого здания/0 шт."); continue
            if not n.isdigit(): print("Число!"); continue
            n = int(n)
            delta = n - self.workers[b]
            if delta > 0 and delta > self.idle_workers: print("Недостаточно свободных."); continue
            self.workers[b] = max(0, n)
            self.idle_workers = self.population - self.workers_total()
            print(f"Ок. {b} → {self.workers[b]} (свободно {self.idle_workers})")

    def process_research(self):
        print("\n🔬 Исследования:")
        print("1. Исследовать ресурс → прогресс")
        print("2. Древо технологий")
        print("3. Тайны предков")
        print("4. Отмена")
        ch = input("→ ").strip()
        if ch == "1":
            self._research_resources()
        elif ch == "2":
            self._technology_menu()
        elif ch == "3":
            self._lore_menu()

    def _research_resources(self):
        print("Введите ресурс для исследований:")
        resource = input("→ ").strip().lower()
        if resource not in self.resources or self.resources[resource] <= 0:
            print("Ресурс недоступен."); return
        value = self.resources[resource] * 0.02 * self.research_bonus
        self.research_progress += value
        self.resources[resource] = 0
        if self.research_progress >= 100 and not self.research_complete:
            self.research_complete = True
            print("🎉 Исследования завершены! Научная победа!")
            self._check_victory()
        else:
            print(f"🔬 Прогресс: {self.research_progress:.1f}%")

    def _technology_menu(self):
        print("\n🌳 Древо технологий:")
        avail: List[Tuple[str, Technology]] = []
        idx = 0
        for tid, t in self.technologies.items():
            if t.researched:
                status = "✅ Исследовано"
            else:
                req_ok = all(req in self.researched_techs for req in t.required_techs)
                res_ok = all(self.resources[r] >= amt for r, amt in t.cost.items() if r != "research")
                r_ok = self.research_progress >= t.cost.get("research", 0)
                if req_ok and res_ok and r_ok:
                    status = "🔓 Доступно"
                    idx += 1; avail.append((tid, t))
                else:
                    status = "🔒 Заблокировано"
            req_str = f" | Требуется: {', '.join(t.required_techs)}" if t.required_techs else ""
            cost_str = ", ".join(f"{k}:{v}" for k, v in t.cost.items())
            print(f"  {t.name} - {status}{req_str}\n     {t.description}\n     Стоимость: {cost_str}")
        if not avail:
            print("Нет доступных технологий."); return
        print("Введите номер технологии:")
        s = input("→ ").strip()
        if not s.isdigit(): print("Число!"); return
        i = int(s) - 1
        if not (0 <= i < len(avail)): print("Неверный выбор."); return
        tid, t = avail[i]
        self._research_technology(tid, t)

    def _research_technology(self, tid: str, t: Technology):
        for r, amt in t.cost.items():
            if r != "research":
                self.adjust_resource(r, -amt)
        t.researched = True
        if tid not in self.researched_techs:
            self.researched_techs.append(tid)
        for eff, val in t.effects.items():
            if eff == "food_production":
                self.food_production_multiplier = max(self.food_production_multiplier, float(val))
            elif eff == "mining_efficiency":
                for action in self.mining_actions.values():
                    for k in list(action.keys()):
                        action[k] = action.get(k, 0) * float(val)
            elif eff == "eco_production_bonus":
                self.happiness += 2
            elif eff == "production_speed":
                self.craft_speed_multiplier *= float(val)
        print(f"✅ Исследовано: {t.name}")

    def _lore_menu(self):
        print("\n🔮 Тайны предков:")
        for sid, s in self.lore_system.ancients_secrets.items():
            status = "✅ Открыто" if s["discovered"] else "🔍 Доступно"
            cost = ", ".join(f"{k}:{v}" for k, v in s["cost"].items())
            print(f"  {s['name']} - {status}\n     {s['description']}\n     Стоимость: {cost}")
        print("Введите id/название тайны (или Enter):")
        q = input("→ ").strip().lower()
        if not q: return
        sid = None
        for k, s in self.lore_system.ancients_secrets.items():
            if k == q or s["name"].lower() == q:
                sid = k; break
        if not sid: print("Не найдено."); return
        if not self.lore_system.discover_secret(sid):
            print("Недоступно/не хватает ресурсов.")

    def process_character_interaction(self):
        print("\n👥 Персонажи:")
        for i, c in enumerate(self.characters, 1):
            print(f"{i}. {c.name} — {c.get_relationship_status()}")
        s = input("→ ").strip()
        if not s.isdigit(): print("Число!"); return
        i = int(s) - 1
        if not (0 <= i < len(self.characters)): print("Неверный выбор."); return
        self._interact_with_character(self.characters[i])

    def _interact_with_character(self, c: Character):
        print(f"\n{c.name}\nОтношение: {c.get_relationship_status()}\n{c.description}")
        if c.quests_offered:
            print("\n📜 Квесты:")
            for q in c.quests_offered:
                print("  -", q)
        print("\nДействия: 1.Поговорить  2.Торговать  3.Помочь  4.Назад")
        ch = input("→ ").strip()
        if ch == "1":
            self._talk_to_character(c)
        elif ch == "2":
            self._trade_with_character(c)
        elif ch == "3":
            self._help_character_quest(c)

    def _talk_to_character(self, c: Character):
        r = c.relationships.get('player', 0)
        msgs = [
            (-100, f"{c.name}: 'Уходи.'"),
            (-20,  f"{c.name}: 'Нам не о чем говорить.'"),
            (0,    f"{c.name}: 'Посмотрим на твои дела.'"),
            (20,   f"{c.name}: 'Время покажет.'"),
            (40,   f"{c.name}: 'Стараешься — это видно.'"),
            (60,   f"{c.name}: 'Уважаю твой подход.'"),
            (80,   f"{c.name}: 'Доверяю тебе тайны.'")
        ]
        msg = msgs[0][1]
        for thr, m in msgs:
            if r >= thr: msg = m
        print(msg)
        if r < 80:
            c.relationships['player'] = min(100, r + 5)
            print("(Отношения улучшены)")

    def _trade_with_character(self, c: Character):
        if c.relationships.get('player', 0) < 20:
            print(f"{c.name}: 'Пока нет доверия.'"); return
        offers = {
            "Старейшина Леса": [("wood", 0.85), ("herbs", 1.25)],
            "Мастер Горных Дел": [("rock", 0.75), ("instrument", 1.45)],
            "Хранительница Знаний": [("food", 1.1), ("ancient_tool", 3.2)]
        }.get(c.name, [])
        if not offers:
            print("Пока нет предложений."); return
        print(f"Торг с {c.name}:")
        for i, (res, mod) in enumerate(offers, 1):
            price = self.market.get_current_price(res) * mod * (0.98 if c.relationships.get('player',0) >= 60 else 1.0)
            print(f"{i}. {res} — {price:.2f} вина/ед.")
        s = input("№ ресурса → ").strip()
        if not s.isdigit(): print("Число!"); return
        i = int(s) - 1
        if not (0 <= i < len(offers)): print("Неверно."); return
        res, mod = offers[i]
        try:
            amt = float(input("Количество: ").strip())
        except Exception:
            print("Число!"); return
        ok = self.market.execute_trade(res, amt, True)
        if ok:
            print("Сделка успешна.")
            c.relationships['player'] = min(100, c.relationships.get('player', 0) + 2)
        else:
            print("Не удалось купить.")

    def _help_character_quest(self, c: Character):
        if not c.quests_offered:
            print("Квестов нет."); return
        print(f"Квесты {c.name}:")
        for i, q in enumerate(c.quests_offered, 1):
            print(f"{i}. {q}")
        # пример: эко-квест
        if "Защитить священную рощу" in c.quests_offered:
            if self.ecosystem.biome_health['forest'] >= 80:
                print("✅ Квест выполнен.")
                c.quests_offered.remove("Защитить священную рощу")
                c.relationships['player'] += 25
                self.resources['ancient_tool'] += 1
                print("Награда: Древний Инструмент")
            else:
                print("Подними здоровье леса до 80+")

    def process_market(self):
        print("\n💰 Рынок: 1.Купить  2.Продать  3.Цены  4.Назад")
        ch = input("→ ").strip()
        if ch == "1": self._buy_resources()
        elif ch == "2": self._sell_resources()
        elif ch == "3": self._show_market_info()

    def _buy_resources(self):
        pool = ['wood','rock','food','coal','steel','herbs','iron','tin','cooper','salt','sulfur']
        for i, r in enumerate(pool, 1):
            print(f"{i}. {r} — {self.market.get_current_price(r):.2f} вина/ед.")
        s = input("№ → ").strip()
        if not s.isdigit(): print("Число!"); return
        i = int(s) - 1
        if not (0 <= i < len(pool)): print("Неверно."); return
        r = pool[i]
        try:
            amt = float(input("Количество: ").strip())
        except Exception:
            print("Число!"); return
        if self.market.execute_trade(r, amt, True): print("Покупка успешна.")
        else: print("Недостаточно вина.")

    def _sell_resources(self):
        pool = [k for k,v in self.resources.items() if v > 0 and k != 'wine']
        if not pool: print("Продавать нечего."); return
        for i, r in enumerate(pool, 1):
            print(f"{i}. {r} — {self.market.get_current_price(r):.2f} вина/ед. (есть {self.resources[r]:.0f})")
        s = input("№ → ").strip()
        if not s.isdigit(): print("Число!"); return
        i = int(s) - 1
        if not (0 <= i < len(pool)): print("Неверно."); return
        r = pool[i]
        try:
            amt = float(input("Количество: ").strip())
        except Exception:
            print("Число!"); return
        if self.market.execute_trade(r, amt, False): print("Продажа успешна.")
        else: print("Недостаточно ресурса.")

    def _show_market_info(self):
        res = ['wood','rock','food','coal','steel','bronze','instrument','herbs','iron','tin','cooper','salt','sulfur']
        print("\n📊 Рынок:")
        for r in res:
            price = self.market.get_current_price(r)
            available = self.resources[r]
            sat = available / (self.storage_capacity or 1)
            trend = "📉 перепроизв." if sat > 0.8 else ("📈 дефицит" if sat < 0.2 else "➡️ стаб.")
            print(f"  {r}: {price:.2f} вина, {trend}")

    def toggle_multiplier(self):
        self.multiplier_mode = (self.multiplier_mode + 1) % len(self.MULTIPLIERS)
        print(f"Множитель: x{self.current_multiplier}")

    def process_random_events(self):
        if random.random() < 0.12:
            events = [
                ("🌧️ Проливные дожди — урожайность ↑", {"food": 8}),
                ("🌪️ Буря повредила строения", {"wood": -5, "rock": -4}),
                ("🎭 Караван — выгодная сделка", {"wine": 14}),
                ("🔥 Лесной пожар", {"wood": -10, "food": -4}, "forest_down"),
                ("💎 Новое месторождение", {"iron": 6, "coal": 4})
            ]
            pick = random.choice(events)
            text, eff = pick[0], pick[1]
            print(f"\n⚡ Событие: {text}")
            for r, a in eff.items():
                self.adjust_resource(r, a)
            if len(pick) == 3 and pick[2] == "forest_down":
                self.ecosystem.biome_health['forest'] = max(0.0, self.ecosystem.biome_health['forest'] - 5)

    def _check_victory(self):
        checks = [
            (self.research_complete, VictoryType.TECHNOLOGICAL, "Научная победа!"),
            (sum(self.resources.values()) > 650, VictoryType.ECONOMIC, "Экономическая победа!"),
            (self.ecosystem.get_overall_health() > 85, VictoryType.ECOLOGICAL, "Экологическая победа!"),
            (len(self.lore_system.discovered_lore) >= 2, VictoryType.CULTURAL, "Культурная победа!")
        ]
        for cond, vtype, msg in checks:
            if cond and not self.victory_achieved:
                self.victory_achieved = True
                print(f"\n🎉 {msg}")
                return True
        return False

    # ---- HUD
    def _display_status(self):
        eco_health = self.ecosystem.get_overall_health()
        eco_status = self.ecosystem.get_health_status()
        if RICH:
            t = Table.grid(expand=True)
            t.add_row(Text(f"🏙️  Градострой: Наследие Предков — День {self.day}", style="bold"))
            t.add_row(f"Население: {self.population} (свободно {self.idle_workers}) | Счастье: {self.happiness:.0f} | Множитель x{self.current_multiplier}")
            t.add_row(f"📦 Склад: {self.storage_capacity} | 🔬 Исслед.: {self.research_progress:.1f}% | 🌍 Экология: {eco_health:.0f}% ({eco_status.value})")
            console.print(Panel(t, box=box.ROUNDED))
            # ресурсы
            rtab = Table(box=box.SIMPLE, title="Ресурсы", show_lines=False)
            for col in ["wood","wine","rock","food","water","coal","steel","bronze","instrument","herbs","ancient_tool"]:
                rtab.add_column(col, justify="right")
            rtab.add_row(*[f"{self.resources[k]:.0f}" for k in ["wood","wine","rock","food","water","coal","steel","bronze","instrument","herbs","ancient_tool"]])
            console.print(rtab)
            # здания
            b_active = {k:v for k,v in self.buildings.items() if v>0}
            if b_active:
                btab = Table(box=box.MINIMAL, title="Постройки")
                btab.add_column("Тип"); btab.add_column("Кол-во"); btab.add_column("Рабочие")
                for k,v in b_active.items():
                    btab.add_row(k, str(v), str(self.workers[k]))
                console.print(btab)
        else:
            print(f"\n🏙️  День {self.day} | 👥 {self.population} (idle {self.idle_workers}) | 🙂 {self.happiness:.0f} | x{self.current_multiplier}")
            print(f"📦 {self.storage_capacity} | 🔬 {self.research_progress:.1f}% | 🌍 {eco_health:.0f}% ({eco_status.value})")
            main = ['wood','wine','rock','food','water']
            adv  = ['coal','steel','bronze','instrument','herbs','ancient_tool']
            print("Основные:", " | ".join(f"{r}:{self.resources[r]:.0f}" for r in main))
            print("Продвинутые:", " | ".join(f"{r}:{self.resources[r]:.0f}" for r in adv if self.resources[r]>0))
            b_active = {k:v for k,v in self.buildings.items() if v>0}
            if b_active:
                print("Постройки:", " | ".join(f"{k}:{v}(wrk:{self.workers[k]})" for k,v in b_active.items()))

    # ---- save/load
    def serialize(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "multiplier_mode": self.multiplier_mode,
            "research_progress": self.research_progress,
            "research_complete": self.research_complete,
            "victory_achieved": self.victory_achieved,
            "craft_speed_multiplier": self.craft_speed_multiplier,
            "research_bonus": self.research_bonus,
            "food_production_multiplier": self.food_production_multiplier,
            "happiness": self.happiness,
            "eco_industry_penalty": self.eco_industry_penalty,
            "resources": dict(self.resources),
            "buildings": dict(self.buildings),
            "storage_count": self.storage_count,
            "population": self.population,
            "idle_workers": self.idle_workers,
            "workers": dict(self.workers),
            "researched_techs": list(self.researched_techs),
            "characters": [
                {"name": c.name, "relationships": c.relationships, "quests": c.quests_offered, "memory": c.memory}
                for c in self.characters
            ],
            "lore": {"discovered": list(self.lore_system.discovered_lore)},
            "events": {"allah": self.allah_event, "globu": self.globu_event, "dur": self.event_duration}
        }

    def deserialize(self, data: Dict[str, Any]):
        self.day = data.get("day", 0)
        self.multiplier_mode = data.get("multiplier_mode", 0)
        self.research_progress = data.get("research_progress", 0.0)
        self.research_complete = data.get("research_complete", False)
        self.victory_achieved = data.get("victory_achieved", False)
        self.craft_speed_multiplier = data.get("craft_speed_multiplier", 1.0)
        self.research_bonus = data.get("research_bonus", 1.0)
        self.food_production_multiplier = data.get("food_production_multiplier", 1.0)
        self.happiness = data.get("happiness", 50.0)
        self.eco_industry_penalty = data.get("eco_industry_penalty", 1.0)
        self.resources = defaultdict(float, data.get("resources", {}))
        self.buildings = defaultdict(int, data.get("buildings", {}))
        self.storage_count = data.get("storage_count", 1)
        self.population = data.get("population", self.cfg.base_population)
        self.idle_workers = data.get("idle_workers", self.population)
        self.workers = defaultdict(int, data.get("workers", {}))
        self.researched_techs = data.get("researched_techs", [])
        # restore characters by name
        name_to_char = {c.name: c for c in self.characters}
        for cd in data.get("characters", []):
            c = name_to_char.get(cd["name"])
            if c:
                c.relationships = cd.get("relationships", c.relationships)
                c.quests_offered = cd.get("quests", c.quests_offered)
                c.memory = cd.get("memory", c.memory)
        self.lore_system.discovered_lore = data.get("lore", {}).get("discovered", [])
        ev = data.get("events", {})
        self.allah_event = ev.get("allah", self.allah_event)
        self.globu_event = ev.get("globu", self.globu_event)
        self.event_duration = ev.get("dur", self.event_duration)

    # ---- day end
    def _end_of_day(self):
        # расход еды: население
        food_need = self.population * self.cfg.pop_food_per_day
        if self.resources['food'] >= food_need:
            self.adjust_resource('food', -food_need)
            self.happiness = min(100.0, self.happiness + 0.5)
        else:
            # голод → счастье падает быстрее, смертность небольшая
            deficit = food_need - self.resources['food']
            self.resources['food'] = 0
            self.happiness = max(0.0, self.happiness - 2.5 - deficit*0.5)
            if random.random() < 0.1:
                if self.population > 1:
                    self.population -= 1
                    self.idle_workers = max(0, self.population - self.workers_total())
                    print("⚠️  Голод унес жизнь жителя.")

        # естественное стремление счастья к 50
        if self.happiness > 50: self.happiness = max(50.0, self.happiness - self.cfg.happiness_decay)
        elif self.happiness < 50: self.happiness = min(50.0, self.happiness + self.cfg.happiness_decay)

        # редкий прирост населения
        if self.happiness >= 70 and random.random() < 0.12:
            self.population += 1
            self.idle_workers += 1
            print("👶 В посёлке родился ребёнок (+1 население).")

        # автосейв
        if self.day % self.autosave_every == 0:
            self.save.save(self.serialize())

    # ---- main loop
    def game_loop(self):
        print("🚀 Добро пожаловать в 'Градострой: Наследие Предков+'")
        print("Команды: 1–6 добыча | 7 строить | 8 крафт | 9 исследования | C персонажи | M рынок | T техи | L лор | 0 множитель | S сохранить | R загрузить | H помощь | D сложность* | Q выход")
        first_turn = True
        while not self.victory_achieved:
            self.clear_screen()
            self._display_status()

            # апдейт
            self.ecosystem.update_ecosystem()
            self.legacy_system.check_achievements()
            self.process_random_events()

            print("\n🎮 Ход: ", end="")
            choice = input().strip().lower()

            if choice in [str(i) for i in range(1,7)]:
                self.process_mining(choice)
                first_turn = False
            elif choice == '7': self.process_building(); first_turn = False
            elif choice == '8': self.process_crafting(); first_turn = False
            elif choice == '9': self.process_research(); first_turn = False
            elif choice == 'c': self.process_character_interaction(); first_turn = False
            elif choice == 'm': self.process_market(); first_turn = False
            elif choice == 't': self._technology_menu(); first_turn = False
            elif choice == 'l': self._lore_menu(); first_turn = False
            elif choice == '0': self.toggle_multiplier()
            elif choice == 's': self.save.save(self.serialize()); print("💾 Сохранено.")
            elif choice == 'r':
                data = self.save.load()
                if data: self.deserialize(data); print("📂 Загружено.")
                else: print("Нет сохранения.")
            elif choice == 'h':
                print("Справка: добывайте ресурсы, стройте, распределяйте рабочих, держите экологию и счастье в балансе.")
                print("Победы: тех/эко/эко/культура. Вино — валюта, не ограничено складом.")
            elif choice == 'd':
                if first_turn:
                    print("Выберите сложность: easy/normal/hard")
                    d = input("→ ").strip().lower()
                    if d in ('easy','normal','hard'):
                        self.cfg.difficulty = Difficulty(d)
                        self.cfg.apply_difficulty(self)
                        print(f"Сложность: {d}")
                    else:
                        print("Неверно.")
                else:
                    print("Сложность меняется только до первого действия.")
            elif choice == 'q':
                self.save.save(self.serialize())
                print("Выход..."); break
            else:
                print("Неизвестная команда.")
                input("Enter..."); continue

            # конец дня
            self.day += 1
            self._end_of_day()
            if self._check_victory(): break

        # финал
        self.clear_screen()
        if self.victory_achieved:
            vtype, title, score = self.legacy_system.calculate_final_legacy()
            print("🎉🎉🎉 ПОБЕДА! 🎉🎉🎉")
            print(f"Тип: {vtype.value}\nТитул: {title}\nСчёт: {score:.2f}")
        else:
            print("До встречи!")
        # статистика
        print(f"\n📊 Итоги:")
        print(f"Исследовано технологий: {len(self.researched_techs)}")
        print(f"Открыто тайн: {len(self.lore_system.discovered_lore)}")
        print(f"Построено зданий: {sum(self.buildings.values())}")
        print(f"Экостатус: {self.ecosystem.get_health_status().value}")

# ---- entry
def main():
    g = Gradostroi()
    # автозагрузка, если есть сейв
    data = g.save.load()
    if data:
        g.deserialize(data)
        print("📂 Найдено сохранение — загружено.")
    try:
        g.game_loop()
    except KeyboardInterrupt:
        try:
            g.save.save(g.serialize())
            print("\nСейв выполнен. Пока!")
        except Exception:
            print("\nПока!")

# ========= PYGAME INTEGRATION FOR GRADOSTROI (drop-in) =========
# Требует: pip install pygame
import time as _time
import sys as _sys

try:
    import pygame as _pg
except Exception as _e:
    _pg = None
    print("⚠️  pygame не установлен. Установи: pip install pygame")

# ---- 1) Адаптер недостающих методов ядра (без ломки классов) ----
def _patch_game_api(_GameCls):
    # быстрый билд: game.build_quick('les'|'sob'|'kam'|'pol'|'pes'|'gli'|'store')
    if not hasattr(_GameCls, "build_quick"):
        def build_quick(self, btype: str) -> bool:
            if btype not in self.building_costs and btype != 'store':
                return False
            cost = self.building_costs.get(btype, {'wood': 20, 'rock': 15}) if btype != 'store' else {'wood':20, 'rock':15}
            scaled = {r: v * (1 + self.buildings[btype] * 0.1) for r, v in cost.items()} if btype != 'store' else cost
            if not all(self.resources[r] >= amt for r, amt in scaled.items()):
                return False
            for r, amt in scaled.items():
                self.adjust_resource(r, -amt)
            if btype == 'store':
                self.storage_count += 1
            else:
                self.buildings[btype] += 1
            return True
        setattr(_GameCls, "build_quick", build_quick)

    # один «тик» игрового дня без консоли
    if not hasattr(_GameCls, "tick_once"):
        def tick_once(self):
            # то же, что делает один цикл в game_loop
            self.ecosystem.update_ecosystem()
            self.legacy_system.check_achievements()
            self.process_random_events()
            self.day += 1
            self._end_of_day()
            self._check_victory()
        setattr(_GameCls, "tick_once", tick_once)

    # безопасные геттеры для HUD
    if not hasattr(_GameCls, "get_eco_tuple"):
        def get_eco_tuple(self):
            return self.ecosystem.get_overall_health(), self.ecosystem.get_health_status().value
        setattr(_GameCls, "get_eco_tuple", get_eco_tuple)

# вызов патча для уже определённого Gradostroi (он у тебя выше в файле)
try:
    _patch_game_api(Gradostroi)
except NameError:
    pass  # если ты вынес адаптер в отдельный модуль — импортни Gradostroi перед этим блоком.

# ---- 2) Визуальный слой PygameView ----
class PygameView:
    def __init__(self, game: "Gradostroi", w: int = 1280, h: int = 720):
        if _pg is None:
            raise RuntimeError("pygame не установлен.")
        _pg.init()
        self.game = game
        self.screen = _pg.display.set_mode((w, h))
        _pg.display.set_caption("Градострой: Наследие Предков — Pygame UI")
        self.font = _pg.font.SysFont("arial", 18)
        self.clock = _pg.time.Clock()
        self.running = True
        self.cell = 44
        self.grid_w, self.grid_h = 10, 6
        self.grid_origin = (380, 90)
        self.last_day_ts = _time.time()
        self.sec_per_day = 3.0  # 1 день = 3 сек

        # быстрые билды на F-клавишах
        self.quick_build_map = {
            _pg.K_F1: "les", _pg.K_F2: "sob", _pg.K_F3: "kam",
            _pg.K_F4: "pol", _pg.K_F5: "pes", _pg.K_F6: "gli",
            _pg.K_F7: "store"
        }

    # ---------- drawing ----------
    def _txt(self, s, xy, color=(230,230,230)):
        self.screen.blit(self.font.render(s, True, color), xy)

    def _panel(self, rect, fill=(35,30,28), border=(90,90,120)):
        _pg.draw.rect(self.screen, fill, rect)
        _pg.draw.rect(self.screen, border, rect, 2)

    def draw_hud(self):
        g = self.game
        eco_val, eco_name = g.get_eco_tuple()
        x0, y0 = 20, 16
        self._panel(_pg.Rect(12, 10, 340, 250), fill=(35, 30, 28))
        self._panel(_pg.Rect(12, 275, 340, 170), fill=(35, 30, 28))
        self._txt(f"📅 День {g.day}", (x0, y0))
        self._txt(f"👥 Население: {getattr(g, 'population', 0)} (idle {getattr(g, 'idle_workers', 0)})", (x0, y0+26))
        self._txt(f"🙂 Счастье: {getattr(g, 'happiness', 50):.0f}", (x0, y0+52))
        self._txt(f"⚡ Множитель: x{g.current_multiplier}", (x0, y0+78))
        self._txt(f"📦 Склад: {g.storage_capacity}  |  Склады: {g.storage_count}", (x0, y0+104))
        self._txt(f"🌍 Экология: {eco_val:.0f}% ({eco_name})", (x0, y0+130))
        self._txt(f"🔬 Исследования: {g.research_progress:.1f}%", (x0, y0+156))

        main = ["wood","wine","rock","food","water"]
        adv  = ["coal","steel","bronze","instrument","herbs","ancient_tool"]
        y = y0+188
        # --- ресурсы ---
        self._txt("Ресурсы:", (x0, y))
        y += 22

        # Основные
        main = ["wood", "wine", "rock", "food", "water"]
        adv = ["coal", "steel", "bronze", "instrument", "herbs", "ancient_tool"]

        # Колонка 1
        col1_x = x0
        col2_x = x0 + 160
        max_rows = max(len(main), len(adv))
        for i in range(max_rows):
            if i < len(main):
                r = main[i]
                self._txt(f"{r:>10}: {self.game.resources[r]:.0f}", (col1_x, y + i * 20))
            if i < len(adv):
                r = adv[i]
                val = self.game.resources[r]
                if val > 0:
                    self._txt(f"{r:>10}: {val:.0f}", (col2_x, y + i * 20))

        # панель помощи
        self._panel(_pg.Rect(12, 275, 340, 170))
        y = 285
        for s in [
            "1…6 — добыча (как в консоли)",
            "F1..F6 — быстрые постройки",
            "F7 — склад (+75 вместимости)",
            "0 — множитель",
            "S/R — сохранить/загрузить",
            "N — следующий день",
            "Q/Esc — выход"
        ]:
            self._txt(s, (20, y)); y += 22

    def draw_map(self):
        # сетка
        gx, gy = self.grid_origin
        for j in range(self.grid_h):
            for i in range(self.grid_w):
                r = _pg.Rect(gx + i*self.cell, gy + j*self.cell, self.cell-2, self.cell-2)
                _pg.draw.rect(self.screen, (42,46,44), r)

        # простая раскладка зданий по типам
        palette = {
            "les": (120,170,120), "sob": (150,120,170), "kam": (140,140,140),
            "pol": (190,180,110), "pes": (200,190,150), "gli": (180,140,110),
            "store": (130,160,200)
        }
        idx = 0
        for btype, count in self.game.buildings.items():
            for _ in range(count):
                x = idx % self.grid_w
                y = idx // self.grid_w
                r = _pg.Rect(gx + x*self.cell+1, gy + y*self.cell+1, self.cell-4, self.cell-4)
                _pg.draw.rect(self.screen, palette.get(btype, (100,100,100)), r)
                self._txt(btype[:3], (r.x+4, r.y+10), (15,15,15))
                idx += 1

    # ---------- input/loop ----------
    def handle_key(self, key):
        g = self.game
        if key in ( _pg.K_1, _pg.K_2, _pg.K_3, _pg.K_4, _pg.K_5, _pg.K_6):
            choice = chr(key)  # '1'..'6'
            g.process_mining(choice)
        elif key in self.quick_build_map:
            btype = self.quick_build_map[key]
            ok = g.build_quick(btype)
            # лёгкий фидбек в консоль (окно не блокируем)
            if not ok:
                print(f"❌ Нет ресурсов для постройки {btype}")
        elif key == _pg.K_0:
            g.toggle_multiplier()
        elif key == _pg.K_s:
            # ожидаем, что есть SaveManager (в твоём Gradostroi+ есть)
            if hasattr(g, "save"):
                g.save.save(g.serialize())
                print("💾 Сохранено")
        elif key == _pg.K_r:
            if hasattr(g, "save"):
                data = g.save.load()
                if data:
                    g.deserialize(data)
                    print("📂 Загружено")
                else:
                    print("— Нет сохранения")
        elif key == _pg.K_n:
            g.tick_once()
        elif key in (_pg.K_q, _pg.K_ESCAPE):
            self.running = False

    def run(self):
        while self.running and not self.game.victory_achieved:
            for e in _pg.event.get():
                if e.type == _pg.QUIT:
                    self.running = False
                elif e.type == _pg.KEYDOWN:
                    self.handle_key(e.key)

            # авто-день каждые sec_per_day
            now = _time.time()
            if now - self.last_day_ts >= self.sec_per_day:
                self.game.tick_once()
                self.last_day_ts = now

            # рендер
            self.screen.fill((28,24,22))
            self.draw_hud()
            self.draw_map()
            _pg.display.flip()
            self.clock.tick(60)

        # финал
        _pg.quit()
        if self.game.victory_achieved:
            vtype, title, score = self.game.legacy_system.calculate_final_legacy()
            print("🎉🎉🎉 ПОБЕДА! 🎉🎉🎉")
            print(f"Тип: {vtype.value}\nТитул: {title}\nСчёт: {score:.2f}")

# ---- 3) Альтернативный вход: запуск Pygame вместо консоли ----
def run_pygame_ui():
    g = Gradostroi()           # твой полноценный класс
    # автозагрузка если есть сейв
    if hasattr(g, "save"):
        data = g.save.load()
        if data: g.deserialize(data)
    ui = PygameView(g)
    ui.run()

# Если хочешь запускать pygame по флагу:
#   python your_file.py --ui
if __name__ == "__main__" and "--ui" in _sys.argv and _pg is not None:
    run_pygame_ui()
# ========= END OF PYGAME INTEGRATION =========
