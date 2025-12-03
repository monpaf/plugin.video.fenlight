# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.parse

from modules.kodi_utils import logger
from modules.settings import (
    jellyfin_url,
    jellyfin_username,
    jellyfin_password,
    jellyfin_library_id
)

class JellyfinAPI:
    def __init__(self):
        # URL serveur
        self.base_url = (jellyfin_url() or '').rstrip('/')
        self.username = jellyfin_username()
        self.password = jellyfin_password()

        # Normalisation du Library Id (vide = pas de filtre)
        raw_lib = jellyfin_library_id() or ''
        raw_lib = raw_lib.strip()
        if raw_lib.lower() in ('', 'none', 'null', '0', 'empty_setting'):
            raw_lib = ''
        self.library_id = raw_lib

        self.token = None
        self.user_id = None
        self.client_header = (
            'MediaBrowser Client="Fenlight", '
            'Device="Kodi", '
            'DeviceId="fenlight-jellyfin", '
            'Version="1.0.0"'
        )

        logger('###JELLYFIN API###', 'Configured base_url=%s library_id=%s' % (self.base_url, self.library_id))

    def _request(self, path, method='GET', data=None, add_token=True):
        if not self.base_url:
            logger('###JELLYFIN API###', 'Base URL not configured')
            raise ValueError('Jellyfin base URL not configured')

        url = self.base_url + path
        headers = {
            'Accept': 'application/json',
            'X-Emby-Authorization': self.client_header,
        }
        if add_token and self.token:
            headers['X-Emby-Token'] = self.token
        if data is not None:
            data = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'

        logger('###JELLYFIN API###', 'REQUEST %s %s' % (method, url))
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode('utf-8')
                if not raw:
                    return {}
                return json.loads(raw)
        except Exception as e:
            logger('###JELLYFIN API###', 'REQUEST ERROR %s %s -> %s' % (method, url, repr(e)))
            raise

    def authenticate(self):
        if self.token and self.user_id:
            return True
        try:
            if not self.username or not self.password:
                logger('###JELLYFIN API###', 'Missing username or password')
                return False

            logger('###JELLYFIN API###', 'Authenticating to %s as %s' % (self.base_url, self.username))
            payload = {'Username': self.username, 'Pw': self.password}
            result = self._request(
                '/Users/AuthenticateByName',
                method='POST',
                data=payload,
                add_token=False
            )
            self.token = result['AccessToken']
            self.user_id = result['User']['Id']
            logger('###JELLYFIN API###', 'Auth OK, user_id=%s' % self.user_id)
            return True
        except Exception as e:
            logger('###JELLYFIN API###', 'auth error: %s' % repr(e))
            return False

    def _libraries(self):
        """
        Retourne la liste des bibliothèques (Views) accessibles à l'utilisateur.
        Utilisé quand aucun Library Id n'est spécifié dans les settings.
        """
        if not self.authenticate():
            return []
        try:
            data = self._request('/Users/%s/Views' % self.user_id)
            libs = data.get('Items', [])
            logger('###JELLYFIN API###', '_libraries found %d libraries' % len(libs))
            return libs
        except Exception as e:
            logger('###JELLYFIN API###', '_libraries error: %s' % repr(e))
            return []

    def search_movie(self, title, year=None):
        logger('###JELLYFIN API###', 'search_movie title=%s year=%s' % (title, year))
        if not self.authenticate():
            logger('###JELLYFIN API###', 'search_movie: auth failed')
            return []

        base_params = {
            'IncludeItemTypes': 'Movie',
            'SearchTerm': title,
            'Recursive': 'true',
            'Limit': '50'
        }

        items = []

        # 1) Si une Library Id est configurée, on l’utilise directement
        if self.library_id:
            params = dict(base_params)
            params['ParentId'] = self.library_id
            params['Fields'] = 'MediaSources'
            qs = urllib.parse.urlencode(params)
            logger('###JELLYFIN API###', 'search_movie using ParentId=%s' % self.library_id)
            data = self._request('/Users/%s/Items?%s' % (self.user_id, qs))
            items = data.get('Items', [])
        else:
            # 2) Sinon, on cherche dans toutes les librairies de l’utilisateur
            libs = self._libraries()
            for lib in libs:
                params = dict(base_params)
                params['ParentId'] = lib['Id']
                qs = urllib.parse.urlencode(params)
                logger('###JELLYFIN API###', 'search_movie in library %s (%s)' % (lib.get('Name'), lib.get('Id')))
                data = self._request('/Users/%s/Items?%s' % (self.user_id, qs))
                lib_items = data.get('Items', [])
                logger('###JELLYFIN API###', 'search_movie library %s returned %d items' % (lib.get('Name'), len(lib_items)))
                items.extend(lib_items)

        logger('###JELLYFIN API###', 'search_movie total items before year filter=%d' % len(items))

        if year:
            items = [i for i in items if str(i.get('ProductionYear')) == str(year)]
            logger('###JELLYFIN API###', 'search_movie filtered to %d items by year' % len(items))

        return items

    def search_episode(self, show_title, season, episode):
        logger('###JELLYFIN API###', 'search_episode show=%s S%sE%s' % (show_title, season, episode))
        if not self.authenticate():
            logger('###JELLYFIN API###', 'search_episode: auth failed')
            return []

        base_params = {
            'IncludeItemTypes': 'Series',
            'SearchTerm': show_title,
            'Recursive': 'true',
            'Limit': '50',
            'Fields': 'MediaSources'
        }

        shows = []

        # 1) Avec Library Id : simple
        if self.library_id:
            params = dict(base_params)
            params['ParentId'] = self.library_id
            qs = urllib.parse.urlencode(params)
            logger('###JELLYFIN API###', 'search_episode using ParentId=%s' % (self.library_id,))
            data = self._request('/Users/%s/Items?%s' % (self.user_id, qs))
            shows = data.get('Items', [])
        else:
            # 2) Sans Library Id : on parcourt toutes les librairies
            libs = self._libraries()
            for lib in libs:
                params = dict(base_params)
                params['ParentId'] = lib['Id']
                qs = urllib.parse.urlencode(params)
                logger('###JELLYFIN API###', 'search_episode in library %s (%s)' % (lib.get('Name'), lib.get('Id')))
                data = self._request('/Users/%s/Items?%s' % (self.user_id, qs))
                lib_shows = data.get('Items', [])
                logger('###JELLYFIN API###', 'search_episode library %s returned %d shows' % (lib.get('Name'), len(lib_shows)))
                shows.extend(lib_shows)

        logger('###JELLYFIN API###', 'search_episode total shows=%d' % len(shows))
        if not shows:
            return []

        # 2) Pour CHAQUE série trouvée, récupérer les épisodes de la saison,
        # puis filtrer sur le numéro d'épisode demandé.
        all_matching_episodes = []
        for show in shows:
            show_id = show['Id']
            show_name = show.get('Name')
            logger('###JELLYFIN API###', 'search_episode fetching episodes for show %s (%s)' % (show_name, show_id))

            ep_params = {
                'UserId': self.user_id,
                'Season': season,
                'Fields': 'MediaSources'
            }
            ep_qs = urllib.parse.urlencode(ep_params)
            ep_data = self._request('/Shows/%s/Episodes?%s' % (show_id, ep_qs))
            episodes = ep_data.get('Items', [])
            logger('###JELLYFIN API###', 'search_episode season episodes for show %s: %d' % (show_name, len(episodes)))

            if not episodes:
                continue

            # filtrer sur l'épisode demandé
            matching = [
                i for i in episodes
                if str(i.get('IndexNumber')) == str(episode)
            ]
            logger('###JELLYFIN API###', 'search_episode show %s filtered to %d episodes' % (show_name, len(matching)))
            all_matching_episodes.extend(matching)

        logger('###JELLYFIN API###', 'search_episode total matching episodes across all shows=%d' % len(all_matching_episodes))
        return all_matching_episodes

    def stream_url(self, item_id):
        if not self.base_url:
            return ''
        # Kodi n’envoie pas X-Emby-Token en header, mais le token est aussi accepté en query string
        # Si besoin tu peux remplacer api_key par AccessToken ou ajuster selon ta config.
        if self.token:
            return '%s/Videos/%s/stream?static=true&api_key=%s' % (self.base_url, item_id, self.token)
        return '%s/Videos/%s/stream?static=true' % (self.base_url, item_id)
