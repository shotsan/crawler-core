"""
Core scraper module using Playwright for website crawling.
Handles page navigation, screenshot capture, HTML saving, and coordinates with popup handler.
"""

import asyncio
import logging
import os
import time
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import aiofiles
from playwright_stealth import stealth_async

from src.popup_handler import PopupHandler
from src.directory_discovery import RecursiveDirectoryDiscovery
from src.fingerprint import get_random_fingerprint
from src.rate_limiter import initialize_rate_limiter, initialize_delay_manager, wait_for_rate_limit, wait_between_pages, record_request
from src.human_behavior import simulate_human_interaction

logger = logging.getLogger(__name__)


async def _create_stealth_context(browser: Browser, config: Any = None) -> BrowserContext:
    """
    Create a browser context with randomized fingerprint.
    Note: Stealth plugin is NOT applied here - it's applied per-page if enabled in config.
    
    Args:
        browser: Playwright browser instance
        config: Optional config object (if None, uses default fingerprint)
    
    Returns:
        Browser context with randomized fingerprint
    """
    # Generate random fingerprint
    fingerprint = get_random_fingerprint()
    
    # Create context with fingerprint (no stealth plugin - stealth is applied per-page if enabled)
    context = await browser.new_context(
        viewport=fingerprint['viewport'],
        user_agent=fingerprint['user_agent'],
        locale=fingerprint['locale'],
        timezone_id=fingerprint['timezone_id'],
    )
    
    logger.debug(f"Created context with fingerprint: {fingerprint['user_agent'][:50]}...")
    
    return context


async def _apply_stealth_to_page(page: Page, config: Any = None) -> None:
    """
    Apply stealth plugin to a page (if enabled in config).
    
    Args:
        page: Playwright page object
        config: Optional config object to check if stealth is enabled
    """
    # Check if stealth is disabled in config
    if config and hasattr(config, 'enable_stealth') and not config.enable_stealth:
        logger.debug("Stealth plugin disabled in config - skipping")
        return
    
    try:
        await stealth_async(page)
        logger.debug("Applied stealth plugin to page")
    except Exception as e:
        logger.warning(f"Failed to apply stealth plugin (non-critical): {e}")


async def _verify_cloudflare_gone(page: Page, logger: logging.Logger) -> bool:
    """Verify that Cloudflare challenge is actually gone from the page. Returns True if Cloudflare is gone."""
    try:
        # Check page title - Cloudflare pages have "Just a moment..." title
        page_title = await page.title()
        if "Just a moment" in page_title or "just a moment" in page_title.lower():
            return False
        
        # Check page content for Cloudflare challenge text
        page_content = await page.content()
        if "Your connection needs to be verified before you can proceed" in page_content:
            return False
        
        # Check for Cloudflare challenge iframe
        cloudflare_iframe = await page.query_selector('iframe[src*="challenges.cloudflare.com"], iframe[src*="cloudflare"]')
        if cloudflare_iframe:
            return False
        
        # Check for Turnstile input - if it exists but has no value, challenge might still be active
        turnstile_input = await page.query_selector('input[name="cf-turnstile-response"]')
        if turnstile_input:
            # If Turnstile input exists, check if page is still showing challenge
            # by checking if the main content is still the challenge page
            has_challenge_content = await page.evaluate("""
                () => {
                    const bodyText = document.body ? document.body.textContent || '' : '';
                    const title = document.title || '';
                    return bodyText.includes('Your connection needs to be verified') || 
                           title.includes('Just a moment');
                }
            """)
            if has_challenge_content:
                return False
        
        return True
    except Exception as e:
        logger.warning(f"⚠️ Error verifying Cloudflare status: {e}")
        # On error, assume it's gone (optimistic)
        return True


