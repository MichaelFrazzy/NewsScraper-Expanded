import sys
import json
import logging
from time import mktime
from datetime import datetime
import feedparser as fp
import newspaper
from newspaper import Article

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('newsscraper.log'),
        logging.StreamHandler()
    ]
)

data = {}
data["newspapers"] = {}

def validate_rss(url):
    """Validate RSS feed before attempting to scrape."""
    try:
        feed = fp.parse(url)
        return len(feed.entries) > 0
    except Exception as err:
        logging.warning(f"Invalid RSS feed: {url}, Error: {err}")
        return False
        

def parse_config(fname):
    """Load and validate the JSON configuration file."""
    try:
        with open(fname, "r") as data_file:
            cfg = json.load(data_file)

        for company, value in cfg.items():
            if "link" not in value:
                raise ValueError(f"Configuration item {company} missing obligatory 'link'.")
            if "rss" in value and not validate_rss(value["rss"]):
                logging.warning(f"Invalid RSS feed for {company}, falling back to direct scraping")
                del value["rss"]

        return cfg
    except Exception as err:
        logging.error(f"Error parsing config file: {err}")
        raise

def _handle_rss(company, value, count, limit):
    """If a RSS link is provided in the JSON file, this will be the first
    choice.

    If you do not want to scrape from the RSS-feed, leave the RSS
    attr empty in the JSON file.
    """

    fpd = fp.parse(value["rss"])
    logging.info(f"Downloading articles from {company}")
    news_paper = {"rss": value["rss"], "link": value["link"], "articles": []}
    for entry in fpd.entries:
        # Check if publish date is provided, if no the article is skipped
        if not hasattr(entry, "published"):
            continue
        if count > limit:
            break
            
        article = {}
        article["link"] = entry.link
        date = entry.published_parsed
        article["published"] = datetime.fromtimestamp(mktime(date)).isoformat()
        
        try:
            content = Article(entry.link,
                keep_article_html=True,
                fetch_images=False,
                MAX_TEXT=None  # Limit text to 100,000 characters
            )
            content.download()
            content.parse()
            # If the download fails (ex. 404) the, script will continue downloading the next article
        
        except Exception as err:
            logging.error(f"Error downloading article from {company}: {err}")
            logging.info("Continuing to next article...")
            continue
            
        article["title"] = content.title
        article["text"] = content.text
        news_paper["articles"].append(article)
        logging.info(f"{count} articles downloaded from {company}, url: {entry.link}")
        count = count + 1
        
    return count, news_paper


def _handle_fallback(company, value, count, limit):
    """This is the fallback method if a RSS-feed link is not provided.

    It uses the python newspaper library to extract articles.
    """
    # After 10 failed articles, the company will be skipped
    
    logging.info(f"Building site for {company}")
    paper = newspaper.build(value["link"], memoize_articles=False)
    news_paper = {"link": value["link"], "articles": []}
    none_type_count = 0
    
    for content in paper.articles:
        if count > limit:
            break
        try:
            content.download()
            content.parse()
        except Exception as err:
            logging.error(f"Error downloading article from {company}: {err}")
            logging.info("Continuing to next article...")
            continue
            
        if content.publish_date is None:
            logging.warning(f"{count} Article has date of type None...")
            none_type_count = none_type_count + 1
            if none_type_count > 10:
                logging.warning(f"Too many noneType dates for {company}, aborting...")
                none_type_count = 0
                break
            count = count + 1
            continue
            
        article = {
            "title": content.title,
            "text": content.text,
            "link": content.url,
            "published": content.publish_date.isoformat(),
        }
        news_paper["articles"].append(article)
        logging.info(f"{count} articles downloaded from {company} using newspaper, url: {content.url}")
        count = count + 1
        none_type_count = 0
        
    return count, news_paper

def run(config, limit=4):
    """Execute the scraping process for all configured news sources."""
    failed_sites = []
    
    for company, value in config.items():
        try:
            count = 1
            if "rss" in value:
                count, news_paper = _handle_rss(company, value, count, limit)
            else:
                count, news_paper = _handle_fallback(company, value, count, limit)
            data["newspapers"][company] = news_paper
        except Exception as err:
            logging.error(f"Failed to process {company}: {err}")
            failed_sites.append(company)

    current_date = datetime.now().strftime("%m_%d_%Y_%H_%M")
    output_filename = f"scraped_articles_{current_date}.json"
    
    try:
        with open(output_filename, "w") as outfile:
            json.dump(data, outfile, indent=2)
        logging.info(f"Successfully saved to {output_filename}")
    except Exception as err:
        logging.error(f"Error saving output file: {err}")
        raise

    if failed_sites:
        logging.warning(f"Failed to process these sites: {', '.join(failed_sites)}")

# Scraper function - requires a command line argument containing json

def main():

    args = list(sys.argv)

    if len(args) < 2:
        logging.error("Usage: newsscraper.py NewsPapers.json")
        sys.exit("Usage: newsscraper.py NewsPapers.json")

    limit = 4
    if "--limit" in args:
        idx = args.index("--limit")
        limit = int(args[idx + 1])
        args = [args[i] for i in range(len(args)) if i not in (idx, idx + 1)]

    fname = args[1]
    try:
        config = parse_config(fname)
    except Exception as err:
        sys.exit(err)
    run(config, limit=limit)


if __name__ == "__main__":
    main()
