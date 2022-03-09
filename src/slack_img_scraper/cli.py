import asyncio
from datetime import datetime

import click

from slack_img_scraper.slack_channels import SlackChannelJoiner
from slack_img_scraper.slack_files import SlackImageDownloader as FileDownloader


@click.group()
def cli():
    pass


@cli.command("by-file")
@click.option("--s3", type=bool, default=False)
def download_historical_images_by_file(s3):
    downloader = FileDownloader(s3=s3)
    asyncio.run(downloader.download_images())


@cli.command("join-channels")
def join_channels():
    channel_joiner = SlackChannelJoiner()
    channel_joiner.join_channels()


if __name__ == "__main__":
    cli()
