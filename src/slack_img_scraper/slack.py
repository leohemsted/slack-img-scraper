import asyncio
import os
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from slack_sdk import WebClient

CHANNELS_TO_ARCHIVE = {"leo-bot-test-channel"}
DOWNLOAD_PATH = Path("output")
# CHANNELS_TO_ARCHIVE = {"chat", "social-rides", "mud", "mallorca"}


class SlackImageDownloader:
    def __init__(self):
        with open("config.yml") as config:
            self.config = yaml.load(config)
        self.client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        self.users = {
            x["id"]: x for page in self.client.users_list() for x in page["members"]
        }
        self.channels = {
            channel["name"]: channel
            for page in self.client.conversations_list()
            for channel in page["channels"]
            # skip DMs etc
            if channel["is_channel"]
            and channel["name"] not in config["channels_to_skip"]
        }

        with open(".last-run-ts.txt", "r") as last_run_f:
            self.last_run_ts = last_run_f.read()

    async def download_images(self):
        tasks = []
        for name_to_archive in CHANNELS_TO_ARCHIVE:
            channel = self.channels[name_to_archive]
            for local_filename, remote_url in self.get_image_urls_for_channel(channel):
                tasks.append(
                    asyncio.create_task(self.download_file(local_filename, remote_url))
                )
        await asyncio.gather(*tasks)
        with open(".last-run-ts.txt", "w") as last_run_f:
            last_run_f.write(str(datetime.utcnow().timestamp()))

    def get_local_filename_for_file(self, channel, file):
        """
        channel-date-username-time.filetype
        """
        dt = datetime.fromtimestamp(file["timestamp"])
        user = self.users[file["user"]]
        username = user.get("real_name", user["name"]).lower().replace(" ", "-")
        return f"{channel['name']}-{dt.date().isoformat()}-{username}-{file['timestamp']}.{file['filetype']}"

    def get_image_files_for_history(self, channel, history, is_thread=False):
        yield from (
            self.get_image_files_for_message(message, channel, is_thread)
            for page in history
            for message in page["messages"]
        )

    def get_image_files_for_message(self, message, channel, is_thread):
        # the first message in a thread is the thread starter, we don't want to recurse
        # if we're inside the thread already so set a flag
        if not is_thread and "thread_ts" in message:
            if message["latest_reply"] >= self.last_run_ts:
                print("start thread")
                thread_history = self.client.conversations_replies(
                    channel=channel["id"],
                    ts=message["thread_ts"],
                    oldest=self.last_run_ts,
                )
                yield from self.get_image_files_for_history(
                    channel, thread_history, is_thread=True
                )
                print("finish thread")

        # if the message is older than the last time we ran, then we don't need to
        # re-download the files from it
        if message["ts"] > self.last_run_ts and "files" in message:
            yield from (
                file
                for file in message["files"]
                if file["mimetype"].startswith("image")
            )

    def get_image_urls_for_channel(self, channel):
        # can't filter on old messages here in case there are new images inside threads
        # that are replies to old messages
        history = self.client.conversations_history(channel=channel["id"])
        for file in self.get_image_files_for_history(channel, history):
            local_filename = self.get_local_filename_for_file(channel, file)
            yield (local_filename, file["url_private"])

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
