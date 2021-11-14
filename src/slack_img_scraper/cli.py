import logging
from datetime import datetime

import click

from slack_img_scraper.slack import SlackImageDownloader


@click.command()
@click.option("-f", "--from-date", type=click.DateTime(), default=datetime.min)
@click.option("-t", "--to-date", type=click.DateTime(), default=datetime.utcnow())
def download_historical_images(from_date, to_date):
    downloader = SlackImageDownloader()
    downloader.download_images()


if __name__ == "__main__":
    download_historical_images()
