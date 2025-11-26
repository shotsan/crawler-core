"""
Fingerprint randomization module for anti-detection.
Generates realistic browser fingerprints including user agents, viewports, timezones, and languages.
"""

import random
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


# Realistic Chrome user agents (updated versions)
CHROME_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Realistic Firefox user agents
FIREFOX_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Realistic Safari user agents
SAFARI_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

# Common desktop viewport sizes (width, height)
COMMON_VIEWPORTS = [
    (1920, 1080),  # Full HD
    (1366, 768),  # Common laptop
    (1536, 864),  # Common laptop
    (1440, 900),  # MacBook
    (1600, 900),  # Wide screen
    (1280, 720),  # HD
    (2560, 1440),  # 2K
]

# Major timezones (IANA timezone identifiers)
COMMON_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Rome",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Singapore",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Australia/Sydney",
    "Australia/Melbourne",
]

# Common language/locale combinations
COMMON_LANGUAGES = [
    "en-US",
    "en-GB",
    "en-CA",
    "en-AU",
    "fr-FR",
    "fr-CA",
    "de-DE",
    "es-ES",
    "es-MX",
    "it-IT",
    "pt-BR",
    "pt-PT",
    "ja-JP",
    "zh-CN",
    "zh-TW",
    "ko-KR",
    "ru-RU",
    "ar-SA",
    "hi-IN",
]


class FingerprintGenerator:
    """Generates randomized browser fingerprints for anti-detection."""
    
    def __init__(self):
        """Initialize the fingerprint generator."""
        self.all_user_agents = CHROME_USER_AGENTS + FIREFOX_USER_AGENTS + SAFARI_USER_AGENTS
    
    def generate_user_agent(self, browser_type: str = "random") -> str:
        """
        Generate a random realistic user agent string.
        
        Args:
            browser_type: "chrome", "firefox", "safari", or "random"
        
        Returns:
            User agent string
        """
        if browser_type == "chrome":
            return random.choice(CHROME_USER_AGENTS)
        elif browser_type == "firefox":
            return random.choice(FIREFOX_USER_AGENTS)
        elif browser_type == "safari":
            return random.choice(SAFARI_USER_AGENTS)
        else:
            return random.choice(self.all_user_agents)
    
    def generate_viewport(self) -> Dict[str, int]:
        """
        Generate a random realistic viewport size.
        
        Returns:
            Dictionary with 'width' and 'height' keys
        """
        width, height = random.choice(COMMON_VIEWPORTS)
        return {'width': width, 'height': height}
    
    def generate_timezone(self) -> str:
        """
        Generate a random timezone identifier.
        
        Returns:
            IANA timezone identifier
        """
        return random.choice(COMMON_TIMEZONES)
    
    def generate_language(self) -> str:
        """
        Generate a random language/locale string.
        
        Returns:
            Language locale string (e.g., "en-US")
        """
        return random.choice(COMMON_LANGUAGES)
    
    def generate_fingerprint(self, browser_type: str = "random") -> Dict[str, Any]:
        """
        Generate a complete randomized fingerprint for a browser context.
        
        Args:
            browser_type: "chrome", "firefox", "safari", or "random"
        
        Returns:
            Dictionary containing:
            - user_agent: User agent string
            - viewport: Dict with width and height
            - timezone_id: Timezone identifier
            - locale: Language locale string
        """
        fingerprint = {
            'user_agent': self.generate_user_agent(browser_type),
            'viewport': self.generate_viewport(),
            'timezone_id': self.generate_timezone(),
            'locale': self.generate_language(),
        }
        
        logger.debug(f"Generated fingerprint: UA={fingerprint['user_agent'][:50]}..., "
                    f"viewport={fingerprint['viewport']}, "
                    f"timezone={fingerprint['timezone_id']}, "
                    f"locale={fingerprint['locale']}")
        
        return fingerprint


# Global instance for easy access
_fingerprint_generator = FingerprintGenerator()


def get_random_fingerprint(browser_type: str = "random") -> Dict[str, Any]:
    """
    Convenience function to get a random fingerprint.
    
    Args:
        browser_type: "chrome", "firefox", "safari", or "random"
    
    Returns:
        Dictionary with fingerprint data
    """
    return _fingerprint_generator.generate_fingerprint(browser_type)

