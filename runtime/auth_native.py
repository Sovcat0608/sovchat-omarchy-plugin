"""System-browser Google callback and opt-in Secret Service persistence."""
import asyncio
import secrets
import shutil
import os
from urllib.parse import urlencode, urlsplit, parse_qs
from api import ApiError, API_ORIGIN


class Vault:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.program = None if os.environ.get("SOVCHAT_NATIVE_DISABLE_KEYRING") == "1" else shutil.which("secret-tool")

    async def command(self, op, token=None):
        if not self.program:
            if op in ("lookup", "clear"): return None
            raise ApiError("KEYRING_UNAVAILABLE")
        async with self.lock:
            args = [self.program, op]
            if op == "store": args += ["--label=SovChat Omarchy session"]
            args += ["application", "com.sovchat.omarchy", "credential", "session"]
            proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            try:
                output, _ = await asyncio.wait_for(proc.communicate(token.encode() if token else None), 20)
                if len(output) > 8193: raise ApiError("KEYRING_UNAVAILABLE")
                if proc.returncode and op == "store": raise ApiError("KEYRING_UNAVAILABLE")
                return output.decode().strip() if op == "lookup" and proc.returncode == 0 else None
            except BaseException:
                if proc.returncode is None: proc.kill()
                await proc.wait()
                raise

    async def load(self): return await self.command("lookup")
    async def save(self, token): await self.command("store", token)
    async def clear(self): await self.command("clear")


async def google_sign_in(remember=False):
    # This port/path is explicitly accepted by the existing server's desktop
    # return URL policy. Bind before opening the browser; never evict another app.
    nonce = secrets.token_urlsafe(32)
    result = asyncio.get_running_loop().create_future()
    clients = set()
    async def callback(reader, writer):
        if len(clients) >= 8:
            writer.close()
            return
        task = asyncio.current_task()
        clients.add(task)
        status = "400 Bad Request"
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            if len(raw) > 20000: return
            lines = raw.decode("ascii").split("\r\n")
            method, target, protocol = lines[0].split(" ")
            headers = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
            host = next((v.strip() for k, v in headers.items() if k.lower() == "host"), "")
            url = urlsplit(target)
            query = parse_qs(url.query, max_num_fields=10)
            if method == "GET" and host == "127.0.0.1:3001" and url.path == "/desktop" and query.get("nativeNonce") == [nonce] and not result.done():
                token = query.get("desktopSessionToken", [""])[0]
                if len(query.get("desktopSessionToken", [])) == 1 and token and len(token) <= 8192 and not any(c.isspace() for c in token):
                    result.set_result(token)
                    status = "200 OK"
                elif "authError" in query:
                    result.set_exception(ApiError("GOOGLE_FAILED"))
        except (ValueError, UnicodeError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            body = b"SovChat sign-in response received. Return to the Omarchy panel; you may close this tab."
            writer.write(("HTTP/1.1 " + status + "\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\nContent-Length: " + str(len(body)) + "\r\n\r\n").encode() + body)
            try: await writer.drain()
            except ConnectionError: pass
            writer.close()
            clients.discard(task)
    try:
        server = await asyncio.start_server(callback, "127.0.0.1", 3001, limit=20000)
    except OSError:
        raise ApiError("GOOGLE_FAILED") from None
    browser = None
    try:
        return_to = "http://127.0.0.1:3001/desktop?" + urlencode({"nativeNonce": nonce})
        url = API_ORIGIN + "/api/auth/google/start?" + urlencode({"clientKind": "desktop", "appVariant": "omarchy",
                         "rememberMe": "true" if remember else "false", "returnTo": return_to})
        browser = await asyncio.create_subprocess_exec("xdg-open", url, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(browser.wait(), 10)
        return await asyncio.wait_for(result, 180)
    except (OSError, asyncio.TimeoutError):
        raise ApiError("GOOGLE_FAILED") from None
    finally:
        if browser is not None and browser.returncode is None:
            browser.kill()
            await browser.wait()
        server.close()
        await server.wait_closed()
        for task in list(clients): task.cancel()
        await asyncio.gather(*clients, return_exceptions=True)
