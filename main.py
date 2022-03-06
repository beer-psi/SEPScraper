import json
import plistlib
import remotezip
import asyncio
import pathlib
import aiopath
import aiofiles
import logging
from requests_futures.sessions import FuturesSession
from typing import Union
from utils import *


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


async def save_all_signed_sepbb(device):
    logging.info(f"Getting signing status for {device['identifier']}")
    signed_ipsw = await get_signing_status(device["identifier"])

    for fw in signed_ipsw:
        logging.info(f"Getting build manifest for firmware {fw['buildid']}")
        async with aiofiles.tempfile.TemporaryDirectory() as tmpdir:
            manifest = await get_manifest(
                fw["url"], aiopath.AsyncPath(tmpdir) / f"{fw['buildid']}.plist"
            )

            with open(manifest, "rb") as f:
                buildmanifest = plistlib.loads(f.read())
        boards = [
            x for x in device["boards"] if x["boardconfig"].lower().endswith("ap")
        ]
        tasks = [
            asyncio.create_task(save_sepbb(device, board, fw, buildmanifest))
            for board in boards
        ]
        await gather_with_concurrency(2, *tasks)


async def main():
    logging.info("Getting all devices")
    with FuturesSession() as session:
        devices = session.get("https://api.ipsw.me/v4/devices").result().json()

    for device in devices:
        await save_all_signed_sepbb(device)


if __name__ == "__main__":
    asyncio.run(main())
