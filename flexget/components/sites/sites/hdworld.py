import re

from loguru import logger
from requests import RequestException

from flexget import plugin
from flexget.components.sites.utils import normalize_scene
from flexget.entry import Entry
from flexget.event import event
from flexget.utils.parsers import MovieParser
from flexget.utils.soup import get_soup

logger = logger.bind(name='search_hdworld')


class SearchHdWorld:
    """
    Search plugin which gives results from www.hd-world.cc

    Configuration:
        - hoster: Name of the hoster as seen in the article (i.e. 'DDownload.com', 'Rapidgator.net',...)
        - search:
            - append_year: Append the entry['movie_year'] to search string
            - whitespace2dot: Replace whitespaces with dots for querying (Mission.Impossible instead of Mission Impossible)

    Example:

    .. code-block::

        search_hdworld:
            hoster: DDownload.com
            search:
                append_year: True
                whitespace2dot: True

    """

    schema = {
        'type': 'object',
        'properties': {
            'hoster': {'type': 'string'},
            'required': ['hoster'],
            'search': {
                'type': 'object',
                'properties': {
                    'append_year': {'type': 'boolean', 'default': False},
                    'whitespace2dot': {'type': 'boolean', 'default': False},
                },
                'additionalProperties': False
            },
        },
        "additionalProperties": False,
    }

    base_url = 'https://hd-world.cc/'

    @plugin.internet(logger)
    def search(self, task, entry, config):

        search_string = normalize_scene(entry['title'])
        if 'search' in config:
            if config['search'].get('append_year'):
                search_string = search_string + " " + str(entry['movie_year'])
            if config['search'].get('whitespace2dot'):
                search_string = re.sub(' +', '.', search_string)

        try:
            params = {'s': search_string}
            logger.verbose('Requesting: {} with params {}', self.base_url, params)
            page = task.requests.get(self.base_url, params=params)
            soup = get_soup(page.content)

            result_entries = self.create_entries(soup, config)
        except RequestException as e:
            logger.error('Search request failed: {}', e)
            return

        logger.verbose('{} releases found.', len(result_entries))

        return result_entries

    def create_entries(self, soup, config):
        def _imdb_url_from_links(links):
            for link in links:
                if link['href'].startswith('https://www.imdb.com'):
                    return link['href']

        def _download_url_from_links(links, hoster):
            for link in links:
                if link.contents[0].lower().strip() == hoster.lower():
                    return link['href']

        queue = []

        for article in soup.find_all('article'):
            title_link = article.find_next('a')
            title = title_link.contents[0].replace('\n', '').strip()
            url_origin = title_link['href']
            logger.verbose("Found {} [{}]".format(title, url_origin))

            parser = MovieParser()
            parser.parse(title)

            child_links = article.findChildren('a', {'target': '_blank'})

            url_imdb = _imdb_url_from_links(child_links)
            url_download = _download_url_from_links(child_links, config['hoster'])

            if url_download is not None:
                entry = Entry(title, url_download)
                entry['name'] = parser.name
                entry['year'] = parser.year
                entry['quality'] = parser.quality
                entry['origin_url'] = url_origin
                if url_imdb is not None:
                    entry['imdb_url'] = url_imdb

                queue.append(entry)
            else:
                logger.verbose("Hoster {} not found for {}", config['hoster'], title)

        return queue


@event('plugin.register')
def register_plugin():
    plugin.register(SearchHdWorld, 'search_hdworld', interfaces=['search'], api_ver=2)
