slack-img-scraper
=================

Downloads all files from a slack instance. Will only download Downloads to an `./output` directory. filenames in the format `channel-name/yyyy-mm-dd-username-file_id.extension`.

```
poetry run python src/slack_img_scraper/cli.py by-file
```


Runs will update `.last-run-ts.txt` to prevent re-downloading duplicates. Will also skip if a file exists.
