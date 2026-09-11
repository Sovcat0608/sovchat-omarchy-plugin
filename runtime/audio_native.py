"""Scoped native output control. Never mute other applications or system sinks."""
import asyncio
import json
import os
import shutil
from api import ApiError


async def set_output_muted(muted):
    if type(muted) is not bool or not shutil.which("pactl"): raise ApiError("MEDIA_UNAVAILABLE")
    async def run(*args):
        process = await asyncio.create_subprocess_exec("pactl", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 2)
            if process.returncode or len(output) > 1024 * 1024: raise ApiError("MEDIA_FAILED")
            return output
        finally:
            if process.returncode is None: process.kill(); await process.wait()
    entries = json.loads(await run("-f", "json", "list", "sink-inputs"))
    for entry in entries:
        if str(entry.get("properties", {}).get("application.process.id")) == str(os.getpid()):
            index = entry.get("index")
            if type(index) is not int or index < 0: raise ApiError("MEDIA_FAILED")
            await run("set-sink-input-mute", str(index), "1" if muted else "0")


def device_rows(devices):
    return [{"id": str(device.id), "name": str(device.name)} for device in devices][:100]
