import os

from slack_sdk import WebClient


class SlackChannelJoiner:
    def __init__(self):
        self.client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        self.exclusion_list = {"gear", "marketplace"}

    def join_channels(self):
        for page in self.client.conversations_list():
            for channel in page["channels"]:
                if (
                    not channel["is_member"]
                    and channel["name"].lower() not in self.exclusion_list
                ):
                    print(f"Joining channel {channel['name']}")
                    self.client.conversations_join(channel=channel["id"])
