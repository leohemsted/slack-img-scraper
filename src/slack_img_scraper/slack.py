import logging
import os
from datetime import datetime

import click
import httpx
from slack_sdk import WebClient

CHANNELS_TO_ARCHIVE = {"leo-bot-test-channel"}
DOWNLOAD_PATH = "output"
# CHANNELS_TO_ARCHIVE = {"chat", "social-rides", "mud", "mallorca"}


class SlackImageDownloader:
    def __init__(self, last_run: datetime = None):
        self.client = WebClient(token=os.environ["SLACK_TOKEN"])
        self.since_ts = last_run.timestamp()

    def download_images(self):
        channels = {
            channel["name"]: channel
            for channel in self.self.client.conversations_list()["channels"]
            if channel["is_channel"]
        }

        for name_to_archive in CHANNELS_TO_ARCHIVE:
            channel = channels[name_to_archive]
            self.get_images_for_channel(channel)

    @staticmethod
    def get_local_filename_for_file(channel, file, user):
        """
        channel-date-username-time.filetype
        """
        dt = datetime.fromtimestamp(file["timestamp"])
        username = user.get("real_name", user["name"]).lower().replace(" ", "-")
        return f"{channel['name']}-{dt.date().isoformat()}-{username}-{dt.time().isoformat()}.{file['filetype']}"

    def get_image_files_for_history(self, history):
        for message in history["messages"]:
            if "files" in message:
                for file in message["files"]:
                    if file["mimetype"].startswith("image"):
                        yield file
        if history.has_more:
            print("more to come!")

    def get_images_for_channel(self, channel):
        users = {x.id: x for x in self.client.users_list()["members"]}
        history = self.client.conversations_history(channel=channel["id"])
        for file in self.get_image_files_for_history(history):
            local_filename = self.get_local_filename_for_file(
                channel, file, users[file["user"]]
            )
            resp = httpx.get(
                file["url_private"],
                headers={"Authentication": f"Bearer {self.client.token}"},
            )
            resp.raise_for_status()

            # if there's an issue with auth, slack will redirect to a login
            if "image" not in resp.headers["content-type"]:
                raise ValueError(
                    f"Couldn't download {file['url_private']} to {local_filename}"
                )

            with open(DOWNLOAD_PATH / local_filename, "wb") as img_file:
                img_file.write(resp.content)