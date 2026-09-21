import asyncio
import random
import string
import time
import os
from typing import Optional, Dict, Callable
from playwright.async_api import async_playwright
from fake_useragent import UserAgent
from config import config

class GmailEngine:
    def __init__(self, proxy_manager):
        self.pm = proxy_manager
        self.ua = UserAgent()
        self.current_proxy = None
        # Use relative path - works anywhere the bot is run from
        self.debug_dir = os.path.join(os.getcwd(), "debug")
        os.makedirs(self.debug_dir, exist_ok=True)
        self.consecutive_errors = 0

    def generate_password(self, length=16):
        uppercase = string.ascii_uppercase
        lowercase = string.ascii_lowercase
        digits = string.digits
        symbols = "!@#$"

        password = [
            random.choice(uppercase), random.choice(uppercase),
            random.choice(lowercase), random.choice(lowercase),
            random.choice(digits), random.choice(digits),
            random.choice(symbols),
        ]

        all_chars = uppercase + lowercase + digits + symbols
        for _ in range(length - 7):
            password.append(random.choice(all_chars))

        random.shuffle(password)
        return ''.join(password)

    def generate_username(self, first, last, retry=0):
        timestamp = int(time.time()) % 100000

        patterns = [
            f"{first.lower()}{last.lower()}{random.randint(100,999)}",
            f"{first.lower()}{last.lower()}{random.randint(1000,9999)}",
            f"{first[0].lower()}{last.lower()}{random.randint(100,999)}",
            f"{first.lower()}{last[0].lower()}{random.randint(1000,9999)}",
            f"{first.lower()}{random.randint(10000,99999)}",
            f"{first.lower()}{last.lower()}{timestamp}",
        ]

        if retry > 2:
            patterns.append(f"{first.lower()}{last.lower()}{random.randint(100000,999999)}")

        return random.choice(patterns)

    def get_random_identity(self):
        first_names = ["James", "Robert", "John", "Michael", "David", "William", "Richard", "Joseph"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
        return {"first": random.choice(first_names), "last": random.choice(last_names)}

    async def _human_delay(self, min_sec=1, max_sec=4):
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def _take_screenshot(self, page, name):
        try:
            path = f"{self.debug_dir}/{name}_{int(time.time())}.png"
            await page.screenshot(path=path)
            return path
        except:
            return None

    async def _detect_page(self, page):
        url = page.url.lower()

        if '/error/' in url:
            return 'error'
        elif 'signup/name' in url or '/name?' in url:
            return 'names'
        elif 'birthdaygender' in url or 'basicinformation' in url:
            return 'birthday'
        elif 'collectemailphone' in url:
            return 'email_phone'
        elif 'username' in url or 'creategmail' in url:
            return 'username'
        elif 'password' in url or 'createpassword' in url:
            return 'password'
        elif 'phone' in url:
            return 'phone'
        elif 'recovery' in url:
            return 'recovery'
        elif 'term' in url or 'agreement' in url:
            return 'terms'
        elif 'myaccount' in url or 'welcome' in url:
            return 'success'

        return 'unknown'

    async def _check_for_blocking(self, page):
        """Check if Google is actually blocking us"""
        try:
            url = page.url.lower()
            content = await page.content()
            content_lower = content.lower()

            # ONLY check URL for error page
            if '/error/' in url:
                return True, "error_page"

            # Check for specific blocking messages (not just any 'bot' text)
            strong_indicators = [
                'unusual traffic',
                'too many attempts',
                'try again later',
                'automated queries',
                'computer or network',
            ]

            for indicator in strong_indicators:
                if indicator in content_lower:
                    return True, indicator

            # 'bot' is too common - check for specific bot detection
            if 'bot detection' in content_lower or 'are you a bot' in content_lower:
                return True, "bot_detection"

            return False, None
        except:
            return False, None

    async def _handle_names(self, page, first_name, last_name):
        try:
            await page.wait_for_selector('input[name="firstName"]', timeout=30000)
            await self._human_delay(1, 2)

            await page.click('input[name="firstName"]')
            await self._human_delay(0.3, 0.8)
            await page.fill('input[name="firstName"]', first_name)

            await self._human_delay(0.5, 1)
            await page.click('input[name="lastName"]')
            await self._human_delay(0.3, 0.8)
            await page.fill('input[name="lastName"]', last_name)

            await self._human_delay(1, 2)
            await page.click('button:has-text("Next")')
            await self._human_delay(3, 5)

            return True
        except Exception as e:
            print(f"Names error: {e}")
            return False

    async def _handle_birthday(self, page):
        try:
            await page.wait_for_selector('input#day', timeout=30000)
            await self._human_delay(1, 2)

            await page.evaluate("""() => {
                const opts = document.querySelectorAll('ul[aria-label="Month"] li[role="option"]');
                const idx = Math.floor(Math.random() * 12);
                if (opts.length > idx) {
                    opts[idx].dispatchEvent(new MouseEvent('click', { bubbles: true }));
                }
            }""")
            await self._human_delay(0.5, 1)

            await page.fill('input#day', str(random.randint(1, 28)))
            await self._human_delay(0.3, 0.8)
            await page.fill('input#year', str(random.randint(1985, 2002)))
            await self._human_delay(0.5, 1)

            await page.evaluate("""() => {
                const opts = document.querySelectorAll('ul[aria-label="Gender"] li[role="option"]');
                if (opts.length > 0) {
                    opts[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
                }
            }""")
            await self._human_delay(0.5, 1)

            await page.click('button:has-text("Next")')
            await self._human_delay(3, 5)

            return True
        except Exception as e:
            print(f"Birthday error: {e}")
            return False

    async def _handle_email_phone(self, page):
        try:
            await self._human_delay(1, 2)

            selectors = [
                'button:has-text("Don\'t have an email")',
                'button:has-text("Don\'t have")',
            ]

            for sel in selectors:
                try:
                    btn = await page.wait_for_selector(sel, timeout=5000)
                    if btn:
                        await btn.click()
                        await self._human_delay(3, 5)
                        return True
                except:
                    continue

            result = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button, a, [role="button"]');
                for (let el of btns) {
                    const text = el.textContent.toLowerCase();
                    if (text.includes('don\'t have') || text.includes('create') || text.includes('gmail')) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")

            if result:
                await self._human_delay(3, 5)
                return True

            return False
        except Exception as e:
            print(f"Email/phone error: {e}")
            return False

    async def _handle_username(self, page, custom_email, first_name, last_name, retry=0):
        try:
            await page.wait_for_selector('input[name="Username"]', timeout=20000)
            await self._human_delay(1, 2)

            await page.click('input[name="Username"]')
            await self._human_delay(0.3, 0.8)
            await page.fill('input[name="Username"]', '')
            await self._human_delay(0.2, 0.5)
            await page.fill('input[name="Username"]', custom_email)

            await page.evaluate("""() => {
                const input = document.querySelector('input[name="Username"]');
                if (input) {
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.blur();
                }
            }""")

            await self._human_delay(2, 3)

            error_found = await page.evaluate("""() => {
                const errors = document.querySelectorAll('[role="alert"], .o6cuMc, .Ekjuhf');
                for (let err of errors) {
                    if (err.textContent && err.textContent.trim().length > 3) {
                        return err.textContent.trim();
                    }
                }
                return null;
            }""")

            if error_found:
                print(f"Username error: {error_found[:80]}")
                if any(x in error_found.lower() for x in ["taken", "unavailable", "invalid", "already"]):
                    return "taken"

            await page.click('button:has-text("Next")')
            await self._human_delay(4, 6)

            current_url = page.url.lower()
            if 'username' not in current_url and 'error' not in current_url:
                return "success"

            post_error = await page.evaluate("""() => {
                const errors = document.querySelectorAll('[role="alert"], .o6cuMc');
                for (let err of errors) {
                    if (err.textContent && err.textContent.trim().length > 3) {
                        return err.textContent.trim();
                    }
                }
                return null;
            }""")

            if post_error:
                print(f"Post-submit error: {post_error[:80]}")
                if any(x in post_error.lower() for x in ["taken", "unavailable", "invalid"]):
                    return "taken"

            if 'username' in current_url:
                await page.evaluate("""() => {
                    const btns = document.querySelectorAll('button');
                    for (let btn of btns) {
                        if (btn.textContent.includes('Next')) {
                            btn.click();
                            break;
                        }
                    }
                }""")
                await self._human_delay(4, 6)

                current_url = page.url.lower()
                if 'username' not in current_url and 'error' not in current_url:
                    return "success"

            return "stuck"

        except Exception as e:
            print(f"Username error: {e}")
            return "error"

    async def _handle_password(self, page, password):
        """Handle password page - detect blocking vs validation errors"""
        try:
            await page.wait_for_selector('input[name="Passwd"]', timeout=20000)
            await self._human_delay(1, 2)

            # Check for blocking BEFORE filling
            is_blocked, reason = await self._check_for_blocking(page)
            if is_blocked:
                print(f"GOOGLE BLOCKING detected: {reason}")
                return "blocked"

            # Fill password
            await page.click('input[name="Passwd"]')
            await self._human_delay(0.3, 0.8)
            await page.fill('input[name="Passwd"]', password)
            await self._human_delay(0.5, 1)

            # Fill confirm
            confirm_filled = False
            for sel in ['input[name="PasswdAgain"]', 'input[aria-label*="confirm" i]', 'input[aria-label*="again" i]']:
                try:
                    await page.wait_for_selector(sel, timeout=3000)
                    await page.click(sel)
                    await self._human_delay(0.3, 0.8)
                    await page.fill(sel, password)
                    confirm_filled = True
                    break
                except:
                    continue

            if not confirm_filled:
                pwd_inputs = await page.query_selector_all('input[type="password"]')
                if len(pwd_inputs) >= 2:
                    await pwd_inputs[1].click()
                    await self._human_delay(0.3, 0.8)
                    await pwd_inputs[1].fill(password)

            await self._human_delay(1, 2)

            # Trigger validation
            await page.evaluate("""() => {
                const inputs = document.querySelectorAll('input[type="password"]');
                inputs.forEach(input => {
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.blur();
                });
            }""")

            await self._human_delay(2, 3)

            # Check for validation errors
            error_found = await page.evaluate("""() => {
                const errors = document.querySelectorAll('[role="alert"], .o6cuMc');
                for (let err of errors) {
                    if (err.textContent && err.textContent.trim().length > 3) {
                        return err.textContent.trim();
                    }
                }
                return null;
            }""")

            if error_found:
                print(f"Password validation error: {error_found[:100]}")
                return "validation_error"

            # Click Next
            await page.click('button:has-text("Next")')
            await self._human_delay(5, 8)

            current_url = page.url.lower()

            # Check if we got redirected to error page (Google blocking)
            if '/error/' in current_url:
                print(f"ERROR page after password - Google is blocking this IP")
                await self._take_screenshot(page, "google_blocking")
                return "blocked"

            if 'password' not in current_url:
                return "success"

            # Still on password - try JS click
            await page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (let btn of btns) {
                    if (btn.textContent.includes('Next')) {
                        btn.click();
                        break;
                    }
                }
            }""")
            await self._human_delay(5, 8)

            current_url = page.url.lower()
            if '/error/' in current_url:
                print(f"ERROR after JS click - Google blocking")
                return "blocked"

            if 'password' not in current_url:
                return "success"

            return "stuck"

        except Exception as e:
            print(f"Password exception: {e}")
            return "error"

    async def _handle_terms(self, page):
        try:
            await self._human_delay(1, 2)

            try:
                await page.click('button:has-text("I agree")', timeout=10000)
                await self._human_delay(3, 5)
                return True
            except:
                pass

            try:
                checkboxes = await page.query_selector_all('[role="checkbox"], input[type="checkbox"]')
                for cb in checkboxes[:3]:
                    await cb.click()
                    await self._human_delay(0.3, 0.8)
                await page.click('button:has-text("Next")')
                await self._human_delay(3, 5)
                return True
            except:
                pass

            return False
        except Exception as e:
            print(f"Terms error: {e}")
            return False

    async def _rotate_proxy(self):
        proxy = await self.pm.get_single_proxy()
        if proxy:
            self.current_proxy = proxy
            return proxy
        return None

    async def create_account(self, first_name, last_name, password=None, custom_email=None, status_callback=None, account_num=1, total=1):
        if not password:
            password = self.generate_password()
        if not custom_email:
            custom_email = self.generate_username(first_name, last_name)

        # FORCE proxy usage - never use Direct IP if proxies available
        proxy = await self._rotate_proxy()
        if not proxy:
            # Try again with fresh fetch
            proxy = await self.pm.get_working_proxy()

        if proxy:
            proxy_str = proxy['original']
            proxy_server = proxy['server']
            proxy_user = proxy.get('username')
            proxy_pass = proxy.get('password')
        else:
            proxy_str = 'Direct IP'
            proxy_server = None
            proxy_user = None
            proxy_pass = None
            print("⚠️ WARNING: No live proxies available! Using Direct IP...")

        async def send_log(msg):
            print(f"[{account_num}/{total}] {msg}", flush=True)
            if status_callback:
                try:
                    await status_callback(f"[{account_num}/{total}] {msg}")
                except:
                    pass

        await send_log(f"Starting... Proxy: {proxy_str[:30]}")

        max_retries = 3
        retry_count = 0
        blocking_detected = False

        while retry_count < max_retries and not blocking_detected:
            try:
                async with async_playwright() as p:
                    # CRITICAL FIX: Proxy at BROWSER level, not context level
                    # Context-level proxy auth fails silently in some Playwright versions
                    launch_options = {
                        'headless': config.HEADLESS,
                        'args': [
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-images',
                            '--mute-audio',
                        ]
                    }
                    if proxy_server:
                        launch_options['proxy'] = {
                            'server': proxy_server,
                            'username': proxy_user,
                            'password': proxy_pass
                        }
                        print(f"🌐 Browser launching with proxy: {proxy_str[:40]}...")

                    browser = await p.chromium.launch(**launch_options)

                    ctx = {
                        'viewport': {'width': 1366, 'height': 768},
                        'user_agent': self.ua.random,
                        'locale': 'en-US',
                        'timezone_id': 'America/New_York',
                    }
                    # DO NOT add proxy here - already set at browser launch level

                    context = await browser.new_context(**ctx)

                    # ADVANCED ANTI-DETECTION
                    await context.add_init_script("""
                        // Remove webdriver flag
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

                        // Fake Chrome runtime
                        window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}};

                        // Fake plugins
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });

                        // Fake languages
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['en-US', 'en']
                        });

                        // Fake platform
                        Object.defineProperty(navigator, 'platform', {
                            get: () => 'Win32'
                        });

                        // Remove automation indicators
                        delete window.__webdriver_script_fn;
                        delete window.__driver_evaluate;
                        delete window.__webdriver_evaluate;
                        delete window.__selenium_evaluate;
                        delete window.__fxdriver_evaluate;

                        // Canvas fingerprint protection
                        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                        HTMLCanvasElement.prototype.toDataURL = function() {
                            const context = this.getContext('2d');
                            if (context) {
                                const imageData = context.getImageData(0, 0, this.width, this.height);
                                for (let i = 0; i < imageData.data.length; i += 4) {
                                    imageData.data[i] += Math.random() * 2 - 1;
                                }
                                context.putImageData(imageData, 0, 0);
                            }
                            return originalToDataURL.apply(this, arguments);
                        };

                        // WebGL fingerprint protection
                        const getParameter = WebGLRenderingContext.getParameter;
                        WebGLRenderingContext.getParameter = function(parameter) {
                            if (parameter === 37445) return 'Intel Inc.';
                            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                            return getParameter(parameter);
                        };
                    """)
                    page = await context.new_page()

                    # NEW: Verify proxy IP before signup
                    if proxy_server:
                        await send_log("🌐 Verifying proxy IP...")
                        try:
                            await page.goto('https://api.ipify.org', timeout=15000)
                            ip_text = (await page.text_content('body')).strip()
                            await send_log(f"🌐 Proxy IP: {ip_text}")
                            print(f"[IP CHECK] Browser IP through proxy: {ip_text}")

                            # Also show IP info from proxy manager if available
                            if proxy and 'ip_info' in proxy:
                                info = proxy['ip_info']
                                await send_log(f"📍 {info.get('country','?')} | {info.get('isp','?')}")
                        except Exception as e:
                            await send_log(f"⚠️ IP check failed (continuing anyway): {e}")

                    await send_log("Loading signup...")
                    await page.goto('https://accounts.google.com/signup', timeout=60000, wait_until='networkidle')
                    await send_log("Page loaded")
                    await self._human_delay(2, 4)

                    username_attempts = 0
                    max_username_attempts = 10
                    password_attempts = 0
                    max_password_attempts = 3

                    for step in range(50):
                        page_type = await self._detect_page(page)
                        await send_log(f"Step {step+1}: {page_type}")

                        if page_type == 'error':
                            # Check if it's Google blocking
                            is_blocked, reason = await self._check_for_blocking(page)
                            if is_blocked:
                                blocking_detected = True
                                await send_log(f"🚫 GOOGLE BLOCKING DETECTED: {reason}")
                                await send_log("💡 SOLUTION: Use residential proxies!")
                                await browser.close()
                                return {
                                    "success": False, 
                                    "error": f"Google blocking this IP ({reason}). Use RESIDENTIAL PROXIES!", 
                                    "email_attempted": f"{custom_email}@gmail.com", 
                                    "proxy_used": proxy_str,
                                    "blocked": True
                                }

                            await page.go_back()
                            await self._human_delay(2, 4)
                            continue

                        elif page_type == 'names':
                            await self._handle_names(page, first_name, last_name)
                            await send_log(f"Names: {first_name} {last_name}")

                        elif page_type == 'birthday':
                            await self._handle_birthday(page)
                            await send_log("Birthday done")

                        elif page_type == 'email_phone':
                            await self._handle_email_phone(page)
                            await send_log("Email/phone done")

                        elif page_type == 'username':
                            if username_attempts >= max_username_attempts:
                                await browser.close()
                                return {"success": False, "error": f"Username failed {max_username_attempts}x", "email_attempted": f"{custom_email}@gmail.com", "proxy_used": proxy_str}

                            username_attempts += 1
                            result = await self._handle_username(page, custom_email, first_name, last_name, username_attempts)

                            if result == "taken":
                                custom_email = self.generate_username(first_name, last_name, username_attempts)
                                await send_log(f"Username taken, new: {custom_email}")
                                continue
                            elif result == "stuck":
                                custom_email = self.generate_username(first_name, last_name, username_attempts)
                                await send_log(f"Username stuck, new: {custom_email}")
                                continue
                            elif result == "error":
                                continue
                            else:
                                await send_log(f"Username OK: {custom_email}")

                        elif page_type == 'password':
                            if password_attempts >= max_password_attempts:
                                await browser.close()
                                return {"success": False, "error": f"Password failed {max_password_attempts}x", "email_attempted": f"{custom_email}@gmail.com", "proxy_used": proxy_str}

                            password_attempts += 1
                            if password_attempts > 1:
                                password = self.generate_password()

                            result = await self._handle_password(page, password)

                            if result == "success":
                                await send_log("Password OK!")
                            elif result == "blocked":
                                blocking_detected = True
                                await send_log("🚫 GOOGLE IS BLOCKING THIS IP")
                                await send_log("💡 Use RESIDENTIAL PROXIES to fix this!")
                                await browser.close()
                                return {
                                    "success": False,
                                    "error": "Google blocked this IP. Try: 1) Fresh sticky session 2) Different proxy 3) Wait 10min",
                                    "email_attempted": f"{custom_email}@gmail.com",
                                    "proxy_used": proxy_str,
                                    "blocked": True
                                }
                            elif result == "validation_error":
                                await send_log(f"Password validation error, retry {password_attempts}/{max_password_attempts}")
                            else:
                                await send_log(f"Password failed, retry {password_attempts}/{max_password_attempts}")

                        elif page_type == 'terms':
                            await self._handle_terms(page)
                            await send_log("Terms done")

                        elif page_type == 'phone':
                            await send_log("⚠️ Phone verification required")
                            await send_log("This is NORMAL for new signups!")
                            await send_log("Google wants to verify you're human")
                            await send_log("")
                            await send_log("💡 SOLUTIONS:")
                            await send_log("1. Wait 24 hours and try again")
                            await send_log("2. Use SMS verification service")
                            await send_log("3. Try different proxy provider")
                            await send_log("")
                            await send_log("Attempting skip methods...")

                            # Method 1: Look for Skip button
                            skip_methods = [
                                'button:has-text("Skip")',
                                'button:has-text("skip")',
                                '[data-skip]',
                                'button[jsname*="skip" i]',
                            ]

                            skipped = False
                            for method in skip_methods:
                                try:
                                    skip = await page.wait_for_selector(method, timeout=3000)
                                    if skip:
                                        await skip.click()
                                        await send_log("✅ Skipped phone verification!")
                                        skipped = True
                                        await self._human_delay(3, 5)
                                        break
                                except:
                                    continue

                            if not skipped:
                                # Method 2: Try "Use another way" or similar
                                alt_methods = [
                                    'button:has-text("Use another")',
                                    'button:has-text("Try another")',
                                    'button:has-text("I\'ll do it later")',
                                    'button:has-text("Do it later")',
                                ]

                                for method in alt_methods:
                                    try:
                                        btn = await page.wait_for_selector(method, timeout=3000)
                                        if btn:
                                            await btn.click()
                                            await send_log("✅ Used alternative method!")
                                            skipped = True
                                            await self._human_delay(3, 5)
                                            break
                                    except:
                                        continue

                            if not skipped:
                                # Method 3: Go back and try different approach
                                await send_log("⚠️ Cannot skip phone - trying alternative...")

                                # Try going back
                                try:
                                    await page.go_back()
                                    await self._human_delay(2, 4)

                                    # Check if we're back on password page
                                    if 'password' in page.url.lower():
                                        # Try different password that might not trigger phone
                                        await send_log("Trying different password...")
                                        password = self.generate_password()
                                        continue
                                except:
                                    pass

                                await browser.close()
                                return {
                                    "success": False, 
                                    "error": "Phone verification required. Try:\n1. Different proxy\n2. Different password\n3. Wait 24 hours", 
                                    "email_attempted": f"{custom_email}@gmail.com", 
                                    "proxy_used": proxy_str
                                }

                        elif page_type == 'recovery':
                            try:
                                skip = await page.wait_for_selector('button:has-text("Skip")', timeout=5000)
                                if skip:
                                    await skip.click()
                                    await send_log("Skipped recovery")
                            except:
                                pass
                            await self._human_delay(1, 2)

                        elif page_type == 'success':
                            await send_log("SUCCESS!")
                            break

                        else:
                            await send_log(f"Unknown: {page.url[:50]}")
                            await self._human_delay(2, 4)

                        await self._human_delay(1, 3)

                    final_url = page.url
                    await send_log(f"Final: {final_url[:60]}")

                    success = 'myaccount' in final_url or 'welcome' in final_url

                    await page.screenshot(path=os.path.join(self.debug_dir, f"final_{custom_email}.png"))
                    await browser.close()

                    if success:
                        return {"success": True, "email": f"{custom_email}@gmail.com", "password": password, "first_name": first_name, "last_name": last_name, "proxy_used": proxy_str}
                    else:
                        return {"success": False, "error": f"Stopped at: {final_url[:100]}", "email_attempted": f"{custom_email}@gmail.com", "proxy_used": proxy_str}

            except Exception as e:
                error_msg = str(e)[:300]
                await send_log(f"ERROR: {error_msg}")
                retry_count += 1
                if retry_count < max_retries and not blocking_detected:
                    await send_log(f"Retry {retry_count}/{max_retries}")
                    proxy = await self._rotate_proxy()
                    if proxy:
                        proxy_str = proxy['original']
                else:
                    if proxy:
                        await self.pm.report_proxy_failure(proxy_str)
                    return {"success": False, "error": error_msg, "email_attempted": f"{custom_email}@gmail.com", "proxy_used": proxy_str}

        if blocking_detected:
            return {
                "success": False,
                "error": "🚫 GOOGLE IS BLOCKING YOUR IP!\n\n💡 SOLUTION: Add RESIDENTIAL PROXIES\n\n1. Buy residential proxies\n2. Go to Proxy Manager\n3. Add proxies\n4. Try again",
                "email_attempted": f"{custom_email}@gmail.com",
                "proxy_used": proxy_str,
                "blocked": True
            }

        return {"success": False, "error": "Max retries exceeded", "email_attempted": f"{custom_email}@gmail.com", "proxy_used": proxy_str}
