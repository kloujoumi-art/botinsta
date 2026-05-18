"""
Simulation de comportement humain : délais, scrolls, mouvements de souris.
Toutes les fonctions sont async pour Playwright.
"""
import asyncio
import random
from playwright.async_api import Page


async def random_sleep(min_s: float = 2.0, max_s: float = 6.0) -> None:
    """Pause aléatoire avec légère variation supplémentaire occasionnelle."""
    delay = random.uniform(min_s, max_s)
    # 15% de chance d'ajouter une micro-hésitation
    if random.random() < 0.15:
        delay += random.uniform(1.5, 4.0)
    await asyncio.sleep(delay)


async def think_pause() -> None:
    """Longue pause simulant une distraction ou réflexion."""
    await asyncio.sleep(random.uniform(10, 30))


async def micro_pause() -> None:
    """Toute petite pause entre deux micro-actions."""
    await asyncio.sleep(random.uniform(0.1, 0.6))


async def scroll_down(page: Page, amount: int = None) -> None:
    if amount is None:
        amount = random.randint(200, 700)
    await page.evaluate(f"window.scrollBy(0, {amount})")
    await asyncio.sleep(random.uniform(0.3, 1.0))


async def scroll_up(page: Page, amount: int = None) -> None:
    if amount is None:
        amount = random.randint(100, 350)
    await page.evaluate(f"window.scrollBy(0, -{amount})")
    await asyncio.sleep(random.uniform(0.2, 0.8))


async def scroll_feed(page: Page, times: int = None) -> None:
    """Simuler un défilement naturel : descend, remonte parfois, s'arrête."""
    if times is None:
        times = random.randint(4, 10)

    for i in range(times):
        amount = random.randint(250, 650)
        await scroll_down(page, amount)
        await asyncio.sleep(random.uniform(0.6, 2.5))

        # Remontée occasionnelle (comme un humain qui reconsidère un post)
        if random.random() < 0.25:
            await scroll_up(page, random.randint(80, 250))
            await asyncio.sleep(random.uniform(1.0, 3.0))

        # Pause plus longue parfois (regarder un contenu)
        if random.random() < 0.20:
            await asyncio.sleep(random.uniform(3.0, 8.0))


async def move_mouse_naturally(page: Page, target_x: float, target_y: float) -> None:
    """Déplacer la souris en courbe vers une cible (simulation Bézier simple)."""
    start_x = random.randint(200, 800)
    start_y = random.randint(200, 600)
    steps = random.randint(12, 22)

    for i in range(steps + 1):
        t = i / steps
        # Bézier cubique avec un point de contrôle aléatoire
        cx = random.randint(300, 700)
        cy = random.randint(200, 500)
        x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * cx + t ** 2 * target_x
        y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * cy + t ** 2 * target_y
        x += random.uniform(-5, 5)
        y += random.uniform(-5, 5)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.008, 0.035))


async def human_click(page: Page, selector: str, timeout: int = 6000) -> bool:
    """Cliquer sur un élément après déplacement naturel de souris."""
    try:
        element = await page.wait_for_selector(selector, timeout=timeout)
        if not element:
            return False
        bbox = await element.bounding_box()
        if bbox:
            x = bbox["x"] + bbox["width"] * random.uniform(0.25, 0.75)
            y = bbox["y"] + bbox["height"] * random.uniform(0.25, 0.75)
            await move_mouse_naturally(page, x, y)
            await asyncio.sleep(random.uniform(0.1, 0.35))
            await page.mouse.click(x, y)
            return True
    except Exception:
        pass
    return False


async def type_like_human(element, text: str) -> None:
    """Saisir du texte avec des délais variables entre chaque caractère."""
    for char in text:
        await element.type(char, delay=random.randint(60, 210))
        if char == " ":
            await asyncio.sleep(random.uniform(0.1, 0.4))


def should_skip(probability: float = 0.12) -> bool:
    """Retourne True si l'action doit être ignorée (comportement aléatoire humain)."""
    return random.random() < probability


async def idle_gesture(page: Page) -> None:
    """Action d'inactivité aléatoire pour rester naturel."""
    choice = random.choice(["scroll_tiny_down", "scroll_tiny_up", "pause", "mouse_wander"])
    if choice == "scroll_tiny_down":
        await page.evaluate(f"window.scrollBy(0, {random.randint(50, 180)})")
    elif choice == "scroll_tiny_up":
        await page.evaluate(f"window.scrollBy(0, -{random.randint(30, 120)})")
    elif choice == "pause":
        await asyncio.sleep(random.uniform(1.5, 5.0))
    elif choice == "mouse_wander":
        await page.mouse.move(random.randint(100, 900), random.randint(100, 700))
    await asyncio.sleep(random.uniform(0.4, 1.5))
