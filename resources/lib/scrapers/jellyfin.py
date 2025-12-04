# -*- coding: utf-8 -*-
from apis.jellyfin_api import JellyfinAPI
from modules import source_utils
from modules.utils import clean_file_name, normalize
from modules.settings import filter_by_name
from modules.kodi_utils import logger

class source:
	def __init__(self):
		self.scrape_provider = 'jellyfin'
		self.sources = []
		self.extensions = source_utils.supported_video_extensions()
		self.api = JellyfinAPI()
		logger('###JELLYFIN SCRAPER###', '__init__ called')

	def results(self, info):
		logger('###JELLYFIN SCRAPER###', 'results() called with info: %s' % repr(info))
		try:
			self.scrape_results = []
			filter_title = filter_by_name(self.scrape_provider)
			logger('###JELLYFIN SCRAPER###', 'filter_title=%s' % filter_title)

			# --- infos Fenlight ---
			self.media_type = info.get('media_type')
			title = info.get('title')
			year = info.get('year')
			self.season = info.get('season')
			self.episode = info.get('episode')
			aliases = source_utils.get_aliases_titles(info.get('aliases', []))
			self.folder_query = source_utils.clean_title(normalize(title))

			logger('###JELLYFIN SCRAPER###',
				   'media_type=%s title=%s year=%s season=%s episode=%s aliases=%s folder_query=%s'
				   % (self.media_type, title, year, self.season, self.episode, aliases, self.folder_query))

			# --- Recherche Jellyfin ---
			if self.media_type == 'movie':
				logger('###JELLYFIN SCRAPER###', 'calling search_movie(%s, %s)' % (title, year))
				items = self.api.search_movie(title, year)
			else:
				show_title = info.get('tvshowtitle') or title
				logger('###JELLYFIN SCRAPER###', 'calling search_episode(%s, %s, %s)' % (show_title, self.season, self.episode))
				items = self.api.search_episode(show_title, self.season, self.episode)

			if not items:
				logger('###JELLYFIN SCRAPER###', 'no items returned by Jellyfin API')
				source_utils.internal_results(self.scrape_provider, self.sources)
				return self.sources

			logger('###JELLYFIN SCRAPER###', 'Jellyfin API returned %d items' % len(items))

			sources_append = self.scrape_results.append

			for idx, item in enumerate(items):
				try:
					logger('###JELLYFIN SCRAPER###', 'processing item #%d: %s' % (idx, repr(item)))
					media = item.get("MediaSources", [])
					file_path = media[0].get("Path") if media else item.get("Path")
					name = file_path.split('/')[-1] if file_path else item.get('Name', title)
					file_name = clean_file_name(name)
					normalized = normalize(file_name)

					logger('###JELLYFIN SCRAPER###', 'raw_name=%s file_name=%s normalized=%s' %
						   (name, file_name, normalized))

					# filtre par titre comme rd_cloud
					if filter_title:
						ok_title = source_utils.check_title(
							title, normalized, aliases, year, self.season, self.episode
						)
						logger('###JELLYFIN SCRAPER###', 'check_title returned %s for "%s"' % (ok_title, normalized))
						if not ok_title:
							logger('###JELLYFIN SCRAPER###', 'skipping item because title check failed')
							continue

					item_id = item.get('Id')
					stream_url = self.api.stream_url(item_id)
					logger('###JELLYFIN SCRAPER###', 'item_id=%s stream_url=%s' % (item_id, stream_url))
					video_quality, details = source_utils.get_file_info(name_info=source_utils.release_info_format(file_name))
					media = item.get("MediaSources", [])
					size = media[0].get("Size", 0) if media else 0
					try:
						size_gb = round(float(size) / 1073741824, 2)
					except Exception as e:
						logger('###JELLYFIN SCRAPER###', 'error converting size to GB: %s' % repr(e))
						size_gb = 0

					logger('###JELLYFIN SCRAPER###', 'size_bytes=%s size_gb=%s' % (size, size_gb))

					source_item = {
						'name': normalized,
						'display_name': file_name,
						'quality': video_quality,
						'size': size_gb,
						'size_label': '%.2f GB' % size_gb,
						'extraInfo': details,
						'url_dl': stream_url,
						'id': stream_url,
						'downloads': False,
						'direct': True,
						'source': self.scrape_provider,
						'debrid': self.scrape_provider,
						'scrape_provider': self.scrape_provider,
						'direct_debrid_link': True,
						'folder_id': '',
						'cache_type': 'jellyfin',
						'jellyfin_id': item_id,  # <--- ajouté
					}

					logger('###JELLYFIN SCRAPER###', 'built source_item: %s' % repr(source_item))
					sources_append(source_item)
				except Exception as e:
					logger('###JELLYFIN SCRAPER###', 'item loop exception: %s' % repr(e))
					continue

			self.sources = self.scrape_results
			logger('###JELLYFIN SCRAPER###', 'finished building sources, total=%d' % len(self.sources))

		except Exception as e:
			logger('###JELLYFIN SCRAPER###', 'results() exception: %s' % repr(e))

		logger('###JELLYFIN SCRAPER###', 'calling internal_results with %d sources' % len(self.sources))
		source_utils.internal_results(self.scrape_provider, self.sources)
		return self.sources