async def _handle_cloudflare_challenge(page: Page, logger: logging.Logger) -> bool:
    """Handle Cloudflare bot detection challenge. Returns True if successful, False otherwise."""
    try:
        page_content = await page.content()
        initial_url = page.url
        cloudflare_detected = False
        detection_method = None
        
        # Check page title for Cloudflare (works in any language)
        page_title = await page.title()
        if "moment" in page_title.lower() or "प्रतीक्षा" in page_title or "espera" in page_title.lower():
            cloudflare_detected = True
            detection_method = "title detection"
        
        # Check for Cloudflare challenge text
        if not cloudflare_detected and "Your connection needs to be verified before you can proceed" in page_content:
            cloudflare_detected = True
            detection_method = "text detection"
        
        # Also check for Cloudflare iframe
        if not cloudflare_detected:
            cloudflare_iframe = await page.query_selector('iframe[src*="challenges.cloudflare.com"], iframe[src*="cloudflare"]')
            if cloudflare_iframe:
                cloudflare_detected = True
                detection_method = "iframe detection"
        
        if not cloudflare_detected:
            return True  # No Cloudflare, proceed normally
        
        # Check if this is Cloudflare Turnstile (newer invisible challenge)
        is_turnstile = False
        turnstile_input = await page.query_selector('input[name="cf-turnstile-response"], input[id*="cf-chl-widget"][id*="_response"]')
        if turnstile_input:
            is_turnstile = True
            logger.info(f"🛡️ Cloudflare Turnstile detected (invisible challenge - no checkbox to click)")
            logger.info(f"   Initial URL: {initial_url}")
            logger.info(f"   Turnstile will complete automatically - waiting for completion...")
        else:
            logger.info(f"🛡️ Cloudflare challenge detected via {detection_method}, attempting to solve...")
            logger.info(f"   Initial URL: {initial_url}")
        
        # Take screenshot for debugging
        try:
            debug_dir = Path('popup_debug_screenshots')
            debug_dir.mkdir(exist_ok=True)
            screenshot_path = debug_dir / f"cloudflare_detected_{int(time.time())}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"📸 Debug screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not take Cloudflare screenshot: {e}")
        
        # For Turnstile, just wait for it to complete automatically
        if is_turnstile:
            logger.info("⏳ Waiting for Cloudflare Turnstile to complete automatically...")
            max_wait_time = 30
            poll_interval = 0.5
            waited_time = 0
            url_changed = False
            
            # Wait for URL to change or for turnstile response to be populated
            while waited_time < max_wait_time:
                current_url = page.url
                if current_url != initial_url:
                    url_changed = True
                    logger.info(f"   ✅ URL changed from {initial_url} to {current_url}")
                    break
                
                # Also check if turnstile response has a value
                try:
                    turnstile_value = await page.evaluate("""
                        () => {
                            const input = document.querySelector('input[name="cf-turnstile-response"]');
                            return input ? input.value : '';
                        }
                    """)
                    if turnstile_value and len(turnstile_value) > 10:  # Turnstile tokens are long
                        logger.info(f"   ✅ Turnstile response received (token length: {len(turnstile_value)})")
                        url_changed = True
                        break
                except:
                    pass
                
                await asyncio.sleep(poll_interval)
                waited_time += poll_interval
                if waited_time % 5 == 0:
                    logger.info(f"   Still waiting for Turnstile... ({waited_time:.1f}s / {max_wait_time}s)")
            
            if url_changed:
                # CRITICAL: Verify Cloudflare is actually gone, not just URL changed
                logger.info("🔍 Verifying Cloudflare challenge is actually resolved...")
                # Reduced initial wait - if Cloudflare is rate limiting, waiting longer won't help
                await asyncio.sleep(10)  # Give page time to update after URL change
                
                # Reduced max wait and more frequent checks - if it's not done quickly, it's probably rate limited
                verification_wait = 0
                max_verification_wait = 50  # Original timeout - allow enough time for Cloudflare to complete
                check_interval = 2  # Check every 2s
                while verification_wait < max_verification_wait:
                    if await _verify_cloudflare_gone(page, logger):
                        logger.info("✅ Cloudflare Turnstile completed successfully - verified page content")
                        return True
                    await asyncio.sleep(check_interval)
                    verification_wait += check_interval
                    if int(verification_wait) % 10 == 0:  # Log every 10s
                        logger.info(f"   Still verifying Cloudflare is gone... ({verification_wait:.1f}s / {max_verification_wait}s)")
                
                # Final check
                if await _verify_cloudflare_gone(page, logger):
                    logger.info("✅ Cloudflare Turnstile completed successfully - verified page content")
                    return True
                else:
                    logger.warning("⚠️ Cloudflare Turnstile: URL changed but verification timed out")
                    logger.warning(f"   Page title: {await page.title()}")
                    logger.warning("   This may be due to rate limiting from parallel requests")
                    logger.warning("   Page will be retried later - continuing...")
                    # Return False but don't treat as critical error - will retry
                    return False
            else:
                logger.error(f"❌ Cloudflare Turnstile timed out after {max_wait_time}s")
                logger.error(f"   Initial URL: {initial_url}")
                logger.error(f"   Final URL: {page.url}")
                return False
        
        # Wait a bit for page to fully load (for non-Turnstile challenges)
        await asyncio.sleep(2)
        
        # Log all interactive elements on the page to help diagnose
        logger.info("🔍 Analyzing page for Cloudflare challenge elements...")
        page_analysis = await page.evaluate("""
            () => {
                const result = {
                    allInputs: [],
                    allButtons: [],
                    allClickable: [],
                    iframes: [],
                    challengeText: []
                };
                
                // Find all inputs
                document.querySelectorAll('input').forEach(input => {
                    const rect = input.getBoundingClientRect();
                    const style = window.getComputedStyle(input);
                    result.allInputs.push({
                        type: input.type,
                        id: input.id || '',
                        className: input.className || '',
                        name: input.name || '',
                        visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                        zIndex: style.zIndex || 'auto'
                    });
                });
                
                // Find all buttons
                document.querySelectorAll('button, [role="button"], [onclick]').forEach(btn => {
                    const rect = btn.getBoundingClientRect();
                    const style = window.getComputedStyle(btn);
                    result.allButtons.push({
                        tagName: btn.tagName,
                        id: btn.id || '',
                        className: btn.className || '',
                        text: btn.textContent?.trim().substring(0, 50) || '',
                        visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                        zIndex: style.zIndex || 'auto'
                    });
                });
                
                // Find all iframes
                document.querySelectorAll('iframe').forEach(iframe => {
                    result.iframes.push({
                        src: iframe.src || '',
                        id: iframe.id || '',
                        className: iframe.className || ''
                    });
                });
                
                // Check for challenge-related text
                const bodyText = document.body.textContent || '';
                if (bodyText.includes('robot') || bodyText.includes('verify') || bodyText.includes('challenge')) {
                    result.challengeText.push('Found challenge-related text in body');
                }
                
                return result;
            }
        """)
        
        logger.info(f"📊 Page Analysis:")
        logger.info(f"   - Total inputs found: {len(page_analysis.get('allInputs', []))}")
        logger.info(f"   - Total buttons found: {len(page_analysis.get('allButtons', []))}")
        logger.info(f"   - Total iframes found: {len(page_analysis.get('iframes', []))}")
        
        # Log ALL inputs (not just visible) - Cloudflare checkbox might be hidden initially
        all_inputs = page_analysis.get('allInputs', [])
        if all_inputs:
            logger.info(f"   - ALL inputs (including hidden):")
            for inp in all_inputs[:10]:  # Log first 10
                logger.info(f"      Input: type={inp.get('type')}, id='{inp.get('id')[:50]}', class='{inp.get('className')[:50]}', name='{inp.get('name')[:50]}', visible={inp.get('visible')}")
        
        # Log visible inputs separately
        visible_inputs = [inp for inp in all_inputs if inp.get('visible', False)]
        if visible_inputs:
            logger.info(f"   - Visible inputs: {len(visible_inputs)}")
            for inp in visible_inputs[:5]:
                logger.info(f"      Visible Input: type={inp.get('type')}, id='{inp.get('id')[:50]}', class='{inp.get('className')[:50]}'")
        else:
            logger.warning(f"   ⚠️ NO VISIBLE INPUTS FOUND - Cloudflare checkbox might be hidden or in iframe")
        
        # Log ALL buttons (not just visible)
        all_buttons = page_analysis.get('allButtons', [])
        if all_buttons:
            logger.info(f"   - ALL buttons (including hidden):")
            for btn in all_buttons[:10]:  # Log first 10
                logger.info(f"      Button: {btn.get('tagName')}, id='{btn.get('id')[:50]}', class='{btn.get('className')[:50]}', text='{btn.get('text')[:50]}', visible={btn.get('visible')}")
        
        # Log visible buttons separately
        visible_buttons = [btn for btn in all_buttons if btn.get('visible', False)]
        if visible_buttons:
            logger.info(f"   - Visible buttons: {len(visible_buttons)}")
            for btn in visible_buttons[:5]:
                logger.info(f"      Visible Button: {btn.get('tagName')}, id='{btn.get('id')[:50]}', class='{btn.get('className')[:50]}', text='{btn.get('text')[:50]}'")
        else:
            logger.warning(f"   ⚠️ NO VISIBLE BUTTONS FOUND")
        
        # Log iframes - Cloudflare challenge is often in an iframe
        iframes = page_analysis.get('iframes', [])
        if iframes:
            logger.info(f"   - Iframes found: {len(iframes)}")
            for iframe in iframes:
                src = iframe.get('src', '')
                logger.info(f"      Iframe: src='{src[:100]}', id='{iframe.get('id')[:50]}', class='{iframe.get('className')[:50]}'")
                if 'cloudflare' in src.lower() or 'challenge' in src.lower():
                    logger.warning(f"      ⚠️ CLOUDFLARE IFRAME DETECTED - challenge might be inside this iframe!")
        else:
            logger.info(f"   - No iframes found")
        
        # Check if Cloudflare challenge is in an iframe first
        cloudflare_iframe_element = None
        if iframes:
            for iframe_info in iframes:
                src = iframe_info.get('src', '')
                if 'cloudflare' in src.lower() or 'challenge' in src.lower():
                    logger.info(f"🔍 Found Cloudflare iframe, attempting to access it...")
                    try:
                        # Try to find the iframe element
                        iframe_selector = f'iframe[src*="{src.split("/")[-1][:20]}"]' if src else 'iframe[src*="cloudflare"]'
                        cloudflare_iframe_element = await page.query_selector('iframe[src*="cloudflare"], iframe[src*="challenge"]')
                        if cloudflare_iframe_element:
                            logger.info(f"   ✅ Found Cloudflare iframe element, will search inside it")
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not access Cloudflare iframe: {e}")
        
        # Look for checkbox - try multiple selectors with detailed logging
        checkbox = None
        checkbox_selectors = [
            'input[type="checkbox"]',
            'input[id*="challenge"]',
            'input[class*="challenge"]',
            'label:has-text("I\'m not a robot") input',
            'label:has-text("I am not a robot") input',
            'input[type="checkbox"][id*="cf"]',
            'input[type="checkbox"][class*="cf"]',
            '[data-ray] input[type="checkbox"]',
            '.cb-input input[type="checkbox"]',
            'input[type="checkbox"][name*="cf"]',
            '#challenge-form input[type="checkbox"]',
            'form input[type="checkbox"]'
        ]
        
        logger.info(f"🔍 Searching for Cloudflare checkbox with {len(checkbox_selectors)} selectors...")
        for i, selector in enumerate(checkbox_selectors):
            try:
                logger.info(f"   Trying selector {i+1}/{len(checkbox_selectors)}: {selector}")
                checkbox = await page.query_selector(selector)
                if checkbox:
                    is_visible = await checkbox.is_visible()
                    checkbox_info = await page.evaluate("""
                        (cb) => {
                            const rect = cb.getBoundingClientRect();
                            const style = window.getComputedStyle(cb);
                            return {
                                id: cb.id || '',
                                className: cb.className || '',
                                type: cb.type || '',
                                name: cb.name || '',
                                visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                                boundingRect: {
                                    x: rect.x,
                                    y: rect.y,
                                    width: rect.width,
                                    height: rect.height
                                },
                                parentTag: cb.parentElement ? cb.parentElement.tagName : 'none',
                                parentId: cb.parentElement ? (cb.parentElement.id || '') : '',
                                parentClass: cb.parentElement ? (cb.parentElement.className || '') : ''
                            };
                        }
                    """, checkbox)
                    logger.info(f"   ✅ Found element with selector '{selector}':")
                    logger.info(f"      ID: '{checkbox_info.get('id')}'")
                    logger.info(f"      Class: '{checkbox_info.get('className')}'")
                    logger.info(f"      Type: '{checkbox_info.get('type')}'")
                    logger.info(f"      Name: '{checkbox_info.get('name')}'")
                    logger.info(f"      Visible: {checkbox_info.get('visible')}")
                    logger.info(f"      Position: x={checkbox_info.get('boundingRect', {}).get('x')}, y={checkbox_info.get('boundingRect', {}).get('y')}")
                    logger.info(f"      Parent: {checkbox_info.get('parentTag')}, id='{checkbox_info.get('parentId')[:50]}', class='{checkbox_info.get('parentClass')[:50]}'")
                    if checkbox_info.get('visible'):
                        logger.info(f"   ✅ CHECKBOX IS VISIBLE - will attempt to click")
                        break
                    else:
                        logger.warning(f"      ⚠️ Element found but NOT VISIBLE, continuing search...")
                        checkbox = None
            except Exception as e:
                logger.warning(f"   ❌ Selector '{selector}' failed: {e}")
                continue
        
        # If checkbox not found in main page, try inside iframe
        if not checkbox and cloudflare_iframe_element:
            logger.info("🔍 Checkbox not found in main page, trying inside Cloudflare iframe...")
            try:
                iframe_frame = await cloudflare_iframe_element.content_frame()
                if iframe_frame:
                    logger.info("   ✅ Accessed iframe content frame")
                    for selector in ['input[type="checkbox"]', 'input[id*="challenge"]']:
                        try:
                            checkbox = await iframe_frame.query_selector(selector)
                            if checkbox:
                                is_visible = await checkbox.is_visible()
                                if is_visible:
                                    logger.info(f"   ✅ Found checkbox inside iframe with selector: {selector}")
                                    break
                        except:
                            continue
            except Exception as e:
                logger.warning(f"   ⚠️ Could not access iframe content: {e}")
        
        if checkbox:
            logger.info("✅ Found Cloudflare checkbox, attempting to click...")
            try:
                await checkbox.click(timeout=5000)
                logger.info("✅ Cloudflare checkbox clicked successfully")
            except Exception as e:
                logger.error(f"❌ Failed to click checkbox: {e}")
                # Try alternative click methods
                try:
                    await checkbox.evaluate("el => el.click()")
                    logger.info("✅ Clicked checkbox via JavaScript")
                except Exception as e2:
                    logger.error(f"❌ JavaScript click also failed: {e2}")
                    return False
            
            # Wait for URL to change (indicating challenge passed)
            logger.info("⏳ Waiting for Cloudflare challenge to complete (waiting for URL change)...")
            max_wait_time = 30
            poll_interval = 0.5
            waited_time = 0
            url_changed = False
            
            while waited_time < max_wait_time:
                current_url = page.url
                if current_url != initial_url:
                    url_changed = True
                    logger.info(f"   URL changed from {initial_url} to {current_url}")
                    break
                await asyncio.sleep(poll_interval)
                waited_time += poll_interval
                if waited_time % 5 == 0:  # Log every 5 seconds
                    logger.info(f"   Still waiting... ({waited_time:.1f}s / {max_wait_time}s)")
            
            if url_changed:
                # CRITICAL: Verify Cloudflare is actually gone, not just URL changed
                logger.info("🔍 Verifying Cloudflare challenge is actually resolved...")
                # Reduced initial wait - if Cloudflare is rate limiting, waiting longer won't help
                await asyncio.sleep(10)  # Give page time to update after URL change
                
                # Reduced max wait and more frequent checks - if it's not done quickly, it's probably rate limited
                verification_wait = 0
                max_verification_wait = 50  # Original timeout - allow enough time for Cloudflare to complete
                check_interval = 2  # Check every 2s
                while verification_wait < max_verification_wait:
                    if await _verify_cloudflare_gone(page, logger):
                        logger.info("✅ Cloudflare challenge completed successfully - verified page content")
                        return True
                    await asyncio.sleep(check_interval)
                    verification_wait += check_interval
                    if int(verification_wait) % 10 == 0:  # Log every 10s
                        logger.info(f"   Still verifying Cloudflare is gone... ({verification_wait:.1f}s / {max_verification_wait}s)")
                
                # Final check
                if await _verify_cloudflare_gone(page, logger):
                    logger.info("✅ Cloudflare challenge completed successfully - verified page content")
                    return True
                else:
                    logger.warning("⚠️ Cloudflare challenge: URL changed but verification timed out")
                    logger.warning("   This may be due to rate limiting from parallel requests")
                    logger.warning("   Page will be retried later - continuing...")
                    return False
            else:
                logger.error(f"❌ Cloudflare challenge timed out after {max_wait_time}s - URL did not change")
                logger.error(f"   Initial URL: {initial_url}")
                logger.error(f"   Final URL: {page.url}")
                return False
        else:
            logger.warning("⚠️ Cloudflare challenge detected but checkbox not found")
            logger.warning("   This means we detected Cloudflare but cannot find the button/checkbox to click")
            logger.warning("   Please check the debug screenshot to identify the correct selector")
            
            # Still try to wait for URL change in case it's automatic
            logger.info("⏳ Waiting for automatic Cloudflare completion (no checkbox found)...")
            max_wait_time = 30
            poll_interval = 0.5
            waited_time = 0
            url_changed = False
            
            while waited_time < max_wait_time:
                current_url = page.url
                if current_url != initial_url:
                    url_changed = True
                    logger.info(f"   URL changed from {initial_url} to {current_url}")
                    break
                await asyncio.sleep(poll_interval)
                waited_time += poll_interval
                if waited_time % 5 == 0:  # Log every 5 seconds
                    logger.info(f"   Still waiting... ({waited_time:.1f}s / {max_wait_time}s)")
            
            if url_changed:
                # CRITICAL: Verify Cloudflare is actually gone, not just URL changed
                logger.info("🔍 Verifying Cloudflare challenge is actually resolved...")
                # Reduced initial wait - if Cloudflare is rate limiting, waiting longer won't help
                await asyncio.sleep(10)  # Give page time to update after URL change
                
                # Reduced max wait and more frequent checks - if it's not done quickly, it's probably rate limited
                verification_wait = 0
                max_verification_wait = 50  # Original timeout - allow enough time for Cloudflare to complete
                check_interval = 2  # Check every 2s
                while verification_wait < max_verification_wait:
                    if await _verify_cloudflare_gone(page, logger):
                        logger.info("✅ Cloudflare challenge completed automatically - verified page content")
                        return True
                    await asyncio.sleep(check_interval)
                    verification_wait += check_interval
                    if int(verification_wait) % 10 == 0:  # Log every 10s
                        logger.info(f"   Still verifying Cloudflare is gone... ({verification_wait:.1f}s / {max_verification_wait}s)")
                
                # Final check
                if await _verify_cloudflare_gone(page, logger):
                    logger.info("✅ Cloudflare challenge completed automatically - verified page content")
                    return True
                else:
                    logger.warning("⚠️ Cloudflare challenge: URL changed but verification timed out")
                    logger.warning("   This may be due to rate limiting from parallel requests")
                    logger.warning("   Page will be retried later - continuing...")
                    return False
            else:
                logger.error(f"❌ Cloudflare challenge FAILED - checkbox not found and URL did not change after {max_wait_time}s")
                logger.error(f"   Initial URL: {initial_url}")
                logger.error(f"   Final URL: {page.url}")
                logger.error("   ACTION REQUIRED: Check debug screenshot to identify the correct button/checkbox selector")
                return False
                
    except Exception as e:
        logger.error(f"❌ Error handling Cloudflare challenge: {str(e)}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return False


async def _discover_selectors_for_url(page: Page, url: str, logger: logging.Logger) -> List[str]:
    """Discover popup selectors for a specific URL (Phase 1.5 per-worker)."""
    discovered_selectors = {}
    
    try:
        # Wait and trigger popups with user-like interactions
        await asyncio.sleep(3)
        
        # Simulate user interactions that might trigger popups
        try:
            await page.evaluate("window.scrollTo(0, 100);")
            await asyncio.sleep(1.5)
            await page.mouse.click(100, 100)
            await asyncio.sleep(1.5)
            await page.evaluate("window.scrollTo(0, 0);")
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.debug(f"Interaction error (non-critical): {e}")
        
        # Final wait for any delayed popups
        await asyncio.sleep(3)
        
        # Force a reflow to ensure all styles are computed
        await page.evaluate("document.body.offsetHeight;")
        await asyncio.sleep(0.5)
        
        # Get full HTML content and analyze it
        html_content = await page.content()
        
        # Analyze HTML for popup/cookie selectors
        logger.info("🔍 Starting HTML analysis for popup/cookie selectors...")
        selectors_found = _analyze_html_for_selectors(html_content)
        logger.info(f"📊 HTML analysis returned {len(selectors_found)} potential selectors")
        
        # Also analyze DOM for high z-index and overlay elements
        logger.info(f"🔍 Analyzing DOM for high z-index overlays")
        dom_result = await page.evaluate("""
            (function() {
                const allElements = document.querySelectorAll('*');
                const zIndexMap = new Map();

                for (let el of allElements) {
                    try {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        
                        let zIndex = parseInt(style.zIndex) || 0;
                        
                        if (isNaN(zIndex) || zIndex === 0) {
                            const inlineZ = parseInt(el.style.zIndex) || 0;
                            if (inlineZ > 0) zIndex = inlineZ;
                        }
                        
                        const position = style.position;
                        const isPositioned = position === 'fixed' || position === 'absolute' || position === 'relative';
                        
                        if (zIndex > 5 || (isPositioned && zIndex > 0)) {
                            let selector = null;
                            let selectorType = 'high_z_overlay';
                            
                            if (el.id && el.id.trim()) {
                                selector = `#${el.id}`;
                            } else if (el.className && typeof el.className === 'string' && el.className.trim()) {
                                const classes = el.className.trim().split(/\\s+/).filter(c => c.length > 0);
                                if (classes.length > 0) {
                                    selector = `.${classes[0]}`;
                                }
                            }
                            
                            if (selector) {
                                const existing = zIndexMap.get(selector);
                                if (!existing || zIndex > existing.z_index) {
                                    zIndexMap.set(selector, {
                                        selector: selector,
                                        type: selectorType,
                                        z_index: zIndex,
                                        position: position
                                    });
                                }
                            }
                        }

                        const viewportWidth = window.innerWidth;
                        const viewportHeight = window.innerHeight;
                        const coverageX = (rect.width / viewportWidth) * 100;
                        const coverageY = (rect.height / viewportHeight) * 100;

                        if ((coverageX > 30 || coverageY > 30) && rect.width > 200 && rect.height > 150) {
                            if (position === 'fixed' || position === 'absolute') {
                                let selector = null;
                                
                                if (el.id && el.id.trim()) {
                                    selector = `#${el.id}`;
                                } else if (el.className && typeof el.className === 'string' && el.className.trim()) {
                                    const classes = el.className.trim().split(/\\s+/).filter(c => c.length > 0);
                                    if (classes.length > 0) {
                                        selector = `.${classes[0]}`;
                                    }
                                }
                                
                                if (selector) {
                                    const existing = zIndexMap.get(selector);
                                    if (!existing || coverageX * coverageY > (existing.coverage || 0)) {
                                        zIndexMap.set(selector, {
                                            selector: selector,
                                            type: 'large_overlay',
                                            coverage: coverageX * coverageY,
                                            coverageX: coverageX,
                                            coverageY: coverageY
                                        });
                                    }
                                }
                            }
                        }
                    } catch (e) {
                        continue;
                    }
                }

                const selectors = Array.from(zIndexMap.values());
                const sortedSelectors = selectors
                    .sort((a, b) => {
                        return (b.z_index || 0) - (a.z_index || 0);
                    });

                return {
                    selectors: sortedSelectors
                };
            })();
        """)
        
        # Extract selectors from DOM analysis
        dom_selectors = dom_result.get('selectors', [])
        if dom_selectors:
            logger.info(f"📊 DOM Analysis found {len(dom_selectors)} overlay selectors")
        
        # Merge HTML and DOM selectors
        selectors_found.extend(dom_selectors)
        logger.info(f"📊 Total selectors after merge: {len(selectors_found)}")
        
        # Process the discovered selectors
        for item in selectors_found:
            try:
                selector = item.get('selector') if isinstance(item, dict) else str(item)
                selector_type = item.get('type', 'unknown') if isinstance(item, dict) else 'unknown'
                
                if not selector:
                    continue
                
                selector_key = f"{selector}|{selector_type}"
                if selector_key not in discovered_selectors:
                    discovered_selectors[selector_key] = selector
                    logger.info(f"🎯 Discovered {selector_type} selector: {selector}")
            except Exception as e:
                logger.debug(f"⚠️ Error processing selector item: {e}")
                continue
        
        selector_list = list(discovered_selectors.values())
        return selector_list
        
    except Exception as e:
        logger.error(f"❌ Error discovering selectors: {e}")
        return []


def _analyze_html_for_selectors(html_content: str) -> List[Dict[str, Any]]:
    """Analyze HTML content for popup and cookie selectors using regex."""
    import re
    selectors = []
    
    try:
        html_lower = html_content.lower()
        
        # Cookie banner frameworks
        frameworks = [
            ('fc-consent-root', '.fc-consent-root', 98),
            ('usercentrics-root', '#usercentrics-root', 98),
            ('cookiebot', '.cookiebot', 95),
            ('onetrust', '.onetrust-banner-container', 95),
            ('cookie-alert', '.cookie-alert', 90)
        ]
        
        for pattern, selector, confidence in frameworks:
            if pattern in html_lower:
                selectors.append({
                    'selector': selector,
                    'type': 'cookie_framework',
                    'confidence': confidence
                })
        
        # Modal/dialog elements
        modal_patterns = [
            ('role="dialog"', '[role="dialog"]', 90),
            ('role="modal"', '[role="modal"]', 90),
            ('aria-modal="true"', '[aria-modal="true"]', 95),
            ('data-modal=', '[data-modal]', 85),
            ('data-popup=', '[data-popup]', 85)
        ]
        
        for pattern, selector, confidence in modal_patterns:
            if pattern in html_lower:
                selectors.append({
                    'selector': selector,
                    'type': 'modal',
                    'confidence': confidence
                })
        
        # Cookie/consent elements by class/id
        cookie_elements = [
            ('class="[^"]*cookie[^"]*"', 'cookie', 90),
            ('id="[^"]*cookie[^"]*"', 'cookie', 95),
            ('class="[^"]*consent[^"]*"', 'consent', 90),
            ('id="[^"]*consent[^"]*"', 'consent', 95),
        ]
        
        for pattern, element_type, confidence in cookie_elements:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches[:3]:
                if 'class=' in match:
                    class_match = re.search(r'class="([^"]*cookie[^"]*)"', match, re.IGNORECASE)
                    if class_match:
                        class_value = class_match.group(1).split()[0]
                        selectors.append({
                            'selector': f'.{class_value}',
                            'type': 'cookie',
                            'confidence': confidence
                        })
                elif 'id=' in match:
                    id_match = re.search(r'id="([^"]*cookie[^"]*)"', match, re.IGNORECASE)
                    if id_match:
                        id_value = id_match.group(1)
                        selectors.append({
                            'selector': f'#{id_value}',
                            'type': 'cookie',
                            'confidence': confidence
                        })
        
        # Accept buttons
        accept_patterns = [
            (r'button[^>]*>([^<]*(?:accept|agree|allow|ok|yes|continue|got it|i understand)[^<]*)</button>', 'accept_button', 70),
            (r'<button[^>]*class="[^"]*(?:accept|agree|allow)[^"]*"', 'accept_button', 85),
        ]
        
        for pattern, selector_type, confidence in accept_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                selectors.append({
                    'selector': f'button:contains("{matches[0][:30] if isinstance(matches[0], tuple) else matches[0][:30]}")',
                    'type': selector_type,
                    'confidence': confidence
                })
        
    except Exception as e:
        logger.error(f"Error in HTML analysis: {e}")
    
    return selectors


def scrape_single_directory_worker(task_data):
    """
    Module-level worker function for multiprocessing.
    Each process launches its own independent browser instance.
    """
    try:
        import random
        import time
        import logging
        
        # Initialize rate limiter and delay manager for this worker process
        initialize_rate_limiter(task_data.get('max_requests_per_domain_per_minute', 30))
        initialize_delay_manager(
            task_data.get('delay_between_pages_min', 2.0),
            task_data.get('delay_between_pages_max', 5.0)
        )
        
        # STAGGERED START: Stagger workers to avoid all hitting at once
        # Each worker waits: task_id * 0.3 seconds (so worker 0 starts immediately, worker 1 waits 0.3s, etc.)
        task_id = task_data.get('task_id', 0)
        stagger_delay = task_id * 0.3  # Stagger by 0.3s per worker
        if stagger_delay > 0:
            worker_logger = logging.getLogger(__name__)
            worker_logger.debug(f"Worker {task_id}: Staggering start by {stagger_delay:.2f}s to avoid simultaneous requests")
            time.sleep(stagger_delay)
        
        # Import required modules in the worker process
        import asyncio
        from playwright.async_api import async_playwright
        from urllib.parse import urlparse
        import hashlib
        import aiofiles
        from pathlib import Path

        async def scrape_page():
            result = {
                'url': task_data['url'],
                'screenshot_taken': False,
                'html_saved': False,
                'error': None
            }

            async with async_playwright() as p:
                try:
                    # Launch independent browser instance for this process
                    browser = await p.chromium.launch(
                        headless=task_data['headless'],
                        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-accelerated-2d-canvas', '--no-first-run', '--no-zygote', '--single-process', '--disable-gpu']
                    )

                    # Create stealth context with randomized fingerprint
                    context = await _create_stealth_context(browser)

                    page = await context.new_page()
                    
                    # Apply stealth plugin to page (if enabled)
                    await _apply_stealth_to_page(page, task_data.get('config'))

                    # Rate limiting: wait if needed before navigation
                    await wait_for_rate_limit(task_data['url'])

                    # Navigate with faster wait condition for e-commerce sites
                    await page.goto(task_data['url'], timeout=task_data['page_load_timeout'] * 1000, wait_until='domcontentloaded')
                    
                    # Record request for rate limiting
                    record_request(task_data['url'])

                    # Create logger for this worker
                    popup_logger = logging.getLogger(f'popup_worker_{task_data["task_id"]}')

                    # PHASE 1.5: Discover selectors for this specific URL (per-worker discovery)
                    # This happens AFTER navigation but BEFORE popup handling
                    popup_logger.info(f"🔍 PHASE 1.5: Discovering popup selectors for {task_data['url']}")
                    
                    # First, handle Cloudflare if detected (must happen before discovery)
                    cloudflare_success = await _handle_cloudflare_challenge(page, popup_logger)
                    if not cloudflare_success:
                        result['error'] = "Cloudflare challenge failed"
                        return result
                    
                    # Add delay after Cloudflare to avoid hammering the server
                    if cloudflare_success:
                        await asyncio.sleep(3)  # Wait 3s after Cloudflare to be respectful

                    # Now discover selectors for this URL (after Cloudflare is handled)
                    discovered_selectors = await _discover_selectors_for_url(page, task_data['url'], popup_logger)
                    
                    if len(discovered_selectors) == 0:
                        popup_logger.warning("⚠️ No selectors discovered in Phase 1.5 - will use general patterns")
                    else:
                        popup_logger.info(f"✅ PHASE 1.5: Discovered {len(discovered_selectors)} selectors for this URL")

                    # Wait for page stabilization after discovery
                    await asyncio.sleep(task_data['wait_after_load'])
                    
                    # Human behavior simulation
                    if task_data.get('enable_mouse_movements', True) or task_data.get('enable_scrolling_simulation', True):
                        await simulate_human_interaction(
                            page,
                            enable_mouse=task_data.get('enable_mouse_movements', True),
                            enable_scroll=task_data.get('enable_scrolling_simulation', True)
                        )

                    # Use full popup handling with discovered selectors
                    from src.popup_handler import PopupHandler
                    popup_handler = PopupHandler(popup_logger)

                    # Use full popup handling strategy with discovered site selectors
                    popup_logger.info(f"🔧 Popup handler initialized with {len(discovered_selectors)} discovered selectors")
                    await popup_handler.handle_popups(
                        page,
                        strategy="aggressive",
                        site_selectors=discovered_selectors if discovered_selectors else None
                    )

                    # Additional stabilization
                    await asyncio.sleep(0.5)

                    # Generate filename based on URL path for flat directory structure
                    parsed = urlparse(task_data['url'])
                    path_parts = parsed.path.strip('/').split('/')

                    # Extract meaningful filename from URL
                    # Skip common prefixes like language codes (en-us, fr, etc.)
                    skip_prefixes = ['en-us', 'en', 'fr', 'de', 'es', 'it', 'zh', 'ja', 'ko']

                    meaningful_parts = []
                    for part in path_parts:
                        if part and part not in skip_prefixes and not part.isdigit():
                            meaningful_parts.append(part)

                    if meaningful_parts:
                        filename_base = '-'.join(meaningful_parts[:3])  # Use first 2-3 meaningful parts
                    elif path_parts and path_parts[0]:
                        filename_base = path_parts[0]  # Fallback to first part
                    else:
                        filename_base = 'root'  # Root directory

                    # Sanitize filename (remove special characters)
                    import re
                    filename_base = re.sub(r'[^\w\-]', '_', filename_base)
                    filename_base = filename_base.strip('_')

                    # Use flat directory structure: root_dir/html/ and root_dir/screenshots/
                    root_dir = Path(task_data['root_dir'])
                    screenshot_dir = root_dir / 'screenshots'
                    html_dir = root_dir / 'html'

                    # Create directories (if they don't exist)
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    html_dir.mkdir(parents=True, exist_ok=True)

                    # Take screenshot
                    screenshot_path = screenshot_dir / f"{filename_base}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    result['screenshot_taken'] = True
                    result['screenshot_path'] = str(screenshot_path)

                    # Save HTML
                    html_path = html_dir / f"{filename_base}.html"
                    html_content = await page.content()

                    async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
                        await f.write(html_content)

                    result['html_saved'] = True
                    result['html_path'] = str(html_path)

                    return result

                except Exception as e:
                    result['error'] = str(e)
                    return result
                finally:
                    try:
                        await browser.close()
                    except:
                        pass

        # Run the async scraping in this process
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(scrape_page())
        finally:
            loop.close()

    except Exception as e:
        return {
            'url': task_data['url'],
            'error': f"Process error: {str(e)}",
            'screenshot_taken': False,
            'html_saved': False
        }


class WebsiteScraper:
    """Handles scraping of individual websites using Playwright."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing WebsiteScraper")
        self.logger.debug("Creating PopupHandler instance")
        self.popup_handler = PopupHandler(self.logger)
        
        # Initialize rate limiter and delay manager
        initialize_rate_limiter(self.config.max_requests_per_domain_per_minute)
        initialize_delay_manager(self.config.delay_between_pages_min, self.config.delay_between_pages_max)
        self.logger.info(f"Rate limiter initialized: {self.config.max_requests_per_domain_per_minute} req/min")
        self.logger.info(f"Delay manager initialized: {self.config.delay_between_pages_min}-{self.config.delay_between_pages_max}s")
        
        # URL store will be initialized per website/run
        self.url_store = None
        self.root_dir = None
        
        self.logger.info("WebsiteScraper initialized successfully")

    async def discover_directories(self, website_data: Dict[str, Any]) -> int:
        """
        PHASE 1: Directory Discovery (Single Browser)
        =============================================
        - Uses ONE browser instance to explore the website
        - Finds ALL directory URLs recursively
        - Writes URLs to SQLite database as they're discovered
        - Fast exploration, no popup handling needed
        - Returns count of discovered URLs (URLs are in SQLite now)

        Args:
            website_data: Dictionary containing website information

        Returns:
            Count of discovered directory URLs
        """
        url = website_data['url']
        domain = website_data['domain']

        self.logger.info(f"🔍 PHASE 1: Starting directory discovery for {url}")

        # Create root directory and URL store for this website/run
        from datetime import datetime
        from src.url_store import URLStore
        simple_domain = domain.replace('www.', '').split('.')[0]
        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M")
        root_dir_name = f"{simple_domain}_{timestamp}"
        self.root_dir = Path(self.config.output_base_dir) / root_dir_name
        self.root_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize URL store
        db_path = str(self.root_dir / "urls.db")
        self.url_store = URLStore(db_path, domain)
        self.logger.info(f"📁 Created URL store: {db_path}")

        discovered_count = 0

        async with async_playwright() as p:
            self.logger.debug("Launching browser for directory discovery")
            browser = await p.chromium.launch(
                headless=self.config.browser_headless,
                args=self.config.browser_args
            )

            try:
                # Create context with randomized fingerprint (NO stealth plugin - stealth is disabled by default)
                context = await _create_stealth_context(browser, self.config)
                
                # Note: Discovery phase does NOT use stealth plugin - stealth is disabled in config

                # Discover directory structure using recursive discovery with URL store
                discovery = RecursiveDirectoryDiscovery(self.config, self.logger, url_store=self.url_store)
                directory_urls = await discovery.discover_all_directories(context, url)
                discovered_count = len(directory_urls)

                self.logger.info(f"🎯 Discovered {discovered_count} directories (stored in SQLite)")

                # Phase 1.5 is now done per-worker in Phase 2 (each worker discovers selectors for its URL)
                # This ensures Cloudflare is handled before discovery and each URL gets its own selectors

            except Exception as e:
                self.logger.error(f"Error during directory discovery: {e}")
                # Fallback: add root URL to store
                if self.url_store:
                    self.url_store.add_url(url)
                discovered_count = 1

            finally:
                await browser.close()

        self.logger.info(f"📂 Directory discovery completed: {discovered_count} directories found")
        return discovered_count

    async def _discover_site_popup_patterns(self, sample_urls: List[str], base_domain: str) -> List[str]:
        """
        PHASE 1.5: Discover site-specific popup and cookie banner selectors.
        Samples 4-5 URLs to identify actual selectors used by the website.

        Args:
            sample_urls: List of URLs to sample
            base_domain: Base domain for filtering

        Returns:
            List of discovered selector patterns
        """
        self.logger.info(f"🔍 PHASE 1.5: Discovering site-specific popup patterns from {len(sample_urls)} sample URLs")

        # Add timeout to prevent hanging
        try:
            return await asyncio.wait_for(
                self._do_discovery_with_timeout(sample_urls, base_domain),
                timeout=30.0  # 30 second timeout
            )
        except asyncio.TimeoutError:
            self.logger.warning("⚠️ Phase 1.5 timed out, using general patterns")
            return []

    async def _do_discovery_with_timeout(self, sample_urls: List[str], base_domain: str) -> List[str]:

        discovered_selectors = {}  # Change to dict to track selector + type combinations
        sample_size = min(5, len(sample_urls))  # Sample 4-5 URLs as user suggested

        # Use a fresh browser for analysis
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # Create stealth context with randomized fingerprint
            context = await _create_stealth_context(browser, self.config)

            try:
                for i, url in enumerate(sample_urls[:sample_size]):
                    try:
                        self.logger.info(f"🔎 Analyzing URL {i+1}/{sample_size}: {url}")
                        page = await context.new_page()
                        
                        # Apply stealth plugin to page
                        await _apply_stealth_to_page(page, self.config)

                        # Navigate and wait for potential popups with longer delay and interaction
                        self.logger.info(f"🌐 Navigating to {url}...")
                        try:
                            await page.goto(url, timeout=30000, wait_until='domcontentloaded')  # Changed to domcontentloaded and increased timeout
                            self.logger.info(f"✅ Page loaded successfully")
                        except Exception as e:
                            self.logger.warning(f"⚠️ Page navigation warning: {e}, continuing anyway...")
                            # Continue even if navigation has issues

                        # Wait longer and try to trigger popups with user-like interactions
                        await asyncio.sleep(3)  # Initial wait - longer for popups to appear

                        # Simulate user interactions that might trigger popups
                        try:
                            # Scroll down a bit (common trigger for cookie banners)
                            await page.evaluate("window.scrollTo(0, 100);")
                            await asyncio.sleep(1.5)

                            # Click somewhere on the page (another common trigger)
                            await page.mouse.click(100, 100)
                            await asyncio.sleep(1.5)

                            # Scroll back up
                            await page.evaluate("window.scrollTo(0, 0);")
                            await asyncio.sleep(1.5)
                        except Exception as e:
                            self.logger.debug(f"Interaction error (non-critical): {e}")

                        # Final wait for any delayed popups - CRITICAL for z-index detection
                        await asyncio.sleep(3)
                        
                        # Force a reflow to ensure all styles are computed
                        await page.evaluate("document.body.offsetHeight;")
                        await asyncio.sleep(0.5)

                        # Get full HTML content and analyze it in Python (much more reliable)
                        html_content = await page.content()

                        # Analyze HTML in Python for popup/cookie selectors
                        self.logger.info("🔍 Starting HTML analysis for popup/cookie selectors...")
                        selectors_found = self._analyze_html_for_selectors(html_content)
                        self.logger.info(f"📊 HTML analysis returned {len(selectors_found)} potential selectors")

                        # Also analyze DOM for high z-index and overlay elements (like Phase 2)
                        self.logger.info(f"🔍 Analyzing DOM for high z-index overlays on {url}")
                        dom_result = await page.evaluate("""
                            (function() {
                                const allElements = document.querySelectorAll('*');
                                const zIndexMap = new Map(); // Track highest z-index per selector

                                for (let el of allElements) {
                                    try {
                                        const style = window.getComputedStyle(el);
                                        const rect = el.getBoundingClientRect();
                                        
                                        // Get z-index - check computed style, inline style, and CSS classes
                                        let zIndex = parseInt(style.zIndex) || 0;
                                        
                                        // If z-index is 'auto', check if parent has z-index
                                        if (isNaN(zIndex) || zIndex === 0) {
                                            // Check inline style
                                            const inlineZ = parseInt(el.style.zIndex) || 0;
                                            if (inlineZ > 0) zIndex = inlineZ;
                                        }
                                        
                                        // Also check if element is positioned (positioned elements can have effective z-index)
                                        const position = style.position;
                                        const isPositioned = position === 'fixed' || position === 'absolute' || position === 'relative';
                                        
                                        // Check for high z-index overlays - LOWER threshold to catch more
                                        // Also check positioned elements even with low z-index (they might be overlays)
                                        if (zIndex > 5 || (isPositioned && zIndex > 0)) {  // Lowered from 10 to 5
                                            let selector = null;
                                            let selectorType = 'high_z_overlay';
                                            
                                            // Prefer ID over class
                                            if (el.id && el.id.trim()) {
                                                selector = `#${el.id}`;
                                            } else if (el.className && typeof el.className === 'string' && el.className.trim()) {
                                                const classes = el.className.trim().split(/\\s+/).filter(c => c.length > 0);
                                                if (classes.length > 0) {
                                                    // Use the first meaningful class
                                                    selector = `.${classes[0]}`;
                                                }
                                            }
                                            
                                            if (selector) {
                                                // Track highest z-index for this selector
                                                const existing = zIndexMap.get(selector);
                                                if (!existing || zIndex > existing.z_index) {
                                                    zIndexMap.set(selector, {
                                                        selector: selector,
                                                        type: selectorType,
                                                        z_index: zIndex,
                                                        position: position
                                                    });
                                                }
                                            }
                                        }

                                        // Check for large viewport coverage (potential overlays)
                                        const viewportWidth = window.innerWidth;
                                        const viewportHeight = window.innerHeight;
                                        const coverageX = (rect.width / viewportWidth) * 100;
                                        const coverageY = (rect.height / viewportHeight) * 100;

                                        if ((coverageX > 30 || coverageY > 30) && rect.width > 200 && rect.height > 150) {
                                            // Look for positioned elements that might be overlays
                                            if (position === 'fixed' || position === 'absolute') {
                                                let selector = null;
                                                
                                                if (el.id && el.id.trim()) {
                                                    selector = `#${el.id}`;
                                                } else if (el.className && typeof el.className === 'string' && el.className.trim()) {
                                                    const classes = el.className.trim().split(/\\s+/).filter(c => c.length > 0);
                                                    if (classes.length > 0) {
                                                        selector = `.${classes[0]}`;
                                                    }
                                                }
                                                
                                                if (selector) {
                                                    const existing = zIndexMap.get(selector);
                                                    if (!existing || coverageX * coverageY > (existing.coverage || 0)) {
                                                        zIndexMap.set(selector, {
                                                            selector: selector,
                                                            type: 'large_overlay',
                                                            coverage: coverageX * coverageY,
                                                            coverageX: coverageX,
                                                            coverageY: coverageY
                                                        });
                                                    }
                                                }
                                            }
                                        }
                                    } catch (e) {
                                        // Skip elements that cause errors
                                        continue;
                                    }
                                }

                                // Convert map to array and sort by z-index (NO CONFIDENCE FILTERING)
                                const selectors = Array.from(zIndexMap.values());
                                const sortedSelectors = selectors
                                    .sort((a, b) => {
                                        // Sort by z-index only - highest first
                                        return (b.z_index || 0) - (a.z_index || 0);
                                    })
                                    // NO LIMIT - try all discovered selectors
                                    // .slice(0, 20);

                                const topZIndexes = sortedSelectors
                                    .filter(s => s.z_index)
                                    .map(s => s.z_index)
                                    .sort((a, b) => b - a)
                                    .slice(0, 10);

                                let zIndexRange = 'none';
                                if (topZIndexes.length > 0) {
                                    const minZ = Math.min.apply(null, topZIndexes);
                                    const maxZ = Math.max.apply(null, topZIndexes);
                                    zIndexRange = `min: ${minZ}, max: ${maxZ}`;
                                }

                                return {
                                    selectors: sortedSelectors,
                                    debug: {
                                        totalElements: allElements.length,
                                        selectorsFound: sortedSelectors.length,
                                        topZIndexes: topZIndexes,
                                        zIndexRange: zIndexRange
                                    }
                                };
                            })();
                        """)

                        # Extract selectors and debug info from DOM analysis
                        dom_selectors = dom_result.get('selectors', [])
                        debug_info = dom_result.get('debug', {})

                        self.logger.info(f"🔍 DOM Analysis Results: {debug_info.get('totalElements', 0)} elements scanned, "
                                        f"{debug_info.get('selectorsFound', 0)} potential overlays found")
                        if debug_info.get('topZIndexes'):
                            self.logger.info(f"📊 Top z-indexes found: {debug_info.get('topZIndexes', [])[:10]}")
                            self.logger.info(f"📊 Z-index range: {debug_info.get('zIndexRange', 'N/A')}")
                        else:
                            self.logger.warning("⚠️ No z-index values found in DOM analysis - popups may not be visible yet")
                        
                        if dom_selectors:
                            self.logger.info(f"📊 DOM Analysis found {len(dom_selectors)} overlay selectors")

                        # Merge HTML and DOM selectors
                        selectors_found.extend(dom_selectors)
                        self.logger.info(f"📊 Total selectors after merge: {len(selectors_found)} (HTML: {len(selectors_found) - len(dom_selectors)}, DOM: {len(dom_selectors)})")

                        # Process the discovered selectors (both HTML and DOM analysis)
                        # NO CONFIDENCE FILTERING - try all selectors
                        self.logger.info(f"🔄 Processing {len(selectors_found)} discovered selectors for storage...")
                        for item in selectors_found:
                            try:
                                selector = item.get('selector') if isinstance(item, dict) else str(item)
                                selector_type = item.get('type', 'unknown') if isinstance(item, dict) else 'unknown'

                                if not selector:
                                    self.logger.warning(f"⚠️ Skipping invalid selector item: {item}")
                                    continue

                                # Create a unique key that includes type for better deduplication
                                selector_key = f"{selector}|{selector_type}"
                                if selector_key not in discovered_selectors:
                                    discovered_selectors[selector_key] = selector
                                    self.logger.info(f"🎯 Discovered {selector_type} selector: {selector}")
                                else:
                                    self.logger.debug(f"⏭️ Skipping duplicate selector: {selector}")
                            except Exception as e:
                                self.logger.warning(f"⚠️ Error processing selector item {item}: {e}")
                                continue

                        self.logger.info(f"📦 Stored {len(discovered_selectors)} unique selectors so far")
                        await page.close()

                    except Exception as e:
                        self.logger.error(f"❌ Error analyzing URL {url}: {e}", exc_info=True)
                        import traceback
                        self.logger.error(f"Traceback: {traceback.format_exc()}")
                        continue

            finally:
                await browser.close()

        selector_list = list(discovered_selectors.values())
        self.logger.info(f"✅ PHASE 1.5 Complete: Discovered {len(selector_list)} site-specific selectors")

        # Store the discovered selectors for Phase 2 (we'll need to pass them)
        self._site_specific_selectors = selector_list

        return selector_list

    def _analyze_html_for_selectors(self, html_content: str) -> List[Dict[str, Any]]:
        """Analyze HTML content for popup and cookie selectors using regex (fast and reliable)."""
        import re

        selectors = []

        try:
            # Convert to lowercase for case-insensitive matching
            html_lower = html_content.lower()

            # 1. COOKIE BANNER FRAMEWORKS (highest priority)
            frameworks = [
                ('fc-consent-root', '.fc-consent-root', 98),
                ('usercentrics-root', '#usercentrics-root', 98),
                ('cookiebot', '.cookiebot', 95),
                ('onetrust', '.onetrust-banner-container', 95),
                ('cookie-alert', '.cookie-alert', 90)
            ]

            for pattern, selector, confidence in frameworks:
                if pattern in html_lower:
                    selectors.append({
                        'selector': selector,
                        'type': 'cookie_framework',
                        'confidence': confidence
                    })

            # 2. MODAL/DIALOG ELEMENTS
            modal_patterns = [
                ('role="dialog"', '[role="dialog"]', 90),
                ('role="modal"', '[role="modal"]', 90),
                ('aria-modal="true"', '[aria-modal="true"]', 95),
                ('data-modal=', '[data-modal]', 85),
                ('data-popup=', '[data-popup]', 85)
            ]

            for pattern, selector, confidence in modal_patterns:
                if pattern in html_lower:
                    selectors.append({
                        'selector': selector,
                        'type': 'modal',
                        'confidence': confidence
                    })

            # 3. COOKIE/CONSENT ELEMENTS BY CLASS/ID (Victoria's Secret specific)
            cookie_elements = [
                ('class="[^"]*cookie[^"]*"', 'cookie', 90),
                ('id="[^"]*cookie[^"]*"', 'cookie', 95),
                ('class="[^"]*consent[^"]*"', 'consent', 90),
                ('id="[^"]*consent[^"]*"', 'consent', 95),
                ('class="[^"]*gdpr[^"]*"', 'gdpr', 90),
                ('id="[^"]*gdpr[^"]*"', 'gdpr', 95),
                ('class="[^"]*privacy[^"]*"', 'privacy', 85),
                ('id="[^"]*privacy[^"]*"', 'privacy', 90)
            ]

            for pattern, element_type, confidence in cookie_elements:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches[:3]:  # Limit to 3 per pattern
                    # Extract the actual class or id value
                    if 'class=' in match:
                        class_match = re.search(r'class="([^"]*cookie[^"]*)"', match, re.IGNORECASE)
                        if class_match:
                            class_name = class_match.group(1).split()[0]  # First class
                            selectors.append({
                                'selector': f'.{class_name}',
                                'type': 'cookie_banner',
                                'confidence': confidence
                            })
                    elif 'id=' in match:
                        id_match = re.search(r'id="([^"]*cookie[^"]*)"', match, re.IGNORECASE)
                        if id_match:
                            element_id = id_match.group(1)
                            selectors.append({
                                'selector': f'#{element_id}',
                                'type': 'cookie_banner',
                                'confidence': confidence
                            })

            # 4. ACCEPT/AGREE BUTTONS (most critical - look for button text)
            button_patterns = [
                r'<button[^>]*>([^<]*(?:accept|agree|allow|ok|yes|consent)[^<]*)</button>',
                r'<a[^>]*>([^<]*(?:accept|agree|allow|ok|yes|consent)[^<]*)</a>',
                r'<input[^>]*value="([^"]*(?:accept|agree|allow|ok|yes|consent)[^"]*)"[^>]*>',
            ]

            for pattern in button_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches[:5]:  # Limit to 5 buttons
                    text = match.strip().lower()

                    # Look for button context around this text
                    start = html_content.lower().find(text)
                    if start > 0:
                        # Look backwards for id= or class=
                        context_start = max(0, start - 200)
                        context = html_content[context_start:start + len(text) + 200]

                        # Try to find ID first
                        id_match = re.search(r'id="([^"]*)"', context, re.IGNORECASE)
                        if id_match:
                            selectors.append({
                                'selector': f'#{id_match.group(1)}',
                                'type': 'accept_button',
                                'confidence': 95,
                                'button_text': text
                            })
                            continue

                        # Try to find class
                        class_match = re.search(r'class="([^"]*consent[^"]*)"', context, re.IGNORECASE)
                        if class_match:
                            class_name = class_match.group(1).split()[0]
                            selectors.append({
                                'selector': f'button.{class_name}',
                                'type': 'accept_button',
                                'confidence': 90,
                                'button_text': text
                            })
                            continue

                        # Fallback: generic button selector
                        selectors.append({
                            'selector': f'button:contains("{text[:20]}")',  # CSS :contains pseudo-selector
                            'type': 'accept_button',
                            'confidence': 70,
                            'button_text': text
                        })

            # 5. COOKIE BANNER SCRIPTS
            script_patterns = [
                ('cookiebot', '.cookiebot', 90),
                ('onetrust', '.onetrust', 90),
                ('usercentrics', '#usercentrics-root', 95),
                ('fc-consent', '.fc-consent-root', 95)
            ]

            for script_name, selector, confidence in script_patterns:
                if script_name in html_lower:
                    selectors.append({
                        'selector': selector,
                        'type': 'cookie_script',
                        'confidence': confidence
                    })

            # Remove duplicates and sort by confidence
            seen = set()
            unique_selectors = []

            for item in selectors:
                selector_key = item['selector']
                if selector_key not in seen:
                    seen.add(selector_key)
                    unique_selectors.append(item)

            # NO CONFIDENCE SORTING - try all selectors
            # unique_selectors.sort(key=lambda x: x.get('confidence', 0), reverse=True)

            # Log discovered selectors
            if unique_selectors:
                self.logger.info(f"🎯 HTML Analysis: Discovered {len(unique_selectors)} selectors: " +
                               ", ".join([f"{s['selector']}({s.get('type', 'unknown')})" for s in unique_selectors[:10]]))
            else:
                self.logger.info("🔍 HTML Analysis: No selectors found in HTML content")

            return unique_selectors[:15]  # Return top 15

        except Exception as e:
            self.logger.debug(f"Error analyzing HTML with regex: {e}")
            return []

    async def scrape_directories_parallel(self, website_data: Dict[str, Any], discovery_running: bool = True) -> Dict[str, Any]:
        """
        PHASE 2: Parallel Scraping (Reads from SQLite)
        ===============================================
        - Reads URLs from SQLite database (written by Phase 1)
        - Launches multiple INDEPENDENT browser processes
        - Each process scrapes one directory URL atomically
        - Each browser handles its own popups independently
        - Saves screenshots and HTML to timestamped directory
        - Continues until no more pending URLs (even if discovery is still running)

        Args:
            website_data: Website information dictionary
            discovery_running: Whether discovery is still running (for logging)

        Returns:
            Dictionary with scraping results and statistics
        """
        domain = website_data['domain']

        if not self.url_store or not self.root_dir:
            self.logger.error("URL store or root directory not initialized")
            return {
                'domain': domain,
                'url': website_data['url'],
                'pages_scraped': 0,
                'screenshots_taken': 0,
                'html_saved': 0,
                'errors': [],
                'pages': []
            }

        root_dir = self.root_dir
        root_dir_name = root_dir.name

        self.logger.info(f"🚀 PHASE 2: Starting parallel scraping from SQLite database using {self.config.use_cpus} CPUs")
        self.logger.info(f"📁 Root directory: {root_dir_name}")

        results = {
            'domain': domain,
            'url': website_data['url'],
            'pages_scraped': 0,
            'screenshots_taken': 0,
            'html_saved': 0,
            'errors': [],
            'pages': []
        }

        # Use ProcessPoolExecutor for true parallel processing
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed

        max_workers = self.config.use_cpus
        self.logger.info(f"⚡ Launching {max_workers} worker processes")

        completed = 0
        task_id_counter = 0
        no_url_count = 0  # Track consecutive "no URL" checks
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            # Keep processing URLs until no more pending URLs
            # Continue even if discovery is still running (it may add more URLs)
            while True:
                # Submit tasks up to max_workers
                while len(futures) < max_workers:
                    # Get next pending URL atomically
                    url = self.url_store.get_next_pending_url()
                    
                    if url:
                        no_url_count = 0  # Reset counter
                        task_data = {
                            'url': url,
                            'domain': domain,
                            'root_dir': str(root_dir),
                            'task_id': task_id_counter,
                            'headless': self.config.browser_headless,
                            'page_load_timeout': self.config.page_load_timeout,
                            'wait_after_load': self.config.wait_after_load,
                            'enable_mouse_movements': self.config.enable_mouse_movements,
                            'enable_scrolling_simulation': self.config.enable_scrolling_simulation,
                            'max_requests_per_domain_per_minute': self.config.max_requests_per_domain_per_minute,
                            'delay_between_pages_min': self.config.delay_between_pages_min,
                            'delay_between_pages_max': self.config.delay_between_pages_max,
                            'config': self.config  # Pass config for stealth check
                        }
                        future = executor.submit(scrape_single_directory_worker, task_data)
                        futures[future] = {'url': url, 'task_id': task_id_counter}
                        task_id_counter += 1
                    else:
                        # No pending URLs
                        no_url_count += 1
                        if no_url_count >= 10 and not discovery_running:
                            # No URLs for 10 checks and discovery is done - exit
                            break
                        elif no_url_count >= 10:
                            # No URLs but discovery might still be running - wait a bit
                            await asyncio.sleep(2)
                            no_url_count = 0
                        else:
                            # Wait a bit before checking again
                            await asyncio.sleep(0.5)
                        break  # Exit inner loop to check completed tasks
                
                # Process completed tasks
                done_futures = []
                for future in futures:
                    if future.done():
                        done_futures.append(future)
                
                for future in done_futures:
                    task_info = futures.pop(future)
                    url = task_info['url']
                    try:
                        page_result = future.result(timeout=600)  # 10 minute timeout per page
                        results['pages'].append(page_result)

                        if page_result.get('screenshot_taken', False):
                            results['screenshots_taken'] += 1
                        if page_result.get('html_saved', False):
                            results['html_saved'] += 1
                        if page_result.get('error'):
                            results['errors'].append(page_result['error'])
                            # Mark as failed (reset to pending for retry)
                            self.url_store.mark_failed(url)
                        else:
                            # Mark as completed
                            self.url_store.mark_completed(url)

                        completed += 1
                        if completed % 5 == 0:
                            pending_count = self.url_store.get_pending_count()
                            self.logger.info(f"📊 Progress: {completed} completed, {pending_count} pending ({results['screenshots_taken']} screenshots, {results['html_saved']} HTML files)")

                    except Exception as e:
                        error_msg = f"Multiprocessing error for {url}: {str(e)}"
                        self.logger.error(error_msg)
                        results['errors'].append(error_msg)
                        self.url_store.mark_failed(url)  # Reset to pending for retry
                        results['pages'].append({
                            'url': url,
                            'error': str(e),
                        'screenshot_taken': False,
                        'html_saved': False
                    })
                    completed += 1
                
                # If no futures left and no more URLs, check one more time
                if not futures and no_url_count >= 10:
                    if not discovery_running or self.url_store.get_pending_count() == 0:
                        break
                    no_url_count = 0  # Reset and continue

        results['pages_scraped'] = completed
        self.logger.info(f"✅ Parallel scraping completed: {results['pages_scraped']} directories processed across {max_workers} independent processes")
        self.logger.info(f"📈 Final stats: {results['screenshots_taken']} screenshots, {results['html_saved']} HTML files, {len(results['errors'])} errors")
        return results

    async def _scrape_single_page_async(self, url: str, domain: str, output_base_dir: str) -> Dict[str, Any]:
        """
        Async version of single page scraping for use in parallel processes.
        """
        result = {
            'url': url,
            'screenshot_taken': False,
            'html_saved': False,
            'error': None
        }

        async with async_playwright() as p:
            browser = None
            context = None
            page = None
            try:
                browser = await p.chromium.launch(
                    headless=self.config.browser_headless,
                    args=self.config.browser_args
                )

                # Create stealth context with randomized fingerprint
                context = await _create_stealth_context(browser, self.config)
                page = await context.new_page()
                
                # Apply stealth plugin to page
                await _apply_stealth_to_page(page, self.config)

                # Rate limiting: wait if needed before navigation
                await wait_for_rate_limit(url)

                await page.goto(url, timeout=self.config.page_load_timeout * 1000, wait_until='networkidle')
                
                # Record request for rate limiting
                record_request(url)

                # Wait for page stabilization
                await asyncio.sleep(self.config.wait_after_load)
                
                # Human behavior simulation
                if self.config.enable_mouse_movements or self.config.enable_scrolling_simulation:
                    await simulate_human_interaction(
                        page,
                        enable_mouse=self.config.enable_mouse_movements,
                        enable_scroll=self.config.enable_scrolling_simulation
                    )

                # Handle popups
                await self.popup_handler.handle_popups(page, strategy="conservative")

                # Additional stabilization
                await asyncio.sleep(0.5)

                # Generate filenames and paths
                from urllib.parse import urlparse
                import hashlib

                url_hash = hashlib.md5(url.encode()).hexdigest()[:6]
                parsed = urlparse(url)
                safe_domain = parsed.netloc.replace('.', '_')

                base_dir = Path(output_base_dir) / domain
                screenshot_dir = base_dir / self.config.screenshot_dir
                html_dir = base_dir / self.config.html_dir

                filename_base = f"{safe_domain}_{url_hash}"

                # Take screenshot
                screenshot_path = screenshot_dir / f"{filename_base}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                result['screenshot_taken'] = True
                result['screenshot_path'] = str(screenshot_path)

                # Save HTML
                html_path = html_dir / f"{filename_base}.html"
                html_content = await page.content()

                import aiofiles
                async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
                    await f.write(html_content)

                result['html_saved'] = True
                result['html_path'] = str(html_path)

            except Exception as e:
                result['error'] = str(e)
            finally:
                # Proper cleanup order: page -> context -> browser
                try:
                    if page:
                        await page.close()
                except Exception:
                    pass

                try:
                    if context:
                        await context.close()
                except Exception:
                    pass

                try:
                    if browser:
                        await browser.close()
                except Exception:
                    pass

        return result

    async def scrape_website(self, website_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Two-phase website scraping: directory discovery + parallel scraping.

        Args:
            website_data: Dictionary containing website information

        Returns:
            Dictionary with scraping results and statistics
        """
        # Phase 1: Discover directories (writes to SQLite as it discovers)
        discovery_task = asyncio.create_task(self.discover_directories(website_data))
        
        # Wait for at least 20 URLs to be discovered before starting scraping
        self.logger.info("⏳ Waiting for 20+ URLs to be discovered before starting scraping...")
        while True:
            if self.url_store:
                pending_count = self.url_store.get_pending_count()
                if pending_count >= 20:
                    self.logger.info(f"✅ {pending_count} URLs discovered - starting scraping phase")
                    break
            await asyncio.sleep(1)  # Check every second
        
        # Phase 2: Scrape directories in parallel (reads from SQLite)
        # Pass discovery_running=True so scraping continues even if discovery is still running
        scraping_task = asyncio.create_task(self.scrape_directories_parallel(website_data, discovery_running=True))
        
        # Wait for both tasks to complete
        discovered_count, results = await asyncio.gather(discovery_task, scraping_task)
        
        self.logger.info(f"✅ All tasks completed: {discovered_count} URLs discovered, {results['pages_scraped']} pages scraped")
        return results

    async def _scrape_single_page(self, context: BrowserContext, url: str,
                                base_dir: Path, screenshot_dir: Path, html_dir: Path) -> Dict[str, Any]:
        """
        Scrape a single page: take screenshot and save HTML.

        Args:
            context: Browser context
            url: URL to scrape
            base_dir: Base directory for this website
            screenshot_dir: Directory for screenshots
            html_dir: Directory for HTML files

        Returns:
            Dictionary with scraping results for this page
        """
        result = {
            'url': url,
            'screenshot_taken': False,
            'html_saved': False,
            'error': None
        }

        page = await context.new_page()

        try:
            # Navigate to page with timeout
            await page.goto(url, timeout=self.config.page_load_timeout * 1000, wait_until='networkidle')

            # Wait for page to stabilize and popups to appear
            await asyncio.sleep(self.config.wait_after_load)

            # Handle popups and overlays
            await self.popup_handler.handle_popups(page, strategy="conservative")

            # Verify page is still functional after popup handling
            try:
                body_exists = await page.evaluate("() => document.body !== null")
                if not body_exists:
                    self.logger.warning("Page body removed during popup handling, reloading...")
                    await page.reload(timeout=self.config.page_load_timeout * 1000)
                    await asyncio.sleep(1.0)
                    # Try popup handling again but more gently
                    await self._handle_popups_gently(page)
            except Exception as e:
                self.logger.warning(f"Error verifying page after popup handling: {e}")

            # Additional wait after popup handling
            await asyncio.sleep(0.3)

            # Generate filename-safe identifiers
            url_hash = hash(url) % 1000000
            domain = urlparse(url).netloc.replace('.', '_')
            filename_base = f"{domain}_{url_hash}"

            # Take screenshot
            screenshot_path = screenshot_dir / f"{filename_base}.png"
            await page.screenshot(
                path=str(screenshot_path),
                full_page=self.config.screenshot_full_page
            )
            result['screenshot_taken'] = True
            result['screenshot_path'] = str(screenshot_path)

            # Save HTML
            html_path = html_dir / f"{filename_base}.html"
            html_content = await page.content()

            async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
                await f.write(html_content)

            result['html_saved'] = True
            result['html_path'] = str(html_path)

            self.logger.debug(f"Successfully scraped {url}")

        except Exception as e:
            result['error'] = str(e)
            self.logger.error(f"Error scraping {url}: {e}")

        finally:
            await page.close()

        return result
