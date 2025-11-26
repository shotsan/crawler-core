#!/usr/bin/env python3
"""
Test script to check if stealth plugin is causing blocking issues.
Tests with a single URL and stops after discovering 1 URL.
"""

import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Page
from src.scraper import _create_stealth_context, _apply_stealth_to_page, _handle_cloudflare_challenge
from src.popup_handler import PopupHandler
from src.config import config
from src.config_loader import ConfigLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_with_stealth(url: str):
    """Test crawling with stealth plugin enabled."""
    logger.info("=" * 60)
    logger.info("TEST 1: WITH STEALTH PLUGIN")
    logger.info("=" * 60)
    
    result = {
        'success': False,
        'blocked': False,
        'cloudflare_passed': False,
        'title': None,
        'status_code': None,
        'page_text_snippet': None,
        'screenshot_path': None,
        'urls_found': 0
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        try:
            context = await _create_stealth_context(browser, config)
            page = await context.new_page()
            
            # Apply stealth plugin
            logger.info("✅ Applying stealth plugin...")
            await _apply_stealth_to_page(page)
            
            logger.info(f"🌐 Navigating to: {url}")
            response = await page.goto(url, timeout=30000, wait_until='domcontentloaded')
            
            # Get HTTP status
            if response:
                result['status_code'] = response.status
                logger.info(f"📊 HTTP Status Code: {response.status}")
                if response.status >= 400:
                    logger.error(f"❌ HTTP Error: {response.status}")
                    result['blocked'] = True
            else:
                logger.warning("⚠️ No response object received")
            
            # Check for Cloudflare
            logger.info("🔍 Checking for Cloudflare challenge...")
            cloudflare_result = await _handle_cloudflare_challenge(page, logger)
            result['cloudflare_passed'] = cloudflare_result
            if not cloudflare_result:
                logger.error("❌ Cloudflare challenge failed!")
                result['blocked'] = True
            
            # Wait a bit
            await asyncio.sleep(2)
            
            # Get page title
            title = await page.title()
            result['title'] = title
            logger.info(f"📄 Page title: {title}")
            
            # Get page content for analysis
            page_content = await page.content()
            page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            
            # Check for blocking indicators
            blocking_keywords = [
                'blocked', 'access denied', 'forbidden', '403', 'cloudflare',
                'checking your browser', 'just a moment', 'ddos protection',
                'captcha', 'verify you are human', 'bot detected', 'automated access'
            ]
            
            blocking_found = []
            page_lower = page_text.lower()
            for keyword in blocking_keywords:
                if keyword in page_lower:
                    blocking_found.append(keyword)
            
            if blocking_found:
                logger.error(f"❌ BLOCKING INDICATORS FOUND: {', '.join(blocking_found)}")
                result['blocked'] = True
            
            # Show page text snippet
            text_snippet = page_text[:500] if len(page_text) > 500 else page_text
            result['page_text_snippet'] = text_snippet
            logger.info("📝 Page text snippet (first 500 chars):")
            logger.info("-" * 60)
            logger.info(text_snippet)
            logger.info("-" * 60)
            
            # Save screenshot
            screenshot_path = f"test_stealth_with_screenshot.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            result['screenshot_path'] = screenshot_path
            logger.info(f"📸 Screenshot saved: {screenshot_path}")
            
            # Discover URLs
            logger.info("🔍 Discovering links...")
            links = await page.query_selector_all('a[href]')
            discovered_urls = []
            for link in links[:10]:
                href = await link.get_attribute('href')
                if href and href.startswith('http'):
                    discovered_urls.append(href)
                    if len(discovered_urls) >= 1:
                        break
            
            result['urls_found'] = len(discovered_urls)
            if discovered_urls:
                logger.info(f"🔗 Discovered {len(discovered_urls)} URL(s):")
                for u in discovered_urls:
                    logger.info(f"   - {u}")
            else:
                logger.warning("⚠️ No URLs discovered")
            
            # Final verdict
            if not result['blocked'] and result['cloudflare_passed'] and result['urls_found'] > 0:
                result['success'] = True
                logger.info("✅ TEST RESULT: SUCCESS (not blocked)")
            else:
                logger.error("❌ TEST RESULT: FAILED (blocked or issues detected)")
                
        except Exception as e:
            logger.error(f"❌ Error with stealth: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result['blocked'] = True
        finally:
            await browser.close()
    
    return result


async def test_without_stealth(url: str):
    """Test crawling WITHOUT stealth plugin."""
    logger.info("=" * 60)
    logger.info("TEST 2: WITHOUT STEALTH PLUGIN")
    logger.info("=" * 60)
    
    result = {
        'success': False,
        'blocked': False,
        'cloudflare_passed': False,
        'title': None,
        'status_code': None,
        'page_text_snippet': None,
        'screenshot_path': None,
        'urls_found': 0
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        try:
            context = await _create_stealth_context(browser, config)
            page = await context.new_page()
            
            # DO NOT apply stealth plugin
            logger.info("⏭️  Skipping stealth plugin...")
            
            logger.info(f"🌐 Navigating to: {url}")
            response = await page.goto(url, timeout=30000, wait_until='domcontentloaded')
            
            # Get HTTP status
            if response:
                result['status_code'] = response.status
                logger.info(f"📊 HTTP Status Code: {response.status}")
                if response.status >= 400:
                    logger.error(f"❌ HTTP Error: {response.status}")
                    result['blocked'] = True
            else:
                logger.warning("⚠️ No response object received")
            
            # Check for Cloudflare
            logger.info("🔍 Checking for Cloudflare challenge...")
            cloudflare_result = await _handle_cloudflare_challenge(page, logger)
            result['cloudflare_passed'] = cloudflare_result
            if not cloudflare_result:
                logger.error("❌ Cloudflare challenge failed!")
                result['blocked'] = True
            
            # Wait a bit
            await asyncio.sleep(2)
            
            # Get page title
            title = await page.title()
            result['title'] = title
            logger.info(f"📄 Page title: {title}")
            
            # Get page content for analysis
            page_content = await page.content()
            page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            
            # Check for blocking indicators
            blocking_keywords = [
                'blocked', 'access denied', 'forbidden', '403', 'cloudflare',
                'checking your browser', 'just a moment', 'ddos protection',
                'captcha', 'verify you are human', 'bot detected', 'automated access'
            ]
            
            blocking_found = []
            page_lower = page_text.lower()
            for keyword in blocking_keywords:
                if keyword in page_lower:
                    blocking_found.append(keyword)
            
            if blocking_found:
                logger.error(f"❌ BLOCKING INDICATORS FOUND: {', '.join(blocking_found)}")
                result['blocked'] = True
            
            # Show page text snippet
            text_snippet = page_text[:500] if len(page_text) > 500 else page_text
            result['page_text_snippet'] = text_snippet
            logger.info("📝 Page text snippet (first 500 chars):")
            logger.info("-" * 60)
            logger.info(text_snippet)
            logger.info("-" * 60)
            
            # Save screenshot
            screenshot_path = f"test_stealth_without_screenshot.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            result['screenshot_path'] = screenshot_path
            logger.info(f"📸 Screenshot saved: {screenshot_path}")
            
            # Discover URLs
            logger.info("🔍 Discovering links...")
            links = await page.query_selector_all('a[href]')
            discovered_urls = []
            for link in links[:10]:
                href = await link.get_attribute('href')
                if href and href.startswith('http'):
                    discovered_urls.append(href)
                    if len(discovered_urls) >= 1:
                        break
            
            result['urls_found'] = len(discovered_urls)
            if discovered_urls:
                logger.info(f"🔗 Discovered {len(discovered_urls)} URL(s):")
                for u in discovered_urls:
                    logger.info(f"   - {u}")
            else:
                logger.warning("⚠️ No URLs discovered")
            
            # Final verdict
            if not result['blocked'] and result['cloudflare_passed'] and result['urls_found'] > 0:
                result['success'] = True
                logger.info("✅ TEST RESULT: SUCCESS (not blocked)")
            else:
                logger.error("❌ TEST RESULT: FAILED (blocked or issues detected)")
                
        except Exception as e:
            logger.error(f"❌ Error without stealth: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result['blocked'] = True
        finally:
            await browser.close()
    
    return result


async def main():
    """Run both tests."""
    # Load config
    try:
        yaml_config = ConfigLoader.load_config()
        if yaml_config:
            config.update_from_yaml(yaml_config)
    except Exception as e:
        logger.warning(f"Could not load YAML config: {e}")
    
    # Test URL
    test_url = "https://zerodha.com/varsity/modules/"
    
    logger.info(f"Testing URL: {test_url}")
    logger.info("")
    
    # Test with stealth
    result_with_stealth = await test_with_stealth(test_url)
    
    logger.info("")
    logger.info("Waiting 5 seconds before next test...")
    await asyncio.sleep(5)
    logger.info("")
    
    # Test without stealth
    result_without_stealth = await test_without_stealth(test_url)
    
    # Detailed Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("DETAILED COMPARISON")
    logger.info("=" * 60)
    
    logger.info("\n📊 WITH STEALTH PLUGIN:")
    logger.info(f"   Success: {result_with_stealth['success']}")
    logger.info(f"   Blocked: {result_with_stealth['blocked']}")
    logger.info(f"   HTTP Status: {result_with_stealth['status_code']}")
    logger.info(f"   Cloudflare Passed: {result_with_stealth['cloudflare_passed']}")
    logger.info(f"   URLs Found: {result_with_stealth['urls_found']}")
    logger.info(f"   Title: {result_with_stealth['title']}")
    logger.info(f"   Screenshot: {result_with_stealth['screenshot_path']}")
    
    logger.info("\n📊 WITHOUT STEALTH PLUGIN:")
    logger.info(f"   Success: {result_without_stealth['success']}")
    logger.info(f"   Blocked: {result_without_stealth['blocked']}")
    logger.info(f"   HTTP Status: {result_without_stealth['status_code']}")
    logger.info(f"   Cloudflare Passed: {result_without_stealth['cloudflare_passed']}")
    logger.info(f"   URLs Found: {result_without_stealth['urls_found']}")
    logger.info(f"   Title: {result_without_stealth['title']}")
    logger.info(f"   Screenshot: {result_without_stealth['screenshot_path']}")
    
    logger.info("\n" + "=" * 60)
    logger.info("VERDICT")
    logger.info("=" * 60)
    
    if result_without_stealth['success'] and not result_with_stealth['success']:
        logger.error("❌ STEALTH PLUGIN IS CAUSING BLOCKING!")
        logger.error("   Recommendation: DISABLE stealth plugin")
    elif result_with_stealth['success'] and not result_without_stealth['success']:
        logger.info("✅ Stealth plugin appears to be helping")
    elif result_with_stealth['blocked'] and result_without_stealth['blocked']:
        logger.warning("⚠️  Both tests were blocked - may be rate limiting or other issue")
    elif result_with_stealth['success'] and result_without_stealth['success']:
        logger.info("ℹ️  Both tests succeeded - stealth may not be the issue")
    else:
        logger.warning("⚠️  Mixed results - check screenshots and details above")
    
    logger.info("\n📸 Check the screenshots to visually verify blocking:")
    logger.info(f"   - {result_with_stealth['screenshot_path']}")
    logger.info(f"   - {result_without_stealth['screenshot_path']}")


if __name__ == "__main__":
    asyncio.run(main())

