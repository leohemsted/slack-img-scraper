import asyncio
from datetime import datetime

import click

from slack_img_scraper.slack_channels import SlackChannelJoiner
from slack_img_scraper.slack_files import SlackImageDownloader as FileDownloader


@click.group()
def cli():
    pass


@cli.command("by-file")
def download_historical_images_by_file():
    downloader = FileDownloader()
    asyncio.run(downloader.download_images())


@cli.command("join-channels")
def join_channels():
    channel_joiner = SlackChannelJoiner()
    channel_joiner.join_channels()


if __name__ == "__main__":
    cli()
