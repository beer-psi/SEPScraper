import json
import plistlib
import remotezip
import asyncio
import pathlib
import aiopath
import aiofiles
import posixpath
import logging
from requests_futures.sessions import FuturesSession
from typing import Union
from utils import *


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')


async def save_signed_sepbb(device):
    logging.info(f"Getting signing status for {device['identifier']}")
    signed_ipsw = await get_signing_status(device['identifier'])

    for fw in signed_ipsw:
        logging.info(f"Getting build manifest for firmware {fw['buildid']}")
        async with aiofiles.tempfile.TemporaryDirectory() as tmpdir:
            manifest = await get_manifest(fw['url'], posixpath.join(tmpdir, f"{fw['buildid']}.plist"))
        
            with open(manifest, 'rb') as f:
                buildmanifest = plistlib.loads(f.read())
        boards = [x for x in device['boards'] if x['boardconfig'].lower().endswith('ap')]
        for board in boards:
            try:
                buildidentity = next(
                    x for x in buildmanifest['BuildIdentities']
                    if x['Info']['DeviceClass'].lower() == board['boardconfig'].lower()
                )
            except StopIteration:
                logging.error("Couldn't get data from BuildManifest")
                continue

            if 'RestoreSEP' in buildidentity['Manifest']:
                sep_path = buildidentity['Manifest']['RestoreSEP']['Info']['Path']
                logging.info(f"[{device['identifier']}, {board['boardconfig']}, {fw['buildid']}] Found SEP firmware at {sep_path}")
            else:
                sep_path = None
                logging.warning(f"[{device['identifier']}, {board['boardconfig']}, {fw['buildid']}] Couldn't find SEP firmware")

            if 'BasebandFirmware' in buildidentity['Manifest']:
                bb_path = buildidentity['Manifest']['BasebandFirmware']['Info']['Path']
                logging.info(f"[{device['identifier']}, {board['boardconfig']}, {fw['buildid']}] Found baseband firmware at {bb_path}")
            else:
                bb_path = None
                logging.warning(f"[{device['identifier']}, {board['boardconfig']}, {fw['buildid']}] Couldn't find baseband firmware")

            logging.info(f"Downloading")
            output_path = aiopath.AsyncPath(f"./output/{device['identifier']}/{board['boardconfig']}/{fw['buildid']}")
            await output_path.mkdir(parents=True, exist_ok=True)
            if sep_path:
                pzb(fw['url'], sep_path, output_path / posixpath.split(sep_path)[-1])
            if bb_path:
                pzb(fw['url'], bb_path, output_path / posixpath.split(bb_path)[-1])


async def main():
    logging.info("Getting all devices")
    with FuturesSession() as session:
        devices = session.get("https://api.ipsw.me/v4/devices").result().json()

    for device in devices:
        await save_signed_sepbb(device)


if __name__ == "__main__":
    asyncio.run(main())
