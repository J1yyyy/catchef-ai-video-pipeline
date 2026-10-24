import random
from pathlib import Path


class MenuError(ValueError):
    pass


def load_dishes(dishes_path: Path) -> list[str]:
    if not dishes_path.exists():
        raise MenuError(f"菜品文件不存在：{dishes_path}")

    dishes: list[str] = []
    with dishes_path.open("r", encoding="utf-8") as file:
        for line in file:
            dish = line.strip()
            if not dish or dish.startswith("#"):
                continue
            dishes.append(dish)

    if not dishes:
        raise MenuError(f"菜品文件为空或只有注释：{dishes_path}")

    return dishes


def select_menu(dishes: list[str], min_count: int, max_count: int) -> list[str]:
    if len(dishes) < min_count:
        raise MenuError(f"菜品数量不足：至少需要 {min_count} 个，当前只有 {len(dishes)} 个")

    actual_max = min(max_count, len(dishes))
    count = random.randint(min_count, actual_max)
    return random.sample(dishes, count)
