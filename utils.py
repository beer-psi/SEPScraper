import plistlib
import remotezip
import aiopath
import asyncio
import logging
from requests_futures.sessions import FuturesSession
from typing import Union


async def gather_with_concurrency(n, *tasks):
    """
    A small utility to run asyncio.gather with concurrency limits.
    `n` is the number of concurrent tasks to run at the same time
    `tasks` is the tasks to run.
    Return the return values of the tasks.
    """
    semaphore = asyncio.Semaphore(n)

    async def sem_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(task) for task in tasks))


def pzb(url: str, filename: str, output_path: str) -> Union[bool, aiopath.AsyncPath]:
    """Extracts a file from a remote ZIP file.

    Args:
        url (str): URL of zip file
        filename (str): File to extract from zip
        output_path (str): Where to save the extracted file

    Returns:
        Union[bool, aiopath.AsyncPath]: Returns the path if extraction was successful, otherwise returns False.
    """
    try:
        with remotezip.RemoteZip(url) as ipsw:
            file = ipsw.read(filename)
    except remotezip.RemoteIOError:
        return False

    with open(output_path, "wb") as f:
        f.write(file)

    return aiopath.AsyncPath(output_path)


async def get_manifest(url: str, path: str) -> Union[bool, aiopath.AsyncPath]:
    """Gets BuildManifest.plist from an IPSw url

    Args:
        url (str): Download link for an IPSW
        path (str): Path to save the BuildManifest to (including filename)

    Returns:
        Union[bool, aiopath.AsyncPath]: Returns the path if saving was successful, otherwise returns False.
    """
    with FuturesSession() as session:
        resp = session.get(
            f"{'/'.join(url.split('/')[:-1])}/BuildManifest.plist"
        ).result()
    if resp.status_code == 200:
        manifest = resp.content

        with open(path, "wb") as f:
            f.write(manifest)

        return aiopath.AsyncPath(path)
    else:
        return await asyncio.to_thread(
            pzb, url, "BuildManifest.plist", path
        ) or await asyncio.to_thread(pzb, url, "BuildManifesto.plist", path)


async def get_signing_status(identifier: str) -> list:
    """Get all signed versions for a device.

    Args:
        identifier (str): Device identifier (e.g. iPhone10,5)

    Returns:
        list: List of all currently signed versions for the device
    """
    with FuturesSession() as session:
        beta_status_future = session.get(f"https://api.m1sta.xyz/betas/{identifier}")
        status_future = session.get(
            f"https://api.ipsw.me/v4/device/{identifier}?type=ipsw"
        )
        beta_status = beta_status_future.result()
        if beta_status.status_code == 200:
            beta_status = beta_status.json()
            beta_status_list = [x for x in beta_status if "signed" in x and x["signed"]]
        else:
            beta_status_list = []
        status = status_future.result()
        if status.status_code == 200:
            status = status.json()
            status_list = [
                x for x in status["firmwares"] if "signed" in x and x["signed"]
            ]
        else:
            status_list = []
    return status_list + beta_status_list


async def save_sepbb(
    device: dict, board: dict, firm: dict, manifest: dict
) -> Union[aiopath.AsyncPath, bool]:
    """Saves SEP and/or baseband firmware for one device, on one board, on one version.

    Args:
        device (dict): The device to save SEP/Baseband for. It should have the `identifier` key.
        board (dict): The boardconfig of the device.
        firm (dict): The firmware to save SEP/Baseband for.
        manifest (dict): The build manifest for that firmware. Must be loaded through plistlib.

    Returns:
        Union[aiopath.AsyncPath, bool]: Returns the folder containing SEP/Baseband firmware on success, False on failure.

    Notes:
        Check https://api.ipsw.me/v4/devices and https://api.ipsw.me/v4/device/:identifier to see how device, board and firm looks like.
    """
    save_path = aiopath.AsyncPath(
        f"./output/{firm['version'].replace(' ', '-')}_{firm['buildid']}/{device['identifier']}/{board['boardconfig']}"
    )

    try:
        buildidentity = next(
            x
            for x in manifest["BuildIdentities"]
            if x["Info"]["DeviceClass"].lower() == board["boardconfig"].lower()
        )
    except StopIteration:
        logging.error("Couldn't get data from BuildManifest")
        return False

    if "RestoreSEP" in buildidentity["Manifest"]:
        sep_path = buildidentity["Manifest"]["RestoreSEP"]["Info"]["Path"]
        logging.info(
            f"[{device['identifier']}, {board['boardconfig']}, {firm['buildid']}] Found SEP firmware at {sep_path}"
        )
    else:
        sep_path = None
        logging.warning(
            f"[{device['identifier']}, {board['boardconfig']}, {firm['buildid']}] Couldn't find SEP firmware"
        )

    if "BasebandFirmware" in buildidentity["Manifest"]:
        bb_path = buildidentity["Manifest"]["BasebandFirmware"]["Info"]["Path"]
        logging.info(
            f"[{device['identifier']}, {board['boardconfig']}, {firm['buildid']}] Found baseband firmware at {bb_path}"
        )
    else:
        bb_path = None
        logging.warning(
            f"[{device['identifier']}, {board['boardconfig']}, {firm['buildid']}] Couldn't find baseband firmware"
        )

    if sep_path or bb_path:
        logging.info(
            f"[{device['identifier']}, {board['boardconfig']}, {firm['buildid']}] Saving SEP and/or BB firmware to {save_path}"
        )
        await save_path.mkdir(parents=True, exist_ok=True)
        if sep_path:
            await asyncio.to_thread(
                pzb,
                firm["url"],
                sep_path,
                save_path / aiopath.AsyncPath(sep_path).parts[-1],
            )
        if bb_path:
            await asyncio.to_thread(
                pzb,
                firm["url"],
                bb_path,
                save_path / aiopath.AsyncPath(bb_path).parts[-1],
            )
        return save_path
    else:
        logging.warning(
            f"[{device['identifier']}, {board['boardconfig']}, {firm['buildid']}] There is no SEP/BB for this IPSW"
        )
        return False
