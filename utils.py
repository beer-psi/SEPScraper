import plistlib
import remotezip
import aiopath
import asyncio
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
    try:
        with remotezip.RemoteZip(url) as ipsw:
            file = ipsw.read(filename)
    except remotezip.RemoteIOError:
        return False

    with open(output_path, 'wb') as f:
        f.write(file)

    return aiopath.AsyncPath(output_path)


async def get_manifest(url: str, path: str) -> Union[bool, aiopath.AsyncPath]:
    with FuturesSession() as session:
        resp = session.get(f"{'/'.join(url.split('/')[:-1])}/BuildManifest.plist").result()
    if resp.status_code == 200:
        manifest = resp.content

        with open(path, 'wb') as f:
            f.write(manifest)

        return aiopath.AsyncPath(path)
    else:
        return await asyncio.to_thread(pzb, url, "BuildManifest.plist", path) or await asyncio.to_thread(pzb, url, "BuildManifesto.plist", path)  


async def get_signing_status(identifier):
    with FuturesSession() as session:
        beta_status_future = session.get(f"https://api.m1sta.xyz/betas/{identifier}")
        status_future = session.get(f"https://api.ipsw.me/v4/device/{identifier}?type=ipsw")
        beta_status = beta_status_future.result()
        if beta_status.status_code == 200:
            beta_status = beta_status.json()
            beta_status_list = [x for x in beta_status if 'signed' in x and x['signed']]
        else:
            beta_status_list = []
        status = status_future.result()
        if status.status_code == 200:
            status = status.json()
            status_list = [x for x in status['firmwares'] if 'signed' in x and x['signed']]
        else:
            status_list = []
    return status_list + beta_status_list




