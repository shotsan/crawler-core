"""
Popup and overlay handler module for the web crawler.
Handles various types of popups, overlays, and modal dialogs.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, List

from playwright.async_api import Page


class PopupHandler:
    """Handles popup and overlay dismissal for web scraping."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.debug_mode = os.getenv('POPUP_DEBUG', 'false').lower() == 'true'
        self.debug_dir = Path('popup_debug_screenshots')
        if self.debug_mode:
            self.debug_dir.mkdir(exist_ok=True)
            self.logger.info(f"Popup debug mode enabled - screenshots will be saved to {self.debug_dir}")

    async def _take_debug_screenshot(self, page: Page, step_name: str) -> None:
        """Take a debug screenshot after each popup handling step."""
        if not self.debug_mode:
            return

        try:
            # Create a safe filename
            safe_name = step_name.replace(' ', '_').replace('/', '_').lower()
            screenshot_path = self.debug_dir / f"popup_debug_{safe_name}.png"

            await page.screenshot(path=str(screenshot_path), full_page=True)
            self.logger.info(f"📸 Debug screenshot taken: {screenshot_path}")
        except Exception as e:
            self.logger.error(f"Failed to take debug screenshot for {step_name}: {e}")

    async def handle_popups(self, page: Page, strategy: str = "conservative", site_selectors: Optional[List[str]] = None) -> None:
        """
        Main entry point for popup handling with different strategies.

        Args:
            page: Playwright page object
            strategy: Handling strategy - "conservative", "aggressive", or "none"
            site_selectors: List of site-specific selectors discovered in Phase 1.5
        """
        if strategy == "none":
            self.logger.debug("Popup handling disabled")
            return

        self.logger.info(f"🎯 Starting popup handling with strategy: {strategy}")
        await self._take_debug_screenshot(page, "popup_start")

        if strategy == "conservative":
            await self._handle_conservative(page, site_selectors)
        elif strategy == "aggressive":
            await self._handle_aggressive(page)
        else:
            self.logger.warning(f"Unknown popup handling strategy: {strategy}")
            await self._handle_conservative(page)

        self.logger.info("✅ Popup handling completed")
        await self._take_debug_screenshot(page, "popup_end")

    async def _handle_conservative(self, page: Page, site_selectors: Optional[List[str]] = None) -> None:
        """
        Conservative popup handling - safe and reliable approach.
        """
        self.logger.info("🚀 Starting conservative popup handling")

        # Strategy 1: Try keyboard ESC first (safest)
        self.logger.info("📌 Step 1: Trying ESC key")
        await self._try_escape_key(page)
        await self._take_debug_screenshot(page, "after_escape_key")
        await asyncio.sleep(0.2)

        # Strategy 2: Handle cookie banners (very common)
        self.logger.info(f"📌 Step 2: Handling cookie consent popups (using {len(site_selectors) if site_selectors else 0} site-specific selectors)")
        await self._handle_cookie_consent_popups(page, site_selectors)
        await asyncio.sleep(0.5)  # Wait before screenshot
        await self._take_debug_screenshot(page, "after_cookie_consent")
        
        # Additional check: verify cookie banner is actually gone, if not try again
        # ALWAYS run aggressive cleanup for OneTrust to ensure it's completely removed
        try:
            await asyncio.sleep(1.0)  # Wait longer for any animations/transitions
            
            # ALWAYS force remove OneTrust elements (they can persist even after clicking)
            self.logger.info("🧹 Running aggressive OneTrust cleanup to ensure complete removal...")
            removed_count = await page.evaluate("""
                () => {
                    let removed = 0;
                    const selectors = [
                        '#onetrust-banner-sdk',
                        '#onetrust-pc-sdk',
                        '#onetrust-consent-sdk',
                        '.onetrust-banner-container',
                        '.onetrust-pc-container',
                        '[id*="onetrust"]',
                        '[class*="onetrust-banner"]',
                        '[class*="onetrust-pc"]',
                        '[class*="cookie-banner"]',
                        '[class*="consent-banner"]'
                    ];
                    
                    selectors.forEach(sel => {
                        try {
                            const elements = document.querySelectorAll(sel);
                            elements.forEach(el => {
                                if (el) {
                                    // Multiple removal methods
                                    el.style.display = 'none';
                                    el.style.visibility = 'hidden';
                                    el.style.opacity = '0';
                                    el.style.height = '0';
                                    el.style.width = '0';
                                    el.style.position = 'absolute';
                                    el.style.left = '-9999px';
                                    el.style.top = '-9999px';
                                    el.setAttribute('hidden', 'true');
                                    el.setAttribute('aria-hidden', 'true');
                                    el.removeAttribute('class');
                                    el.remove();
                                    removed++;
                                }
                            });
                        } catch(e) {}
                    });
                    
                    // Also remove any iframes that might contain OneTrust
                    try {
                        const iframes = document.querySelectorAll('iframe');
                        iframes.forEach(iframe => {
                            try {
                                const src = iframe.src || '';
                                if (src.includes('onetrust') || src.includes('cookie')) {
                                    iframe.remove();
                                    removed++;
                                }
                            } catch(e) {}
                        });
                    } catch(e) {}
                    
                    return removed;
                }
            """)
            self.logger.info(f"🗑️ Aggressive cleanup removed {removed_count} OneTrust/cookie banner elements")
            
            # Wait a bit more and verify
            await asyncio.sleep(0.5)
            cookie_banner_still_visible = await page.evaluate("""
                () => {
                    const indicators = [
                        document.querySelector('#onetrust-banner-sdk'),
                        document.querySelector('.onetrust-banner-container'),
                        document.querySelector('#onetrust-pc-sdk'),
                        document.querySelector('[id*="onetrust"]'),
                        document.querySelector('[class*="onetrust-banner"]'),
                        document.querySelector('[class*="cookie-banner"]'),
                        document.querySelector('[class*="consent-banner"]')
                    ];
                    return indicators.some(el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        // Check if element is actually visible
                        return style.display !== 'none' && 
                               style.visibility !== 'hidden' && 
                               style.opacity !== '0' &&
                               rect.width > 0 && 
                               rect.height > 0;
                    });
                }
            """)
            
            if cookie_banner_still_visible:
                self.logger.warning("⚠️ Cookie banner STILL visible after cleanup, attempting final FORCE removal...")
                # One more aggressive pass
                await page.evaluate("""
                    () => {
                        // Remove ALL elements with onetrust in id or class
                        const allElements = document.querySelectorAll('*');
                        allElements.forEach(el => {
                            const id = el.id || '';
                            const className = el.className || '';
                            if ((typeof className === 'string' && className.toLowerCase().includes('onetrust')) ||
                                id.toLowerCase().includes('onetrust')) {
                                el.style.display = 'none';
                                el.remove();
                            }
                        });
                    }
                """)
                self.logger.info("🗑️ Final aggressive removal completed")
                await asyncio.sleep(0.5)
            else:
                self.logger.info("✅ Cookie banner verification: No visible banners found")
        except Exception as e:
            self.logger.warning(f"Error in cookie banner verification/cleanup: {e}")
        
        # Take a verification screenshot after aggressive cleanup
        await self._take_debug_screenshot(page, "after_aggressive_cleanup")
        await asyncio.sleep(0.3)

        # Strategy 3: Click obvious close buttons
        self.logger.info("📌 Step 3: Clicking basic close buttons")
        await self._click_close_buttons_basic(page)
        await self._take_debug_screenshot(page, "after_close_buttons")
        await asyncio.sleep(0.2)

        # Strategy 4: Final gentle cleanup
        self.logger.info("📌 Step 4: Final gentle overlay cleanup")
        await self._final_overlay_cleanup_conservative(page)
        await self._take_debug_screenshot(page, "after_final_cleanup")

        # Short wait for animations
        await asyncio.sleep(0.5)
        self.logger.info("✅ Conservative popup handling completed")

    async def _handle_aggressive(self, page: Page) -> None:
        """
        Aggressive popup handling - comprehensive but potentially risky.
        """
        self.logger.debug("Starting aggressive popup handling")

        # Strategy 1: Remove high z-index overlays via JavaScript
        await self._remove_high_z_index_elements(page)

        # Strategy 2: Handle cookie banners and consent popups
        await self._handle_cookie_consent_popups(page)

        # Strategy 3: Dismiss modal dialogs and overlays
        await self._dismiss_modal_dialogs(page)

        # Strategy 4: Click common close buttons
        await self._click_close_buttons(page)

        # Strategy 5: Try keyboard shortcuts
        await self._try_keyboard_dismissals(page)

        # Strategy 6: Remove fixed/absolute positioned overlays
        await self._remove_positioned_overlays(page)

        # Strategy 7: Handle age verification popups
        await self._handle_age_verification(page)

        # Strategy 8: Final cleanup - remove any remaining overlays
        await self._final_overlay_cleanup(page)

        # Wait for any animations to complete
        await asyncio.sleep(1.0)

    async def _try_escape_key(self, page: Page) -> None:
        """Try pressing Escape key to dismiss popups."""
        try:
            self.logger.debug("🔴 Pressing ESC key to dismiss popups")
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.5)
            self.logger.info("✅ ESC key pressed successfully")
        except Exception as e:
            self.logger.error(f"❌ Error pressing ESC key: {e}")

    async def _handle_cookie_consent_popups(self, page: Page, site_selectors: Optional[List[str]] = None) -> None:
        """Handle cookie consent and GDPR popups."""
        self.logger.info("🍪 Handling cookie consent popups")

        # Prioritize high z-index selectors - they're strong popup indicators
        high_z_selectors = []
        other_selectors = []
        if site_selectors:
            for selector in site_selectors:
                # Prioritize high z-index overlays and known popup patterns
                if any(keyword in str(selector).lower() for keyword in ['onetrust', 'usercentrics', 'cookie', 'consent', 'gdpr', 'modal', 'dialog', 'overlay', 'popup']):
                    high_z_selectors.append(selector)
                else:
                    other_selectors.append(selector)
        
        # Start with high z-index selectors first, then others
        cookie_selectors = high_z_selectors + other_selectors
        if site_selectors:
            self.logger.info(f"🎯 Using {len(site_selectors)} discovered selectors ({len(high_z_selectors)} high-priority, {len(other_selectors)} others)")
        
        # Special handling for OneTrust - add common OneTrust selectors if we detected OneTrust
        onetrust_detected = any('onetrust' in str(s).lower() for s in (site_selectors or []))
        if onetrust_detected:
            self.logger.info("🍪 OneTrust detected, adding OneTrust-specific selectors")
            onetrust_selectors = [
                '#onetrust-banner-sdk',
                '#onetrust-pc-sdk',
                '#onetrust-consent-sdk',
                '.onetrust-banner-container',
                '.onetrust-pc-container',
                '[id*="onetrust"]',
                '[class*="onetrust"]',
                '#onetrust-accept-btn-handler',
                '#onetrust-pc-btn-handler',
                'button[id*="onetrust-accept"]',
                'button[id*="onetrust-pc-accept"]'
            ]
            # Add OneTrust selectors at the beginning for priority
            cookie_selectors = onetrust_selectors + cookie_selectors
            self.logger.info(f"🍪 Added {len(onetrust_selectors)} OneTrust-specific selectors")

        # Add general cookie banner selectors as fallback
        general_selectors = [
            # Common cookie banner selectors
            '[class*="cookie"]', '[id*="cookie"]',
            '[class*="consent"]', '[id*="consent"]',
            '[class*="gdpr"]', '[id*="gdpr"]',
            '[class*="cmp"]', '[id*="cmp"]',
            '[data-testid*="cookie"]', '[data-testid*="consent"]',
            # Specific platform selectors
            '#usercentrics-root', '#cookiebot', '.fc-consent-root',
            '.gdpr-banner', '.cookie-banner', '.consent-banner',
            # Additional e-commerce patterns
            '[class*="privacy"]', '[id*="privacy"]',
            '[class*="accept-all"]', '[id*="accept-all"]',
            '.cookie-accept-all', '.privacy-accept-all'
        ]

        cookie_selectors.extend(general_selectors)

        self.logger.info(f"🔍 Checking {len(cookie_selectors)} cookie selectors (including {len(general_selectors)} general patterns)")

        for selector in cookie_selectors:
            try:
                self.logger.info(f"🔎 Checking selector: {selector}")

                # First, check if the selector itself exists
                # For OneTrust, wait a bit and try multiple times as it loads dynamically
                container = None
                if 'onetrust' in selector.lower():
                    # Try multiple times for OneTrust as it may load dynamically
                    for attempt in range(3):
                        container = await page.query_selector(selector)
                        if container:
                            break
                        await asyncio.sleep(0.3)
                    if not container:
                        # Try case-insensitive search for OneTrust
                        self.logger.info(f"🔍 OneTrust selector {selector} not found, trying case-insensitive search...")
                        container = await page.evaluate(f"""
                            (sel) => {{
                                // Try exact match first
                                let el = document.querySelector(sel);
                                if (el) return true;
                                
                                // Try case-insensitive class/id match
                                const allElements = document.querySelectorAll('*');
                                const searchLower = sel.toLowerCase();
                                
                                for (let elem of allElements) {{
                                    if (elem.id && elem.id.toLowerCase().includes('onetrust')) {{
                                        return true;
                                    }}
                                    if (elem.className && typeof elem.className === 'string') {{
                                        if (elem.className.toLowerCase().includes('onetrust') || 
                                            elem.className.toLowerCase().includes('banner-container')) {{
                                            return true;
                                        }}
                                    }}
                                }}
                                return false;
                            }}
                        """, selector)
                        if container:
                            # If found via JS, use a more generic selector
                            if '#' in selector:
                                container = await page.query_selector('[id*="onetrust"]')
                            else:
                                container = await page.query_selector('[class*="onetrust"]')
                
                if not container:
                    container = await page.query_selector(selector)
                
                if not container:
                    self.logger.info(f"⚠️ Container {selector} not found in DOM, skipping")
                    continue
                
                # Check if container is visible
                try:
                    is_visible = await container.is_visible()
                    if not is_visible:
                        self.logger.info(f"⚠️ Container {selector} exists but not visible, trying to remove anyway...")
                        # Still try to remove it even if not visible
                        await page.evaluate(f"""
                            (sel) => {{
                                const el = document.querySelector(sel);
                                if (el) {{
                                    el.style.display = 'none';
                                    el.remove();
                                    return true;
                                }}
                                return false;
                            }}
                        """, selector)
                        continue
                except Exception as e:
                    self.logger.debug(f"Error checking visibility: {e}")
                
                self.logger.info(f"✅ Container {selector} found and visible, looking for buttons...")

                # Try to find accept/reject buttons with expanded patterns
                accept_buttons = await page.query_selector_all(
                    f'{selector} button[class*="accept"], '
                    f'{selector} button[class*="agree"], '
                    f'{selector} button[class*="ok"], '
                    f'{selector} [data-testid*="accept"], '
                    f'{selector} [aria-label*="accept"], '
                    f'{selector} button[class*="allow"], '
                    f'{selector} button[class*="yes"], '
                    f'{selector} button[data-action*="accept"], '
                    f'{selector} button[data-testid*="accept"], '
                    f'{selector} a[class*="accept"], '  # Sometimes links are used
                    f'{selector} a[class*="agree"], '
                    # OneTrust specific patterns
                    f'{selector} #onetrust-accept-btn-handler, '
                    f'{selector} button[id*="onetrust"], '
                    f'{selector} button[id*="accept"], '
                    f'{selector} [id*="accept-btn"], '
                    f'{selector} [id*="acceptBtn"], '
                    # Generic button patterns within container
                    f'{selector} button, '
                    f'{selector} [role="button"], '
                    f'{selector} a[href*="#"]'
                )

                self.logger.info(f"🎯 Found {len(accept_buttons)} potential buttons for selector {selector}")

                # If no buttons found, try to click the container itself or remove it
                if len(accept_buttons) == 0:
                    self.logger.info(f"⚠️ No buttons found in {selector}, trying alternative approaches...")
                    
                    # Try to find any clickable element in the container
                    try:
                        # Look for any button or clickable element - use more comprehensive search
                        any_buttons = await container.query_selector_all('button, [role="button"], a, [onclick], input[type="button"], input[type="submit"]')
                        self.logger.info(f"🔍 Found {len(any_buttons)} clickable elements in container {selector}")
                        
                        for btn in any_buttons[:10]:  # Check more buttons
                            try:
                                # Check visibility first
                                is_btn_visible = await btn.is_visible()
                                if not is_btn_visible:
                                    continue
                                    
                                text = await btn.inner_text()
                                text_lower = text.lower() if text else ""
                                
                                # Also check aria-label
                                aria_label = await btn.get_attribute('aria-label') or ""
                                aria_label_lower = aria_label.lower()
                                
                                # Check if button text or aria-label suggests it's an accept button
                                accept_keywords = ['accept', 'agree', 'allow', 'ok', 'okay', 'yes', 'continue', 'got it', 'i understand', 'i accept', 'allow all', 'accept all']
                                if any(keyword in text_lower for keyword in accept_keywords) or any(keyword in aria_label_lower for keyword in accept_keywords):
                                    self.logger.info(f"🖱️ Clicking button with text: '{text[:50] if text else aria_label}' in {selector}")
                                    await btn.click(timeout=2000)
                                    await asyncio.sleep(0.5)
                                    self.logger.info(f"✅ Successfully clicked button in {selector}")
                                    # DON'T return - continue checking all selectors (some sites have multiple popups)
                                    break  # Break out of button loop but continue with next selector
                            except Exception as e:
                                self.logger.debug(f"❌ Failed to click element: {e}")
                                continue
                        
                        # If still no luck, try removing/hiding the container - FORCE REMOVAL
                        self.logger.info(f"🗑️ No acceptable buttons found, FORCE removing container {selector} via JavaScript")
                        removed = await page.evaluate(f"""
                            (selector) => {{
                                try {{
                                    // Try multiple selectors in case the exact one doesn't match
                                    let el = document.querySelector(selector);
                                    if (!el) {{
                                        // Try case-insensitive class match
                                        const allElements = document.querySelectorAll('*');
                                        for (let elem of allElements) {{
                                            if (elem.className && typeof elem.className === 'string') {{
                                                if (elem.className.toLowerCase().includes('onetrust') || 
                                                    elem.className.toLowerCase().includes('banner-container')) {{
                                                    el = elem;
                                                    break;
                                                }}
                                            }}
                                        }}
                                    }}
                                    
                                    if (el) {{
                                        // Try multiple methods to ensure removal
                                        el.style.display = 'none';
                                        el.style.visibility = 'hidden';
                                        el.style.opacity = '0';
                                        el.style.height = '0';
                                        el.style.width = '0';
                                        el.style.overflow = 'hidden';
                                        el.style.position = 'absolute';
                                        el.style.left = '-9999px';
                                        el.setAttribute('hidden', 'true');
                                        el.removeAttribute('class');
                                        el.remove();
                                        
                                        // Also try to remove parent if it's a wrapper
                                        if (el.parentElement) {{
                                            const parent = el.parentElement;
                                            if (parent.className && typeof parent.className === 'string' && 
                                                (parent.className.toLowerCase().includes('onetrust') || 
                                                 parent.className.toLowerCase().includes('cookie'))) {{
                                                parent.style.display = 'none';
                                                parent.remove();
                                            }}
                                        }}
                                        
                                        return true;
                                    }}
                                }} catch(e) {{
                                    console.error('Error removing container:', e);
                                    return false;
                                }}
                                return false;
                            }}
                        """, selector)
                        if removed:
                            self.logger.info(f"✅ Successfully FORCE removed container {selector}")
                            await asyncio.sleep(0.5)
                            # DON'T return - continue checking all selectors (some sites have multiple popups)
                        else:
                            self.logger.warning(f"⚠️ Failed to remove container {selector}, will try next selector")
                        await asyncio.sleep(0.5)
                        continue
                    except Exception as e:
                        self.logger.warning(f"❌ Error with alternative approach for {selector}: {e}")
                        # Still try to remove it
                        try:
                            await page.evaluate(f"(sel) => {{ const el = document.querySelector(sel); if (el) {{ el.remove(); }} }}", selector)
                            self.logger.info(f"🗑️ Attempted emergency removal of {selector}")
                        except:
                            pass
                        continue

                # Try clicking found buttons
                for i, button in enumerate(accept_buttons[:5]):  # Increased from 3 to 5
                    try:
                        # Check if button is visible
                        is_visible = await button.is_visible()
                        if not is_visible:
                            self.logger.debug(f"⏭️ Button {i+1} not visible, skipping")
                            continue
                            
                        text = await button.inner_text()
                        self.logger.info(f"🖱️ Clicking accept button {i+1} in {selector} (text: '{text[:50] if text else 'no text'}')")
                        await button.click(timeout=2000)
                        await asyncio.sleep(0.5)
                        self.logger.info(f"✅ Successfully clicked accept button in {selector}")
                        # DON'T return - continue checking all selectors to ensure all popups are dismissed
                        # Some sites have multiple popups
                    except Exception as e:
                        self.logger.debug(f"❌ Failed to click accept button {i+1}: {e}")
                        continue
            except Exception as e:
                self.logger.debug(f"❌ Error handling cookie selector {selector}: {e}")
                continue

        # If no buttons found in containers, try enhanced text-based search for accept buttons
        self.logger.debug("🔤 Trying enhanced text-based button search")
        try:
            # Expanded text patterns for cookie/consent buttons
            text_patterns = [
                'accept all', 'accept all cookies', 'accept cookies', 'accept',
                'agree', 'agree to all', 'i agree', 'allow all', 'allow cookies', 'allow',
                'ok', 'okay', 'yes', 'continue', 'got it', 'close', 'dismiss',
                'consent', 'approve', 'confirm', 'proceed'
            ]

            # First try visible buttons with text
            for pattern in text_patterns:
                try:
                    # Find buttons containing this text (case insensitive)
                    buttons = await page.query_selector_all('button, a, [role="button"], input[type="submit"], input[type="button"]')
                    for button in buttons[:15]:  # Limit to first 15 buttons
                        try:
                            # Check if button is visible
                            is_visible = await button.is_visible()
                            if not is_visible:
                                continue

                            text_content = await button.inner_text()
                            if text_content and pattern.lower() in text_content.lower():
                                self.logger.debug(f"📝 Found visible button with text '{text_content}' matching pattern '{pattern}'")

                                # Check button position (not off-screen)
                                bbox = await button.bounding_box()
                                if bbox and bbox['y'] >= 0 and bbox['x'] >= 0:
                                    await button.click(timeout=2000)
                                    await asyncio.sleep(0.3)
                                    self.logger.info(f"✅ Successfully clicked button with text '{text_content}'")
                                    return
                        except Exception as e:
                            continue
                except Exception as e:
                    continue

            # Second attempt: look for buttons with specific attributes or data
            try:
                special_buttons = await page.query_selector_all(
                    '[data-testid*="accept"], [data-testid*="agree"], [data-testid*="consent"], '
                    '[aria-label*="accept"], [aria-label*="agree"], '
                    '[data-action*="accept"], [data-action*="agree"], '
                    '.btn-accept, .accept-btn, .consent-btn'
                )

                for button in special_buttons[:10]:
                    try:
                        is_visible = await button.is_visible()
                        if is_visible:
                            bbox = await button.bounding_box()
                            if bbox and bbox['y'] >= 0 and bbox['x'] >= 0:
                                text_content = await button.inner_text()
                                self.logger.debug(f"🎯 Found special button: '{text_content or 'no text'}'")
                                await button.click(timeout=2000)
                                await asyncio.sleep(0.3)
                                self.logger.info(f"✅ Successfully clicked special button")
                                return
                    except Exception as e:
                        continue
            except Exception as e:
                self.logger.debug(f"❌ Error in special button search: {e}")

        except Exception as e:
            self.logger.debug(f"❌ Error in enhanced text-based search: {e}")

        # Try general overlay removal techniques (better than site-specific selectors)
        await self._remove_overlay_elements(page)

        self.logger.info("🍪 Cookie consent popup handling completed (no buttons found or clicked)")

    async def _remove_overlay_elements(self, page: Page) -> None:
        """Remove overlay elements using general techniques (z-index, positioning, size)."""
        self.logger.info("🎭 Removing overlay elements using general techniques")

        try:
            # Technique 1: Remove elements with very high z-index (likely overlays) - MORE AGGRESSIVE
            removed_high_z = await page.evaluate("""
                function removeHighZIndexElements() {
                    const elements = document.querySelectorAll('*');
                    let removed = 0;

                    for (let el of elements) {
                        const computedStyle = window.getComputedStyle(el);
                        const zIndex = parseInt(computedStyle.zIndex);

                        // Remove elements with very high z-index (more aggressive threshold)
                        // But first try to click close buttons if they exist
                        if (!isNaN(zIndex) && zIndex >= 1000) {  // Changed to >= to catch z-index 1300
                            // Check if it's a modal with a close button before removing
                            const closeBtn = el.querySelector('button[class*="close"], .close, [class*="modal-close"], button[aria-label*="close"]');
                            if (closeBtn) {
                                try {
                                    closeBtn.click();
                                    // Small delay to allow click to register
                                    setTimeout(() => {}, 50);
                                } catch(e) {}
                            }
                            // Remove the element
                            el.remove();
                            removed++;
                        }

                        // Also remove elements with fixed/absolute positioning that cover significant viewport
                        if ((computedStyle.position === 'fixed' || computedStyle.position === 'absolute') &&
                            computedStyle.display !== 'none') {

                            const rect = el.getBoundingClientRect();
                            const viewportWidth = window.innerWidth;
                            const viewportHeight = window.innerHeight;

                            // If element covers more than 30% of viewport, likely an overlay (more aggressive)
                            const coverage = (rect.width * rect.height) / (viewportWidth * viewportHeight);
                            if (coverage > 0.3 && zIndex > 1) {  // Lowered thresholds
                                el.remove();
                                removed++;
                            }
                        }
                    }
                    return removed;
                }
                return removeHighZIndexElements();
            """)

            if removed_high_z > 0:
                self.logger.info(f"🎯 Removed {removed_high_z} high z-index overlay elements")
            await asyncio.sleep(0.3)  # Longer wait

        except Exception as e:
            self.logger.debug(f"❌ Error removing overlay elements: {e}")

        try:
            # Technique 2: Remove common overlay/modal classes and IDs - MORE PATTERNS
            general_overlay_patterns = [
                '.modal-overlay', '.overlay', '.popup-overlay',
                '.cookie-overlay', '.consent-overlay', '.gdpr-overlay',
                '#modal-overlay', '#overlay', '#cookie-overlay',
                '.backdrop', '.modal-backdrop', '.popup-backdrop',
                '[role="dialog"]', '[role="modal"]',
                '.modal', '.popup', '.lightbox',
                # More aggressive patterns for e-commerce sites
                '.cookie-banner', '.cookie-notice', '.cookie-popup',
                '.privacy-banner', '.consent-banner', '.gdpr-banner',
                '.notification-banner', '.alert-banner',
                '.popup-modal', '.modal-dialog', '.dialog-overlay',
                '.slide-out', '.flyout', '.dropdown-overlay'
            ]

            for pattern in general_overlay_patterns:
                try:
                    removed = await page.evaluate(f"""
                        const elements = document.querySelectorAll('{pattern}');
                        let count = 0;
                        for (let el of elements) {{
                            if (el && el.parentNode) {{
                                el.remove();
                                count++;
                            }}
                        }}
                        return count;
                    """)

                    if removed > 0:
                        self.logger.info(f"🗑️ Removed {removed} elements matching {pattern}")

                except Exception as e:
                    continue

        except Exception as e:
            self.logger.debug(f"❌ Error removing general overlay patterns: {e}")

        try:
            # Technique 3: Remove elements with common overlay attributes
            await page.evaluate("""
                function removeByAttributes() {
                    let removed = 0;

                    // Remove elements with aria-modal="true"
                    const ariaModals = document.querySelectorAll('[aria-modal="true"]');
                    for (let el of ariaModals) {
                        el.remove();
                        removed++;
                    }

                    // Remove elements with data-testid containing overlay/modal
                    const testIdElements = document.querySelectorAll('[data-testid*="overlay"], [data-testid*="modal"], [data-testid*="popup"]');
                    for (let el of testIdElements) {
                        el.remove();
                        removed++;
                    }

                    return removed;
                }
                return removeByAttributes();
            """)

            self.logger.debug("✅ Removed elements by attributes")

        except Exception as e:
            self.logger.debug(f"❌ Error removing by attributes: {e}")

        # Technique 4: Second pass - more aggressive removal after waiting
        try:
            await asyncio.sleep(0.5)  # Wait for any dynamic popups to appear

            # Remove any remaining overlays that might have appeared
            second_pass_removed = await page.evaluate("""
                function secondPassRemoval() {
                    let removed = 0;

                    // Remove any element with z-index > 100 that covers significant area
                    const allElements = document.querySelectorAll('*');
                    for (let el of allElements) {
                        const style = window.getComputedStyle(el);
                        const zIndex = parseInt(style.zIndex);
                        const rect = el.getBoundingClientRect();

                        // More aggressive: any positioned element with moderate z-index
                        if ((style.position === 'fixed' || style.position === 'absolute') &&
                            !isNaN(zIndex) && zIndex > 100 &&
                            rect.width > 100 && rect.height > 100 && // Not too small
                            style.display !== 'none') {
                            el.remove();
                            removed++;
                        }
                    }

                    // Remove any element with common overlay text patterns
                    const textElements = document.querySelectorAll('*');
                    for (let el of textElements) {
                        const text = el.textContent || '';
                        const lowerText = text.toLowerCase();

                        // Look for common popup text patterns
                        if (lowerText.includes('accept') && lowerText.includes('cookie') ||
                            lowerText.includes('gdpr') && lowerText.includes('consent') ||
                            lowerText.includes('privacy') && lowerText.includes('policy')) {

                            // If this element is likely an overlay, remove its parent container
                            let container = el;
                            for (let i = 0; i < 3 && container; i++) { // Go up 3 levels max
                                if (container.id && (container.id.includes('cookie') || container.id.includes('consent'))) {
                                    container.remove();
                                    removed++;
                                    break;
                                }
                                if (container.className && typeof container.className === 'string' &&
                                    (container.className.includes('cookie') || container.className.includes('consent'))) {
                                    container.remove();
                                    removed++;
                                    break;
                                }
                                container = container.parentElement;
                            }
                        }
                    }

                    return removed;
                }
                return secondPassRemoval();
            """)

            if second_pass_removed > 0:
                self.logger.info(f"🔄 Second pass removed {second_pass_removed} additional overlay elements")

        except Exception as e:
            self.logger.debug(f"❌ Error in second pass overlay removal: {e}")

    async def _handle_site_specific_cookies(self, page: Page) -> None:
        """Handle site-specific cookie banners for major e-commerce sites."""
        try:
            current_url = page.url
            self.logger.debug(f"🏪 Checking site-specific cookie handling for: {current_url}")

            # Victoria's Secret specific patterns
            if 'victoriassecret.com' in current_url:
                self.logger.debug("👙 Victoria's Secret detected - using specific cookie patterns")

                # Victoria's Secret often uses these patterns
                vs_selectors = [
                    '.cookie-notification', '.cookie-banner', '.cookie-consent',
                    '[data-testid*="cookie"]', '.privacy-banner', '.gdpr-modal',
                    '.consent-modal', '.cookie-popup', '.privacy-popup'
                ]

                for selector in vs_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            self.logger.debug(f"🎯 Found Victoria's Secret cookie element: {selector}")

                            # Look for accept buttons within this element
                            accept_buttons = await page.query_selector_all(
                                f'{selector} button, {selector} a, {selector} [role="button"]'
                            )

                            for button in accept_buttons[:5]:
                                try:
                                    text = await button.inner_text()
                                    text_lower = text.lower() if text else ""
                                    if any(keyword in text_lower for keyword in ['accept', 'agree', 'allow', 'ok', 'yes']):
                                        self.logger.debug(f"🖱️ Clicking VS button with text: '{text}'")
                                        await button.click(timeout=2000)
                                        await asyncio.sleep(0.5)
                                        self.logger.info(f"✅ Successfully clicked Victoria's Secret cookie accept button")
                                        return
                                except Exception as e:
                                    continue
                    except Exception as e:
                        continue

            # Add other major e-commerce sites here if needed
            # elif 'other-site.com' in current_url:
            #     # Handle other site specific patterns

        except Exception as e:
            self.logger.debug(f"❌ Error in site-specific cookie handling: {e}")

    async def _click_close_buttons_basic(self, page: Page) -> None:
        """Click basic close/dismiss buttons without complex logic."""
        self.logger.info("🔘 Clicking basic close buttons")

        basic_selectors = [
            # Most common close patterns
            'button[class*="close"]', '.close',
            'button[class*="dismiss"]', '.dismiss',
            'button[aria-label*="close"]',
            'button[class*="accept"]',  # For cookie banners
            'button[class*="ok"]'
        ]

        self.logger.debug(f"🔍 Checking {len(basic_selectors)} basic close button selectors")

        for selector in basic_selectors:
            try:
                self.logger.debug(f"🔎 Checking close selector: {selector}")
                buttons = await page.query_selector_all(selector)
                self.logger.debug(f"🎯 Found {len(buttons)} buttons for selector {selector}")

                if buttons:
                    # Just click the first one found
                    self.logger.debug(f"🖱️ Clicking first button for selector {selector}")
                    await buttons[0].click(timeout=2000)
                    await asyncio.sleep(0.3)
                    self.logger.info(f"✅ Successfully clicked basic close button: {selector}")
                    # DON'T return - continue checking all selectors (some sites have multiple popups)
                    continue
            except Exception as e:
                self.logger.debug(f"❌ Error clicking {selector}: {e}")
                continue

        self.logger.info("🔘 Basic close button clicking completed (no buttons found or clicked)")

    async def _final_overlay_cleanup_conservative(self, page: Page) -> None:
        """Conservative final cleanup - only hide obvious overlays."""
        try:
            self.logger.info("🧹 Performing conservative overlay cleanup")

            # Very conservative: only hide elements with very specific overlay patterns
            result = await page.evaluate("""
                () => {
                    // Only target the most obvious overlay patterns
                    const obviousSelectors = [
                        '.modal-backdrop.fade.show',
                        '.popup-overlay',
                        '#cookiebot'
                    ];

                    let hidden = 0;
                    obviousSelectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            el.style.display = 'none';
                            hidden++;
                        });
                    });

                    // Scroll to top
                    window.scrollTo(0, 0);

                    return hidden;
                }
            """)

            self.logger.info(f"🧹 Conservative overlay cleanup completed - hidden {result} elements")

        except Exception as e:
            self.logger.error(f"❌ Error in conservative cleanup: {e}")

    async def _remove_high_z_index_elements(self, page: Page) -> None:
        """Remove elements with very high z-index that are likely popups/overlays."""
        try:
            self.logger.debug("Removing high z-index elements")

            # More conservative: only remove elements with extremely high z-index (> 999999)
            # and that actually cover most of the screen
            removed_count = await page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('*');
                    let removed = 0;

                    for (let el of elements) {
                        const zIndex = window.getComputedStyle(el).zIndex;
                        if (zIndex && parseInt(zIndex) > 999999) {
                            // Only remove if it covers most of the viewport
                            const rect = el.getBoundingClientRect();
                            const viewport = { width: window.innerWidth, height: window.innerHeight };
                            const coverage = (rect.width * rect.height) / (viewport.width * viewport.height);

                            // Must cover at least 60% of screen and be positioned
                            if (coverage > 0.6 &&
                                (el.style.position === 'fixed' || el.style.position === 'absolute')) {
                                el.remove();
                                removed++;
                            }
                        }
                    }

                    return removed;
                }
            """)

            if removed_count > 0:
                self.logger.debug(f"Removed {removed_count} extremely high z-index elements")

        except Exception as e:
            self.logger.error(f"Error removing high z-index elements: {e}")

    async def _dismiss_modal_dialogs(self, page: Page) -> None:
        """Dismiss modal dialogs and overlays."""
        self.logger.debug("Dismissing modal dialogs")

        modal_selectors = [
            # Standard modal selectors
            '[class*="modal"]', '[id*="modal"]',
            '[class*="dialog"]', '[id*="dialog"]',
            '[class*="popup"]', '[id*="popup"]',
            '[class*="overlay"]', '[id*="overlay"]',
            '[role="dialog"]', '[role="alertdialog"]',
            # Framework specific
            '.modal-backdrop', '.overlay-backdrop',
            '.popup-overlay', '.dialog-overlay',
            # Generic overlays
            '.fixed-overlay', '.absolute-overlay'
        ]

        for selector in modal_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    # Try to hide via CSS
                    await page.evaluate("""
                        (el) => {
                            el.style.display = 'none';
                            el.style.visibility = 'hidden';
                            el.style.opacity = '0';
                        }
                    """, element)
                    self.logger.debug(f"Hidden modal element: {selector}")
            except Exception as e:
                self.logger.debug(f"Error dismissing modal {selector}: {e}")
                continue

    async def _click_close_buttons(self, page: Page) -> None:
        """Click various types of close/dismiss buttons."""
        self.logger.debug("Clicking comprehensive close buttons")

        close_selectors = [
            # Generic close buttons
            'button[class*="close"]', 'button[class*="dismiss"]',
            'button[aria-label*="close"]', 'button[aria-label*="dismiss"]',
            'button[data-testid*="close"]', 'button[data-testid*="dismiss"]',
            '.close', '.dismiss', '.close-button', '.dismiss-button',
            '[class*="close"]', '[class*="dismiss"]',

            # Specific icon classes
            '.fa-close', '.fa-times', '.icon-close', '.icon-dismiss',
            '.cross', '.x-button', '.close-icon',

            # Text-based close buttons
            'button:contains("×")', 'button:contains("✕")',
            'button:contains("Close")', 'button:contains("Dismiss")',
            'button:contains("OK")', 'button:contains("Accept")',

            # Newsletter popup close
            '[class*="newsletter"] button', '[id*="newsletter"] button',

            # Age verification
            'button[class*="yes"]', 'button[class*="confirm"]',
            'button[class*="continue"]', 'button[aria-label*="yes"]'
        ]

        for selector in close_selectors:
            try:
                buttons = await page.query_selector_all(selector)
                for button in buttons[:5]:  # Limit to prevent spam clicking
                    try:
                        # Check if button is visible and clickable
                        is_visible = await page.evaluate("""
                            (btn) => {
                                const rect = btn.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0 &&
                                       window.getComputedStyle(btn).display !== 'none' &&
                                       window.getComputedStyle(btn).visibility !== 'hidden';
                            }
                        """, button)

                        if is_visible:
                            await button.click(timeout=2000)
                            await asyncio.sleep(0.5)
                            self.logger.debug(f"Clicked close button: {selector}")
                            # DON'T return - continue checking all selectors
                            break  # Break out of loop but continue with next selector
                    except Exception as e:
                        self.logger.debug(f"Failed to click button {selector}: {e}")
                        continue
            except Exception as e:
                self.logger.debug(f"Error with selector {selector}: {e}")
                continue

    async def _try_keyboard_dismissals(self, page: Page) -> None:
        """Try keyboard shortcuts to dismiss popups."""
        self.logger.debug("Trying keyboard dismissals")

        keyboard_actions = [
            ('Escape', 0.5),      # ESC key
            ('Enter', 0.3),       # Enter key
            ('Tab', 0.2),         # Tab to next element
            ('Tab', 0.2),         # Tab again
            ('Enter', 0.3),       # Enter on focused element
        ]

        for key, delay in keyboard_actions:
            try:
                await page.keyboard.press(key)
                await asyncio.sleep(delay)
                self.logger.debug(f"Pressed {key} key")
            except Exception as e:
                self.logger.debug(f"Error pressing {key}: {e}")

    async def _remove_positioned_overlays(self, page: Page) -> None:
        """Remove fixed and absolute positioned overlays."""
        try:
            self.logger.debug("Removing positioned overlays")

            removed_count = await page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('*');
                    let removed = 0;

                    for (let el of elements) {
                        const style = window.getComputedStyle(el);
                        const position = style.position;
                        const zIndex = parseInt(style.zIndex) || 0;

                        // Remove if it's positioned and likely an overlay
                        if ((position === 'fixed' || position === 'absolute') &&
                            zIndex > 100 &&
                            (style.width.includes('%') || parseInt(style.width) > window.innerWidth * 0.7) &&
                            (style.height.includes('%') || parseInt(style.height) > window.innerHeight * 0.7)) {

                            // Additional check: if it covers most of the viewport
                            const rect = el.getBoundingClientRect();
                            const coverage = (rect.width * rect.height) / (window.innerWidth * window.innerHeight);

                            if (coverage > 0.5) {
                                el.remove();
                                removed++;
                            }
                        }
                    }

                    return removed;
                }
            """)

            if removed_count > 0:
                self.logger.debug(f"Removed {removed_count} positioned overlays")

        except Exception as e:
            self.logger.error(f"Error removing positioned overlays: {e}")

    async def _handle_age_verification(self, page: Page) -> None:
        """Handle age verification popups."""
        self.logger.debug("Handling age verification popups")

        age_selectors = [
            'button[class*="yes"]', 'button[class*="over"]',
            'button[class*="old"]', 'button[class*="continue"]',
            'button[class*="enter"]', 'button[class*="confirm"]',
            '[class*="age"] button', '[id*="age"] button'
        ]

        for selector in age_selectors:
            try:
                buttons = await page.query_selector_all(selector)
                for button in buttons[:2]:  # Usually just 1-2 options
                    try:
                        await button.click(timeout=2000)
                        await asyncio.sleep(0.5)
                        self.logger.debug(f"Handled age verification: {selector}")
                        # DON'T return - continue checking all selectors
                        break  # Break out of loop but continue with next selector
                    except Exception as e:
                        self.logger.debug(f"Failed age verification click: {e}")
                        continue
            except Exception as e:
                self.logger.debug(f"Error with age selector {selector}: {e}")
                continue

    async def _final_overlay_cleanup(self, page: Page) -> None:
        """Final cleanup of any remaining overlays using targeted methods."""
        try:
            self.logger.debug("Performing final overlay cleanup")

            # Use JavaScript to hide (not remove) common overlay patterns
            await page.evaluate("""
                () => {
                    // Hide by common class names (don't remove to avoid breaking page)
                    const selectors = [
                        '.overlay', '.popup', '.modal', '.dialog',
                        '.backdrop', '.mask', '.veil', '.curtain'
                    ];

                    selectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => {
                            // Only hide if it's likely an overlay (high z-index or covers screen)
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            const viewport = { width: window.innerWidth, height: window.innerHeight };

                            if (parseInt(style.zIndex) > 100 ||
                                (rect.width > viewport.width * 0.8 && rect.height > viewport.height * 0.8)) {
                                el.style.display = 'none';
                            }
                        });
                    });

                    // Scroll to top in case popup blocked scrolling
                    window.scrollTo(0, 0);
                }
            """)

            self.logger.debug("Completed final overlay cleanup")

        except Exception as e:
            self.logger.error(f"Error in final cleanup: {e}")
