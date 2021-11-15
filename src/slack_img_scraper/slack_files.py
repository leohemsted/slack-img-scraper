import asyncio
import os
from datetime import datetime
from pathlib import Path

import httpx
from slack_sdk import WebClient

CHANNELS_TO_ARCHIVE = {"leo-bot-test-channel"}
DOWNLOAD_PATH = Path("output")
# CHANNELS_TO_ARCHIVE = {"chat", "social-rides", "mud", "mallorca"}


class SlackImageDownloader:
    def __init__(self):
        self.client = WebClient(token=os.environ["SLACK_TOKEN"])
        self.users = {
            x["id"]: x for page in self.client.users_list() for x in page["members"]
        }
        self.channels = {
            channel["id"]: channel
            for page in self.client.conversations_list()
            for channel in page["channels"]
        }

        self.run_start_ts = datetime.utcnow().timestamp()

        with open(".last-run-ts.txt", "r") as last_run_f:
            self.last_run_ts = last_run_f.read()

    def get_files(self):
        kwargs = {
            "types": ["images"],
            "ts_from": self.last_run_ts,
            "ts_to": self.run_start_ts,
        }
        response = self.client.files_list(**kwargs)
        yield from response["files"]
        if response["paging"]["pages"] > 1:
            for i in range(2, response["paging"]["pages"] + 1):
                print(f"page {i}")
                yield from self.client.files_list(
                    **kwargs,
                    page=i,
                )["files"]

    def get_local_filename_for_file(self, file):
        """
        channel-date-username-timestamp.filetype
        """
        channel = (
            self.channels[file["channels"][0]]
            if file.get("channels", [])
            else "unknown-channel"
        )
        dt = datetime.fromtimestamp(file["timestamp"])
        user = self.users[file["user"]]
        username = user.get("real_name", user["name"]).lower().replace(" ", "-")
        return f"{channel['name']}-{dt.date().isoformat()}-{username}-{file['timestamp']}.{file['filetype']}"

    async def download_images(self):
        tasks = []
        for file in self.get_files():
            remote_url = file["url_private"]
            local_filename = self.get_local_filename_for_file(file)
            print(remote_url, local_filename)
            tasks.append(
                asyncio.create_task(self.download_file(local_filename, remote_url))
            )

        await asyncio.gather(*tasks)
        with open(".last-run-ts.txt", "w") as last_run_f:
            last_run_f.write(str(datetime.utcnow().timestamp()))

    async def download_file(self, local_filename, remote_url):
        async with httpx.AsyncClient() as httpx_client:
            print(f"2 - {local_filename}")
            resp = await httpx_client.get(
                remote_url,
                headers={"Authorization": f"Bearer {self.client.token}"},
            )
        resp.raise_for_status()

        # if there's an issue with auth, slack will redirect to a login
        if "image" not in resp.headers["content-type"]:
            raise ValueError(f"Couldn't download {remote_url} to {local_filename}")

        with open(DOWNLOAD_PATH / local_filename, "wb") as img_file:
            print(f"writing to {local_filename}")
            img_file.write(resp.content)
