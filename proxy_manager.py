import asyncio
import aiohttp
import re
import uuid
from typing import List, Tuple, Optional, Dict
from config import config

class ProxyManager:
    def __init__(self, db):
        self.db = db

    def parse_proxy(self, proxy_str: str) -> Optional[Dict]:
        """Parse ANY proxy format"""
        proxy_str = proxy_str.strip()

        # Remove protocol if present
        proxy_str = re.sub(r'^https?://', '', proxy_str)
        proxy_str = re.sub(r'^socks[45]?://', '', proxy_str)

        # Split by :
        parts = proxy_str.split(':')

        if len(parts) == 2:
            # Format: host:port
            host, port = parts
            return {
                'host': host,
                'port': port,
                'username': None,
                'password': None,
                'auth': False
            }

        elif len(parts) == 4:
            # Format: host:port:user:pass
            host, port, user, pwd = parts
            return {
                'host': host,
                'port': port,
                'username': user,
                'password': pwd,
                'auth': True
            }

        elif len(parts) == 3:
            # Format: host:port:auth (some providers)
            host, port, auth = parts
            # Try to split auth
            if '@' in auth:
                user, pwd = auth.split('@', 1)
                return {
                    'host': host,
                    'port': port,
                    'username': user,
                    'password': pwd,
                    'auth': True
                }

        return None

    def build_proxy_url(self, parsed: Dict, auth_type='standard') -> str:
        """Build proxy URL in different formats"""
        host = parsed['host']
        port = parsed['port']
        user = parsed.get('username')
        pwd = parsed.get('password')

        if not parsed['auth']:
            return f"http://{host}:{port}"

        if auth_type == 'standard':
            # user:pass@host:port
            return f"http://{user}:{pwd}@{host}:{port}"
        elif auth_type == 'swapped':
            # pass:user@host:port
            return f"http://{pwd}:{user}@{host}:{port}"
        elif auth_type == 'encoded':
            # URL encoded
            from urllib.parse import quote
            return f"http://{quote(user)}:{quote(pwd)}@{host}:{port}"

        return f"http://{user}:{pwd}@{host}:{port}"


    def make_sticky(self, parsed: Dict) -> Dict:
        """
        Add sticky session for rotating residential proxies.
        Decodo/Smartproxy format: username-sessid-XXXXXX
        This keeps the SAME IP for the entire signup session.
        """
        if not parsed.get('auth') or not parsed.get('username'):
            return parsed

        username = parsed['username']

        # Don't double-add if already has session param
        if '-sessid-' in username or '-session-' in username or '-sess-' in username:
            return parsed

        # Generate unique session ID (Decodo keeps sticky ~10 min per sessid)
        session_id = uuid.uuid4().hex[:8]
        parsed['username'] = f"{username}-sessid-{session_id}"
        return parsed

    async def verify_proxy_ip(self, proxy_url: str) -> Dict:
        """Check the actual IP and ISP through the proxy"""
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    'http://ip-api.com/json',
                    proxy=proxy_url,
                    ssl=False
                ) as resp:
                    data = await resp.json()
                    return {
                        'ip': data.get('query', 'unknown'),
                        'isp': data.get('isp', 'unknown'),
                        'org': data.get('org', 'unknown'),
                        'country': data.get('country', 'unknown'),
                        'mobile': data.get('mobile', False),
                        'proxy_flag': data.get('proxy', False),
                        'hosting': data.get('hosting', False)
                    }
        except Exception as e:
            return {'ip': 'unknown', 'error': str(e)}

    async def check_proxy(self, proxy_str: str) -> Tuple[bool, float, str]:
        """Check proxy - SIMPLE and RELIABLE"""
        parsed = self.parse_proxy(proxy_str)
        if not parsed:
            return False, 0.0, "parse_error"

        # Try different auth formats
        auth_types = ['standard', 'swapped'] if parsed['auth'] else ['none']

        for auth_type in auth_types:
            try:
                proxy_url = self.build_proxy_url(parsed, auth_type)

                timeout = aiohttp.ClientTimeout(total=20)
                start = asyncio.get_event_loop().time()

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # Simple test - just check if we can reach Google
                    async with session.get(
                        'https://www.google.com/generate_204',
                        proxy=proxy_url,
                        ssl=False
                    ) as response:
                        latency = asyncio.get_event_loop().time() - start

                        if response.status == 204:
                            return True, latency, auth_type

            except asyncio.TimeoutError:
                continue
            except aiohttp.ClientProxyConnectionError:
                continue
            except aiohttp.ClientHttpProxyError as e:
                if e.status == 407:
                    # Auth failed, try next format
                    continue
                continue
            except Exception:
                continue

        return False, 0.0, "failed"

    async def import_proxies(self, proxy_data: str) -> Dict[str, int]:
        """Import and validate proxies"""
        lines = proxy_data.strip().split('\n')
        live = 0
        dead = 0
        invalid = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parsed = self.parse_proxy(line)
            if not parsed:
                invalid += 1
                continue

            # Validate
            is_live, latency, auth_type = await self.check_proxy(line)

            if is_live:
                await self.db.add_proxy(line, 'http')
                await self.db.update_proxy_status(line, 'live', latency)
                live += 1
            else:
                dead += 1

        return {"live": live, "dead": dead, "invalid": invalid}

    async def validate_all_proxies(self, status_callback=None):
        """Re-validate all proxies"""
        import aiosqlite
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute("SELECT proxy_string FROM proxies")
            rows = await cursor.fetchall()

        live_count = 0
        for row in rows:
            proxy = row[0]
            is_live, latency, auth_type = await self.check_proxy(proxy)

            if is_live:
                await self.db.update_proxy_status(proxy, 'live', latency)
                live_count += 1
                if status_callback:
                    await status_callback(f"✅ {proxy[:40]}... ({latency:.2f}s)")
            else:
                await self.db.update_proxy_status(proxy, 'dead')
                if status_callback:
                    await status_callback(f"❌ {proxy[:40]}...")

        return live_count

    async def get_working_proxy(self) -> Optional[Dict]:
        """Get a working proxy with STICKY SESSION and IP verification"""
        import aiosqlite
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute(
                "SELECT proxy_string FROM proxies WHERE status='live' ORDER BY response_time ASC LIMIT 10"
            )
            rows = await cursor.fetchall()

        for row in rows:
            proxy_str = row[0]
            parsed = self.parse_proxy(proxy_str)
            if parsed:
                # MAKE STICKY - same IP for entire session (CRITICAL FIX)
                parsed = self.make_sticky(parsed)

                for auth_type in ['standard', 'swapped'] if parsed['auth'] else ['none']:
                    proxy_url = self.build_proxy_url(parsed, auth_type)

                    # Verify the IP is actually working and get info
                    ip_info = await self.verify_proxy_ip(proxy_url)

                    return {
                        'server': f"http://{parsed['host']}:{parsed['port']}",
                        'username': parsed.get('username'),
                        'password': parsed.get('password'),
                        'original': proxy_str,
                        'url': proxy_url,
                        'ip_info': ip_info
                    }

        return None

    async def get_single_proxy(self) -> Optional[Dict]:
        return await self.get_working_proxy()

    async def report_proxy_failure(self, proxy_str: str):
        await self.db.mark_proxy_failed(proxy_str)
