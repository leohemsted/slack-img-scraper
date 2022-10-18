import sys
import asyncio
import os
import re
from datetime import datetime
from pathlib import Path

import boto3
import httpx
import yaml
from slack_sdk import WebClient

CHANNELS_TO_ARCHIVE = {"leo-bot-test-channel"}
DOWNLOAD_PATH = Path("output")
# CHANNELS_TO_ARCHIVE = {"chat", "social-rides", "mud", "mallorca"}

# limit number of concurrents
connection_pool = asyncio.Semaphore(50)


class LocalFiles(set):
    def __init__(self):
        # assumes channel-date-username-file_id.filetype
        super().__init__()
        for _path, _subdirs, files in os.walk(DOWNLOAD_PATH):
            self.update(file.split(".")[-2].split("-")[-1] for file in files)
        print(f"Found {len(self)} existing files")


class SlackImageDownloader:
    def __init__(self, s3):
        with open("config.yml") as config:
            self.config = yaml.load(config, Loader=yaml.SafeLoader)
        self.s3 = boto3.resource("s3") if s3 else None
        self.client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        self.users = {
            x["id"]: x for page in self.client.users_list() for x in page["members"]
        }
        self.channels = {
            channel["id"]: channel
            for page in self.client.conversations_list()
            for channel in page["channels"]
            if channel["name"] not in self.config["channels_to_skip"]
        }

        self.existing_files = LocalFiles()

        self.run_start_ts = datetime.utcnow().timestamp()

        self.set_last_run_ts()

    def set_last_run_ts(self):
        if self.s3:
            s3 = boto3.resource("s3")
        else:
            with open(".last-run-ts.txt", "r") as last_run_f:
                self.last_run_ts = last_run_f.read()

    def get_files(self):
        kwargs = {
            "types": ["images"],
            "ts_from": self.last_run_ts,
            "ts_to": self.run_start_ts,
        }
        response = self.client.files_list(**kwargs)
        print(response["paging"])
        yield from response["files"]
        for i in range(2, response["paging"]["pages"] + 1):
            response = self.client.files_list(
                **kwargs,
                page=i,
            )
            print(
                f"page {i} of {response['paging']['pages']} - can access "
                f"{len(response['files'])} files out of {response['paging']['count']}"
            )
            yield from response["files"]

    def get_local_filename_for_file(self, file):
        """
        returns two vals: folder and filename.
        channel / date-username-file_id.filetype

        assumption: file is shared in at least one channel that we archive. we'll pick
        the first channel as slack orders them in the api
        """
        channel = next(
            (
                self.channels[channel_id]
                for channel_id in file.get("channels", [])
                if channel_id in self.channels
            ),
            {"name": "unknown-channel"},
        )
        dt = datetime.fromtimestamp(file["timestamp"])
        user = self.users[file["user"]]
        # remove all non-filename-friendly characters from peoples names
        username = re.sub(r"[^\w\d-]", "_", user.get("real_name", user["name"])).lower()
        return (
            f"{channel['name']}",
            f"{dt.date().isoformat()}-{username}-{file['id']}.{file['filetype']}",
        )

    async def download_images(self):
        tasks = []
        for file in self.get_files():
            remote_url = file["url_private"]

            if (
                # if it's been shared in at least one channel we care about
                any(
                    channel_id in self.channels
                    for channel_id in file.get("channels", [])
                )
                # if we haven't downloaded it already
                and file["id"] not in self.existing_files
            ):
                local_folder, local_filename = self.get_local_filename_for_file(file)
                print(f"{remote_url} -> {local_folder}/{local_filename}")
                tasks.append(
                    asyncio.create_task(
                        self.download_file(local_folder, local_filename, remote_url)
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [result for result in results if result is not None]
        if errors:
            print("Something went wrong! Take a look at it and try again")
            sys.exit(1)
        else:
            with open(".last-run-ts.txt", "w") as last_run_f:
                last_run_f.write(str(self.run_start_ts))

    async def download_file(self, local_folder, local_filename, remote_url):
        async with httpx.AsyncClient() as httpx_client, connection_pool:
            resp = await httpx_client.get(
                remote_url,
                headers={"Authorization": f"Bearer {self.client.token}"},
            )
        resp.raise_for_status()

        # if there's an issue with auth, slack will redirect to a login
        content_type = resp.headers["content-type"]
        if not ("image" in content_type or "binary" in content_type):
            print(
                f"Response headers suggest it's not an image. Status code {resp.status_code}. Headers: {resp.headers}"
            )
            raise ValueError(f"Couldn't download {remote_url} to {local_filename}")

        os.makedirs(DOWNLOAD_PATH / local_folder, exist_ok=True)
        with open(DOWNLOAD_PATH / local_folder / local_filename, "wb") as img_file:
            print(f"writing to {DOWNLOAD_PATH}/{local_folder}/{local_filename}")
            img_file.write(resp.content)
