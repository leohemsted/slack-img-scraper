import logging
import os
from datetime import datetime
from pathlib import Path

import click
import httpx
from slack_sdk import WebClient

CHANNELS_TO_ARCHIVE = {"leo-bot-test-channel"}
DOWNLOAD_PATH = Path("output")
# CHANNELS_TO_ARCHIVE = {"chat", "social-rides", "mud", "mallorca"}


class SlackImageDownloader:
    def __init__(self):
        self.client = WebClient(token=os.environ["SLACK_TOKEN"])
        self.users = {x["id"]: x for x in self.client.users_list()["members"]}
        self.channels = {
            channel["name"]: channel
            for channel in self.client.conversations_list()["channels"]
            # skip DMs etc
            if channel["is_channel"]
        }

        with open(".last-run-ts.txt", "r") as last_run_f:
            self.last_run_ts = last_run_f.read()

    def download_images(self):
        for name_to_archive in CHANNELS_TO_ARCHIVE:
            channel = self.channels[name_to_archive]
            self.get_images_for_channel(channel)

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
        for message in history["messages"]:
            # the first message in a thread is the thread starter, we don't want to
            # recurse if we're inside the thread already so set a flag
            if not is_thread and "thread_ts" in message:
                print(message["latest_reply"], self.last_run_ts)
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
            if message["ts"] > self.last_run_ts:
                if "files" in message:
                    for file in message["files"]:
                        if file["mimetype"].startswith("image"):
                            print("found file", file["url_private"])
                            yield file
        if history["has_more"]:
            print("more to come!")

    def get_images_for_channel(self, channel):
        # can't filter on old messages here in case there are new images inside threads
        # that are replies to old messages
        history = self.client.conversations_history(channel=channel["id"])
        for file in self.get_image_files_for_history(channel, history):
            local_filename = self.get_local_filename_for_file(channel, file)
            resp = httpx.get(
                file["url_private"],
                headers={"Authorization": f"Bearer {self.client.token}"},
            )
            resp.raise_for_status()

            # if there's an issue with auth, slack will redirect to a login
            if "image" not in resp.headers["content-type"]:
                raise ValueError(
                    f"Couldn't download {file['url_private']} to {local_filename}"
                )

            with open(DOWNLOAD_PATH / local_filename, "wb") as img_file:
                print(f"writing to {local_filename}")
                img_file.write(resp.content)
