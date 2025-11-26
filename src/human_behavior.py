"""
Human behavior simulation module for anti-detection.
Simulates realistic mouse movements, scrolling patterns, and random delays.
"""

import asyncio
import random
import logging
from typing import Optional
from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def random_mouse_movement(page: Page, num_movements: int = 2) -> None:
    """
    Simulate random mouse movements using bezier-like curves.
    
    Args:
        page: Playwright page object
        num_movements: Number of mouse movements to perform
    """
    try:
        viewport = page.viewport_size
        if not viewport:
            return
        
        width = viewport['width']
        height = viewport['height']
        
        # Start from a random position
        current_x = random.randint(100, width - 100)
        current_y = random.randint(100, height - 100)
        
        for _ in range(num_movements):
            # Generate target position with some randomness
            target_x = random.randint(100, width - 100)
            target_y = random.randint(100, height - 100)
            
            # Move mouse in steps to simulate natural movement
            steps = random.randint(5, 10)
            for step in range(steps):
                # Bezier-like interpolation
                t = step / steps
                # Add some randomness to the path
                noise_x = random.randint(-20, 20)
                noise_y = random.randint(-20, 20)
                
                x = int(current_x + (target_x - current_x) * t + noise_x)
                y = int(current_y + (target_y - current_y) * t + noise_y)
                
                # Clamp to viewport
                x = max(0, min(width, x))
                y = max(0, min(height, y))
                
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.01, 0.05))
            
            current_x = target_x
            current_y = target_y
            
            # Random pause between movements
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        logger.debug(f"Completed {num_movements} mouse movements")
    except Exception as e:
        logger.debug(f"Mouse movement simulation error (non-critical): {e}")


async def realistic_scroll(page: Page, scroll_amount: Optional[int] = None) -> None:
    """
    Simulate realistic scrolling behavior with variable speed and pauses.
    
    Args:
        page: Playwright page object
        scroll_amount: Amount to scroll (None = random amount)
    """
    try:
        if scroll_amount is None:
            # Random scroll amount (partial page scroll)
            scroll_amount = random.randint(300, 800)
        
        # Get viewport height
        viewport = page.viewport_size
        if not viewport:
            return
        viewport_height = viewport['height']
        
        # Scroll in multiple steps with variable speed
        num_steps = random.randint(3, 6)
        step_size = scroll_amount // num_steps
        
        for step in range(num_steps):
            # Variable scroll speed (sometimes faster, sometimes slower)
            scroll_speed = random.randint(step_size - 50, step_size + 50)
            
            await page.evaluate(f"window.scrollBy(0, {scroll_speed})")
            
            # Random pause between scroll steps (simulates reading)
            pause_time = random.uniform(0.2, 0.8)
            await asyncio.sleep(pause_time)
        
        # Sometimes scroll back up a bit (human behavior)
        if random.random() < 0.3:  # 30% chance
            back_scroll = random.randint(50, 200)
            await page.evaluate(f"window.scrollBy(0, -{back_scroll})")
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        logger.debug(f"Completed realistic scroll: {scroll_amount}px in {num_steps} steps")
    except Exception as e:
        logger.debug(f"Scroll simulation error (non-critical): {e}")


async def random_delay(min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
    """
    Wait for a random amount of time to simulate human thinking/reading time.
    
    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def simulate_human_interaction(page: Page, enable_mouse: bool = True, enable_scroll: bool = True) -> None:
    """
    Simulate a sequence of human-like interactions on a page.
    
    Args:
        page: Playwright page object
        enable_mouse: Whether to perform mouse movements
        enable_scroll: Whether to perform scrolling
    """
    try:
        # Random delay before starting interactions
        await random_delay(0.3, 1.0)
        
        if enable_mouse:
            # Perform some mouse movements
            await random_mouse_movement(page, num_movements=random.randint(1, 3))
        
        if enable_scroll:
            # Perform realistic scrolling
            await realistic_scroll(page)
        
        # Random delay after interactions
        await random_delay(0.2, 0.8)
        
        logger.debug("Completed human interaction simulation")
    except Exception as e:
        logger.debug(f"Human interaction simulation error (non-critical): {e}")

