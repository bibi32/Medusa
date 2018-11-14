# coding=utf-8
"""Request handler for configuration."""
from __future__ import unicode_literals

import inspect
import logging
import pkgutil
import platform
import sys

from medusa import (
    app,
    classes,
    common,
    config,
    db,
    logger,
    ws,
)
from medusa.common import IGNORED, Quality, SKIPPED, WANTED
from medusa.helper.mappings import NonEmptyDict
from medusa.indexers.indexer_config import get_indexer_config
from medusa.logger.adapters.style import BraceAdapter
from medusa.server.api.v2.base import (
    BaseRequestHandler,
    BooleanField,
    EnumField,
    IntegerField,
    ListField,
    MetadataStructureField,
    StringField,
    iter_nested_items,
    set_nested_value,
)

from six import iteritems, itervalues, text_type

from tornado.escape import json_decode

log = BraceAdapter(logging.getLogger(__name__))
log.logger.addHandler(logging.NullHandler())


def layout_schedule_post_processor(v):
    """Calendar layout should sort by date."""
    if v == 'calendar':
        app.COMING_EPS_SORT = 'date'


def theme_name_setter(object, name, value):
    """Hot-swap theme."""
    config.change_theme(value)


def season_folders_validator(value):
    """Validate default season folders setting."""
    return not (app.NAMING_FORCE_FOLDERS and value is False)


class ConfigHandler(BaseRequestHandler):
    """Config request handler."""

    #: resource name
    name = 'config'
    #: identifier
    identifier = ('identifier', r'\w+')
    #: path param
    path_param = ('path_param', r'\w+')
    #: allowed HTTP methods
    allowed_methods = ('GET', 'PATCH', )
    #: patch mapping
    patches = {
        'anonRedirect': StringField(app, 'ANON_REDIRECT'),
        'emby.enabled': BooleanField(app, 'USE_EMBY'),
        'torrents.authType': StringField(app, 'TORRENT_AUTH_TYPE'),
        'torrents.dir': StringField(app, 'TORRENT_DIR'),
        'torrents.enabled': BooleanField(app, 'USE_TORRENTS'),
        'torrents.highBandwidth': StringField(app, 'TORRENT_HIGH_BANDWIDTH'),
        'torrents.host': StringField(app, 'TORRENT_HOST'),
        'torrents.label': StringField(app, 'TORRENT_LABEL'),
        'torrents.labelAnime': StringField(app, 'TORRENT_LABEL_ANIME'),
        'torrents.method': StringField(app, 'TORRENT_METHOD'),
        'torrents.password': StringField(app, 'TORRENT_PASSWORD'),
        'torrents.path': BooleanField(app, 'TORRENT_PATH'),
        'torrents.paused': BooleanField(app, 'TORRENT_PAUSED'),
        'torrents.rpcurl': StringField(app, 'TORRENT_RPCURL'),
        'torrents.seedLocation': StringField(app, 'TORRENT_SEED_LOCATION'),
        'torrents.seedTime': StringField(app, 'TORRENT_SEED_TIME'),
        'torrents.username': StringField(app, 'TORRENT_USERNAME'),
        'torrents.verifySSL': BooleanField(app, 'TORRENT_VERIFY_CERT'),
        'nzb.enabled': BooleanField(app, 'USE_NZBS'),
        'nzb.dir': StringField(app, 'NZB_DIR'),
        'nzb.method': StringField(app, 'NZB_METHOD'),
        'nzb.nzbget.category': StringField(app, 'NZBGET_CATEGORY'),
        'nzb.nzbget.categoryAnime': StringField(app, 'NZBGET_CATEGORY_ANIME'),
        'nzb.nzbget.categoryAnimeBacklog': StringField(app, 'NZBGET_CATEGORY_ANIME_BACKLOG'),
        'nzb.nzbget.categoryBacklog': StringField(app, 'NZBGET_CATEGORY_BACKLOG'),
        'nzb.nzbget.host': StringField(app, 'NZBGET_HOST'),
        'nzb.nzbget.password': StringField(app, 'NZBGET_PASSWORD'),
        'nzb.nzbget.priority': StringField(app, 'NZBGET_PRIORITY'),
        'nzb.nzbget.useHttps': BooleanField(app, 'NZBGET_USE_HTTPS'),
        'nzb.nzbget.username': StringField(app, 'NZBGET_USERNAME'),
        'nzb.sabnzbd.apiKey': StringField(app, 'SAB_APIKEY'),
        'nzb.sabnzbd.category': StringField(app, 'SAB_CATEGORY'),
        'nzb.sabnzbd.categoryAnime': StringField(app, 'SAB_CATEGORY_ANIME'),
        'nzb.sabnzbd.categoryAnimeBacklog': StringField(app, 'SAB_CATEGORY_ANIME_BACKLOG'),
        'nzb.sabnzbd.categoryBacklog': StringField(app, 'SAB_CATEGORY_BACKLOG'),
        'nzb.sabnzbd.forced': BooleanField(app, 'SAB_FORCED'),
        'nzb.sabnzbd.host': StringField(app, 'SAB_HOST'),
        'nzb.sabnzbd.password': StringField(app, 'SAB_PASSWORD'),
        'nzb.sabnzbd.username': StringField(app, 'SAB_USERNAME'),
        'selectedRootIndex': IntegerField(app, 'SELECTED_ROOT'),
        'layout.schedule': EnumField(app, 'COMING_EPS_LAYOUT', ('poster', 'banner', 'list', 'calendar'),
                                     default_value='banner', post_processor=layout_schedule_post_processor),
        'layout.history': EnumField(app, 'HISTORY_LAYOUT', ('compact', 'detailed'), default_value='detailed'),
        'layout.home': EnumField(app, 'HOME_LAYOUT', ('poster', 'small', 'banner', 'simple', 'coverflow'),
                                 default_value='poster'),
        'layout.show.allSeasons': BooleanField(app, 'DISPLAY_ALL_SEASONS'),
        'layout.show.specials': BooleanField(app, 'DISPLAY_SHOW_SPECIALS'),
        'layout.show.showListOrder': ListField(app, 'SHOW_LIST_ORDER'),
        'theme.name': StringField(app, 'THEME_NAME', setter=theme_name_setter),
        'backlogOverview.period': StringField(app, 'BACKLOG_PERIOD'),
        'backlogOverview.status': StringField(app, 'BACKLOG_STATUS'),
        'rootDirs': ListField(app, 'ROOT_DIRS'),

        'showDefaults.status': EnumField(app, 'STATUS_DEFAULT', (SKIPPED, WANTED, IGNORED), int),
        'showDefaults.statusAfter': EnumField(app, 'STATUS_DEFAULT_AFTER', (SKIPPED, WANTED, IGNORED), int),
        'showDefaults.quality': IntegerField(app, 'QUALITY_DEFAULT', validator=Quality.is_valid_combined_quality),
        'showDefaults.subtitles': BooleanField(app, 'SUBTITLES_DEFAULT', validator=lambda v: app.USE_SUBTITLES, converter=bool),
        'showDefaults.seasonFolders': BooleanField(app, 'SEASON_FOLDERS_DEFAULT', validator=season_folders_validator, converter=bool),
        'showDefaults.anime': BooleanField(app, 'ANIME_DEFAULT', converter=bool),
        'showDefaults.scene': BooleanField(app, 'SCENE_DEFAULT', converter=bool),

        'postProcessing.showDownloadDir': StringField(app, 'TV_DOWNLOAD_DIR'),
        'postProcessing.processAutomatically': BooleanField(app, 'PROCESS_AUTOMATICALLY'),
        'postProcessing.processMethod': StringField(app, 'PROCESS_METHOD'),
        'postProcessing.deleteRarContent': BooleanField(app, 'DELRARCONTENTS'),
        'postProcessing.unpack': BooleanField(app, 'UNPACK'),
        'postProcessing.noDelete': BooleanField(app, 'NO_DELETE'),
        'postProcessing.postponeIfSyncFiles': BooleanField(app, 'POSTPONE_IF_SYNC_FILES'),
        'postProcessing.autoPostprocessorFrequency': IntegerField(app, 'AUTOPOSTPROCESSOR_FREQUENCY'),
        'postProcessing.airdateEpisodes': BooleanField(app, 'AIRDATE_EPISODES'),

        'postProcessing.moveAssociatedFiles': BooleanField(app, 'MOVE_ASSOCIATED_FILES'),
        'postProcessing.allowedExtensions': ListField(app, 'ALLOWED_EXTENSIONS'),
        'postProcessing.addShowsWithoutDir': BooleanField(app, 'ADD_SHOWS_WO_DIR'),
        'postProcessing.createMissingShowDirs': BooleanField(app, 'CREATE_MISSING_SHOW_DIRS'),
        'postProcessing.renameEpisodes': BooleanField(app, 'RENAME_EPISODES'),
        'postProcessing.postponeIfNoSubs': BooleanField(app, 'POSTPONE_IF_NO_SUBS'),
        'postProcessing.nfoRename': BooleanField(app, 'NFO_RENAME'),
        'postProcessing.syncFiles': ListField(app, 'SYNC_FILES'),
        'postProcessing.fileTimestampTimezone': StringField(app, 'FILE_TIMESTAMP_TIMEZONE'),
        'postProcessing.extraScripts': ListField(app, 'EXTRA_SCRIPTS'),
        'postProcessing.extraScriptsUrl': StringField(app, 'EXTRA_SCRIPTS_URL'),
        'postProcessing.naming.pattern': StringField(app, 'NAMING_PATTERN'),
        'postProcessing.naming.enableCustomNamingAnime': BooleanField(app, 'NAMING_CUSTOM_ANIME'),
        'postProcessing.naming.enableCustomNamingSports': BooleanField(app, 'NAMING_CUSTOM_SPORTS'),
        'postProcessing.naming.enableCustomNamingAirByDate': BooleanField(app, 'NAMING_CUSTOM_ABD'),
        'postProcessing.naming.patternSports': StringField(app, 'NAMING_SPORTS_PATTERN'),
        'postProcessing.naming.patternAirByDate': StringField(app, 'NAMING_ABD_PATTERN'),
        'postProcessing.naming.patternAnime': StringField(app, 'NAMING_ANIME_PATTERN'),
        'postProcessing.naming.animeMultiEp': IntegerField(app, 'NAMING_ANIME_MULTI_EP'),
        'postProcessing.naming.animeNamingType': IntegerField(app, 'NAMING_ANIME'),
        'postProcessing.naming.multiEp': IntegerField(app, 'NAMING_MULTI_EP'),
        'postProcessing.naming.stripYear': BooleanField(app, 'NAMING_STRIP_YEAR'),

        'search.general.randomizeProviders': BooleanField(app, 'RANDOMIZE_PROVIDERS'),
        'search.general.downloadPropers': BooleanField(app, 'DOWNLOAD_PROPERS'),
        'search.general.checkPropersInterval': StringField(app, 'CHECK_PROPERS_INTERVAL'),
        # 'search.general.propersIntervalLabels': IntegerField(app, 'PROPERS_INTERVAL_LABELS'),
        'search.general.propersSearchDays': IntegerField(app, 'PROPERS_SEARCH_DAYS'),
        'search.general.backlogDays': IntegerField(app, 'BACKLOG_DAYS'),
        'search.general.backlogFrequency': IntegerField(app, 'BACKLOG_FREQUENCY'),
        'search.general.minBacklogFrequency': IntegerField(app, 'MIN_BACKLOG_FREQUENCY'),
        'search.general.dailySearchFrequency': IntegerField(app, 'DAILYSEARCH_FREQUENCY'),
        'search.general.minDailySearchFrequency': IntegerField(app, 'MIN_DAILYSEARCH_FREQUENCY'),
        'search.general.removeFromClient': BooleanField(app, 'REMOVE_FROM_CLIENT'),
        'search.general.torrentCheckerFrequency': IntegerField(app, 'TORRENT_CHECKER_FREQUENCY'),
        'search.general.minTorrentCheckerFrequency': IntegerField(app, 'MIN_TORRENT_CHECKER_FREQUENCY'),
        'search.general.usenetRetention': IntegerField(app, 'USENET_RETENTION'),
        'search.general.trackersList': ListField(app, 'TRACKERS_LIST'),
        'search.general.allowHighPriority': BooleanField(app, 'ALLOW_HIGH_PRIORITY'),
        'search.general.useFailedDownloads': BooleanField(app, 'USE_FAILED_DOWNLOADS'),
        'search.general.deleteFailed': BooleanField(app, 'DELETE_FAILED'),
        'search.general.cacheTrimming': BooleanField(app, 'CACHE_TRIMMING'),
        'search.general.maxCacheAge': IntegerField(app, 'MAX_CACHE_AGE'),

        'search.filters.ignored': ListField(app, 'IGNORE_WORDS'),
        'search.filters.undesired': ListField(app, 'UNDESIRED_WORDS'),
        'search.filters.preferred': ListField(app, 'PREFERRED_WORDS'),
        'search.filters.required': ListField(app, 'REQUIRE_WORDS'),
        'search.filters.ignoredSubsList': ListField(app, 'IGNORED_SUBS_LIST'),
        'search.filters.ignoreUnknownSubs': BooleanField(app, 'IGNORE_UND_SUBS'),

        'notifiers.kodi.enabled': BooleanField(app, 'USE_KODI'),
        'notifiers.kodi.alwaysOn': BooleanField(app, 'USE_KODI'),
        'notifiers.kodi.notifyOnSnatch': BooleanField(app, 'KODI_NOTIFY_ONSNATCH'),
        'notifiers.kodi.notifyOnDownload': BooleanField(app, 'KODI_NOTIFY_ONDOWNLOAD'),
        'notifiers.kodi.notifyOnSubtitleDownload': BooleanField(app, 'KODI_NOTIFY_ONSUBTITLEDOWNLOAD'),
        'notifiers.kodi.update.library': BooleanField(app, 'KODI_UPDATE_LIBRARY'),
        'notifiers.kodi.update.full': BooleanField(app, 'KODI_UPDATE_FULL'),
        'notifiers.kodi.update.onlyFirst': BooleanField(app, 'KODI_UPDATE_ONLYFIRST'),
        'notifiers.kodi.host': ListField(app, 'KODI_HOST'),
        'notifiers.kodi.username': StringField(app, 'KODI_USERNAME'),
        'notifiers.kodi.password': StringField(app, 'KODI_PASSWORD'),
        'notifiers.kodi.libraryCleanPending': BooleanField(app, 'KODI_LIBRARY_CLEAN_PENDING'),
        'notifiers.kodi.cleanLibrary': BooleanField(app, 'KODI_CLEAN_LIBRARY'),

        'notifiers.plex.server.enabled': BooleanField(app, 'USE_PLEX_SERVER'),
        'notifiers.plex.server.updateLibrary': BooleanField(app, 'PLEX_UPDATE_LIBRARY'),
        'notifiers.plex.server.host': ListField(app, 'PLEX_SERVER_HOST'),
        'notifiers.plex.server.https': BooleanField(app, 'PLEX_SERVER_HTTPS'),
        'notifiers.plex.server.username': StringField(app, 'PLEX_SERVER_HOST'),
        'notifiers.plex.server.password': StringField(app, 'PLEX_SERVER_HOST'),
        'notifiers.plex.server.token': StringField(app, 'PLEX_SERVER_HOST'),
        'notifiers.plex.client.enabled': BooleanField(app, 'USE_PLEX_CLIENT'),
        'notifiers.plex.client.username': StringField(app, 'PLEX_CLIENT_USERNAME'),
        'notifiers.plex.client.host': ListField(app, 'PLEX_CLIENT_HOST'),
        'notifiers.plex.client.notifyOnSnatch': BooleanField(app, 'PLEX_NOTIFY_ONSNATCH'),
        'notifiers.plex.client.notifyOnDownload': BooleanField(app, 'PLEX_NOTIFY_ONDOWNLOAD'),
        'notifiers.plex.client.notifyOnSubtitleDownload': BooleanField(app, 'PLEX_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.emby.enabled': BooleanField(app, 'USE_EMBY'),
        'notifiers.emby.host': StringField(app, 'EMBY_HOST'),
        'notifiers.emby.apiKey': StringField(app, 'EMBY_APIKEY'),

        'notifiers.nmj.enabled': BooleanField(app, 'USE_NMJ'),
        'notifiers.nmj.host': StringField(app, 'NMJ_HOST'),
        'notifiers.nmj.database': StringField(app, 'NMJ_DATABASE'),
        'notifiers.nmj.mount': StringField(app, 'NMJ_MOUNT'),

        'notifiers.nmjv2.enabled': BooleanField(app, 'USE_NMJv2'),
        'notifiers.nmjv2.host': StringField(app, 'NMJv2_HOST'),
        'notifiers.nmjv2.dbloc': StringField(app, 'NMJv2_DBLOC'),
        'notifiers.nmjv2.database': StringField(app, 'NMJv2_DATABASE'),

        'notifiers.synologyIndex.enabled': BooleanField(app, 'USE_SYNOINDEX'),

        'notifiers.synology.enabled': BooleanField(app, 'USE_SYNOLOGYNOTIFIER'),
        'notifiers.synology.notifyOnSnatch': BooleanField(app, 'SYNOLOGYNOTIFIER_NOTIFY_ONSNATCH'),
        'notifiers.synology.notifyOnDownload': BooleanField(app, 'SYNOLOGYNOTIFIER_NOTIFY_ONDOWNLOAD'),
        'notifiers.synology.notifyOnSubtitleDownload': BooleanField(app, 'SYNOLOGYNOTIFIER_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.pyTivo.enabled': BooleanField(app, 'USE_PYTIVO'),
        'notifiers.pyTivo.host': StringField(app, 'PYTIVO_HOST'),
        'notifiers.pyTivo.name': StringField(app, 'PYTIVO_TIVO_NAME'),
        'notifiers.pyTivo.shareName': StringField(app, 'PYTIVO_SHARE_NAME'),

        'notifiers.growl.enabled': BooleanField(app, 'USE_GROWL'),
        'notifiers.growl.host': StringField(app, 'GROWL_HOST'),
        'notifiers.growl.password': StringField(app, 'GROWL_PASSWORD'),
        'notifiers.growl.notifyOnSnatch': BooleanField(app, 'GROWL_NOTIFY_ONSNATCH'),
        'notifiers.growl.notifyOnDownload': BooleanField(app, 'GROWL_NOTIFY_ONDOWNLOAD'),
        'notifiers.growl.notifyOnSubtitleDownload': BooleanField(app, 'GROWL_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.prowl.enabled': BooleanField(app, 'USE_PROWL'),
        'notifiers.prowl.api': ListField(app, 'PROWL_API'),
        'notifiers.prowl.messageTitle': StringField(app, 'PROWL_MESSAGE_TITLE'),
        'notifiers.prowl.priority': IntegerField(app, 'PROWL_PRIORITY'),
        'notifiers.prowl.notifyOnSnatch': BooleanField(app, 'PROWL_NOTIFY_ONSNATCH'),
        'notifiers.prowl.notifyOnDownload': BooleanField(app, 'PROWL_NOTIFY_ONDOWNLOAD'),
        'notifiers.prowl.notifyOnSubtitleDownload': BooleanField(app, 'PROWL_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.libnotify.enabled': BooleanField(app, 'USE_LIBNOTIFY'),
        'notifiers.libnotify.notifyOnSnatch': BooleanField(app, 'LIBNOTIFY_NOTIFY_ONSNATCH'),
        'notifiers.libnotify.notifyOnDownload': BooleanField(app, 'LIBNOTIFY_NOTIFY_ONDOWNLOAD'),
        'notifiers.libnotify.notifyOnSubtitleDownload': BooleanField(app, 'LIBNOTIFY_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.pushover.enabled': BooleanField(app, 'USE_PUSHOVER'),
        'notifiers.pushover.apiKey': StringField(app, 'PUSHOVER_APIKEY'),
        'notifiers.pushover.userKey': StringField(app, 'PUSHOVER_USERKEY'),
        'notifiers.pushover.device': ListField(app, 'PUSHOVER_DEVICE'),
        'notifiers.pushover.sound': StringField(app, 'PUSHOVER_SOUND'),
        'notifiers.pushover.priority': IntegerField(app, 'PUSHOVER_PRIORITY'),
        'notifiers.pushover.notifyOnSnatch': BooleanField(app, 'PUSHOVER_NOTIFY_ONSNATCH'),
        'notifiers.pushover.notifyOnDownload': BooleanField(app, 'PUSHOVER_NOTIFY_ONDOWNLOAD'),
        'notifiers.pushover.notifyOnSubtitleDownload': BooleanField(app, 'PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.boxcar2.enabled': BooleanField(app, 'USE_BOXCAR2'),
        'notifiers.boxcar2.accessToken': StringField(app, 'BOXCAR2_ACCESSTOKEN'),
        'notifiers.boxcar2.notifyOnSnatch': BooleanField(app, 'BOXCAR2_NOTIFY_ONSNATCH'),
        'notifiers.boxcar2.notifyOnDownload': BooleanField(app, 'BOXCAR2_NOTIFY_ONDOWNLOAD'),
        'notifiers.boxcar2.notifyOnSubtitleDownload': BooleanField(app, 'BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.pushalot.enabled': BooleanField(app, 'USE_PUSHALOT'),
        'notifiers.pushalot.authToken': StringField(app, 'PUSHALOT_AUTHORIZATIONTOKEN'),
        'notifiers.pushalot.notifyOnSnatch': BooleanField(app, 'PUSHALOT_NOTIFY_ONSNATCH'),
        'notifiers.pushalot.notifyOnDownload': BooleanField(app, 'PUSHALOT_NOTIFY_ONDOWNLOAD'),
        'notifiers.pushalot.notifyOnSubtitleDownload': BooleanField(app, 'PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.pushbullet.enabled': BooleanField(app, 'USE_PUSHBULLET'),
        'notifiers.pushbullet.api': StringField(app, 'PUSHBULLET_API'),
        'notifiers.pushbullet.device': StringField(app, 'PUSHBULLET_DEVICE'),
        'notifiers.pushbullet.notifyOnSnatch': BooleanField(app, 'PUSHBULLET_NOTIFY_ONSNATCH'),
        'notifiers.pushbullet.notifyOnDownload': BooleanField(app, 'PUSHBULLET_NOTIFY_ONDOWNLOAD'),
        'notifiers.pushbullet.notifyOnSubtitleDownload': BooleanField(app, 'PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.join.enabled': BooleanField(app, 'USE_JOIN'),
        'notifiers.join.api': StringField(app, 'JOIN_API'),
        'notifiers.join.device': StringField(app, 'JOIN_DEVICE'),
        'notifiers.join.notifyOnSnatch': BooleanField(app, 'JOIN_NOTIFY_ONSNATCH'),
        'notifiers.join.notifyOnDownload': BooleanField(app, 'JOIN_NOTIFY_ONDOWNLOAD'),
        'notifiers.join.notifyOnSubtitleDownload': BooleanField(app, 'JOIN_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.freemobile.enabled': BooleanField(app, 'USE_FREEMOBILE'),
        'notifiers.freemobile.api': StringField(app, 'FREEMOBILE_APIKEY'),
        'notifiers.freemobile.id': StringField(app, 'FREEMOBILE_ID'),
        'notifiers.freemobile.notifyOnSnatch': BooleanField(app, 'FREEMOBILE_NOTIFY_ONSNATCH'),
        'notifiers.freemobile.notifyOnDownload': BooleanField(app, 'FREEMOBILE_NOTIFY_ONDOWNLOAD'),
        'notifiers.freemobile.notifyOnSubtitleDownload': BooleanField(app, 'FREEMOBILE_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.telegram.enabled': BooleanField(app, 'USE_TELEGRAM'),
        'notifiers.telegram.api': StringField(app, 'TELEGRAM_APIKEY'),
        'notifiers.telegram.id': StringField(app, 'TELEGRAM_ID'),
        'notifiers.telegram.notifyOnSnatch': BooleanField(app, 'TELEGRAM_NOTIFY_ONSNATCH'),
        'notifiers.telegram.notifyOnDownload': BooleanField(app, 'TELEGRAM_NOTIFY_ONDOWNLOAD'),
        'notifiers.telegram.notifyOnSubtitleDownload': BooleanField(app, 'TELEGRAM_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.twitter.enabled': BooleanField(app, 'USE_TWITTER'),
        'notifiers.twitter.dmto': StringField(app, 'TWITTER_DMTO'),
        'notifiers.twitter.username': StringField(app, 'TWITTER_USERNAME'),
        'notifiers.twitter.password': StringField(app, 'TWITTER_PASSWORD'),
        'notifiers.twitter.prefix': StringField(app, 'TWITTER_PREFIX'),
        'notifiers.twitter.directMessage': BooleanField(app, 'TWITTER_USEDM'),
        'notifiers.twitter.notifyOnSnatch': BooleanField(app, 'TWITTER_NOTIFY_ONSNATCH'),
        'notifiers.twitter.notifyOnDownload': BooleanField(app, 'TWITTER_NOTIFY_ONDOWNLOAD'),
        'notifiers.twitter.notifyOnSubtitleDownload': BooleanField(app, 'TWITTER_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.trakt.enabled': BooleanField(app, 'USE_TRAKT'),
        'notifiers.trakt.pinUrl': StringField(app, 'TRAKT_PIN_URL'),
        'notifiers.trakt.username': StringField(app, 'TRAKT_USERNAME'),
        'notifiers.trakt.accessToken': StringField(app, 'TRAKT_ACCESS_TOKEN'),
        'notifiers.trakt.timeout': IntegerField(app, 'TRAKT_TIMEOUT'),
        'notifiers.trakt.defaultIndexer': IntegerField(app, 'TRAKT_DEFAULT_INDEXER'),
        'notifiers.trakt.sync': BooleanField(app, 'TRAKT_SYNC'),
        'notifiers.trakt.syncRemove': BooleanField(app, 'TRAKT_SYNC_REMOVE'),
        'notifiers.trakt.syncWatchlist': BooleanField(app, 'TRAKT_SYNC_WATCHLIST'),
        'notifiers.trakt.methodAdd': IntegerField(app, 'TRAKT_METHOD_ADD'),
        'notifiers.trakt.removeWatchlist': BooleanField(app, 'TRAKT_REMOVE_WATCHLIST'),
        'notifiers.trakt.removeSerieslist': BooleanField(app, 'TRAKT_REMOVE_SERIESLIST'),
        'notifiers.trakt.removeShowFromApplication': BooleanField(app, 'TRAKT_REMOVE_SHOW_FROM_APPLICATION'),
        'notifiers.trakt.startPaused': BooleanField(app, 'TRAKT_START_PAUSED'),
        'notifiers.trakt.blacklistName': StringField(app, 'TRAKT_BLACKLIST_NAME'),

        'notifiers.email.enabled': BooleanField(app, 'USE_EMAIL'),
        'notifiers.email.host': StringField(app, 'EMAIL_HOST'),
        'notifiers.email.port': IntegerField(app, 'EMAIL_PORT'),
        'notifiers.email.from': StringField(app, 'EMAIL_FROM'),
        'notifiers.email.tls': BooleanField(app, 'EMAIL_TLS'),
        'notifiers.email.username': StringField(app, 'EMAIL_USER'),
        'notifiers.email.password': StringField(app, 'EMAIL_PASSWORD'),
        'notifiers.email.addressList': ListField(app, 'EMAIL_LIST'),
        'notifiers.email.subject': StringField(app, 'EMAIL_SUBJECT'),
        'notifiers.email.notifyOnSnatch': BooleanField(app, 'EMAIL_NOTIFY_ONSNATCH'),
        'notifiers.email.notifyOnDownload': BooleanField(app, 'EMAIL_NOTIFY_ONDOWNLOAD'),
        'notifiers.email.notifyOnSubtitleDownload': BooleanField(app, 'EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD'),

        'notifiers.slack.enabled': BooleanField(app, 'USE_SLACK'),
        'notifiers.slack.webhook': StringField(app, 'SLACK_WEBHOOK'),
        'notifiers.slack.notifyOnSnatch': BooleanField(app, 'SLACK_NOTIFY_SNATCH'),
        'notifiers.slack.notifyOnDownload': BooleanField(app, 'SLACK_NOTIFY_DOWNLOAD'),
        'notifiers.slack.notifyOnSubtitleDownload': BooleanField(app, 'SLACK_NOTIFY_SUBTITLEDOWNLOAD'),

    }

    def http_get(self, identifier, path_param=None):
        """Query general configuration.

        :param identifier:
        :param path_param:
        :type path_param: str
        """
        config_sections = DataGenerator.sections()

        if identifier and identifier not in config_sections:
            return self._not_found('Config not found')

        if not identifier:
            config_data = NonEmptyDict()

            for section in config_sections:
                config_data[section] = DataGenerator.get_data(section)

            return self._ok(data=config_data)

        config_data = DataGenerator.get_data(identifier)

        if path_param:
            if path_param not in config_data:
                return self._bad_request('{key} is a invalid path'.format(key=path_param))

            config_data = config_data[path_param]

        return self._ok(data=config_data)

    def http_patch(self, identifier, *args, **kwargs):
        """Patch general configuration."""
        if not identifier:
            return self._bad_request('Config identifier not specified')

        if identifier != 'main':
            return self._not_found('Config not found')

        data = json_decode(self.request.body)
        accepted = {}
        ignored = {}

        # Remove the metadata providers from the nested items.
        # It's ugly but I don't see a better solution for it right now.
        if data.get('metadata'):
            metadata_providers = data['metadata'].pop('metadataProviders')

            if metadata_providers:
                patch_metadata_providers = MetadataStructureField(app, 'metadata_provider_dict')
                if patch_metadata_providers and patch_metadata_providers.patch(app, metadata_providers):
                    set_nested_value(accepted, 'metadata.metadataProviders', metadata_providers)
                else:
                    set_nested_value(ignored, 'metadata.metadataProviders', metadata_providers)

        for key, value in iter_nested_items(data):
            patch_field = self.patches.get(key)
            if patch_field and patch_field.patch(app, value):
                set_nested_value(accepted, key, value)
            else:
                set_nested_value(ignored, key, value)

        if ignored:
            log.warning('Config patch ignored {items!r}', {'items': ignored})

        # Make sure to update the config file after everything is updated
        app.instance.save_config()

        # Push an update to any open Web UIs through the WebSocket
        msg = ws.Message('configUpdated', {
            'section': identifier,
            'config': DataGenerator.get_data(identifier)
        })
        msg.push()

        return self._ok(data=accepted)


class DataGenerator(object):
    """Generate the requested config data on demand."""

    @classmethod
    def sections(cls):
        """Get the available section names."""
        return [
            name[5:]
            for (name, function) in inspect.getmembers(cls, predicate=inspect.isfunction)
            if name.startswith('data_')
        ]

    @classmethod
    def get_data(cls, section):
        """Return the requested section data."""
        return getattr(cls, 'data_' + section)()

    @staticmethod
    def data_main():
        """Main."""
        section_data = NonEmptyDict()

        section_data['anonRedirect'] = app.ANON_REDIRECT
        section_data['animeSplitHome'] = bool(app.ANIME_SPLIT_HOME)
        section_data['animeSplitHomeInTabs'] = bool(app.ANIME_SPLIT_HOME_IN_TABS)
        section_data['comingEpsSort'] = app.COMING_EPS_SORT
        section_data['comingEpsDisplayPaused'] = bool(app.COMING_EPS_DISPLAY_PAUSED)
        section_data['datePreset'] = app.DATE_PRESET
        section_data['fuzzyDating'] = bool(app.FUZZY_DATING)
        section_data['themeName'] = app.THEME_NAME
        section_data['posterSortby'] = app.POSTER_SORTBY
        section_data['posterSortdir'] = app.POSTER_SORTDIR
        section_data['rootDirs'] = app.ROOT_DIRS
        section_data['sortArticle'] = bool(app.SORT_ARTICLE)
        section_data['timePreset'] = app.TIME_PRESET
        section_data['trimZero'] = bool(app.TRIM_ZERO)
        section_data['fanartBackground'] = bool(app.FANART_BACKGROUND)
        section_data['fanartBackgroundOpacity'] = float(app.FANART_BACKGROUND_OPACITY or 0)
        section_data['gitUsername'] = app.GIT_USERNAME
        section_data['branch'] = app.BRANCH
        section_data['commitHash'] = app.CUR_COMMIT_HASH
        section_data['release'] = app.APP_VERSION
        section_data['sslVersion'] = app.OPENSSL_VERSION
        section_data['pythonVersion'] = sys.version
        section_data['databaseVersion'] = NonEmptyDict()
        section_data['databaseVersion']['major'] = app.MAJOR_DB_VERSION
        section_data['databaseVersion']['minor'] = app.MINOR_DB_VERSION
        section_data['os'] = platform.platform()
        section_data['pid'] = app.PID
        section_data['locale'] = '.'.join([text_type(loc or 'Unknown') for loc in app.LOCALE])
        section_data['localUser'] = app.OS_USER or 'Unknown'
        section_data['programDir'] = app.PROG_DIR
        section_data['dataDir'] = app.DATA_DIR
        section_data['configFile'] = app.CONFIG_FILE
        section_data['dbPath'] = db.DBConnection().path
        section_data['cacheDir'] = app.CACHE_DIR
        section_data['logDir'] = app.LOG_DIR
        section_data['appArgs'] = app.MY_ARGS
        section_data['webRoot'] = app.WEB_ROOT
        section_data['runsInDocker'] = bool(app.RUNS_IN_DOCKER)
        section_data['githubUrl'] = app.GITHUB_IO_URL
        section_data['wikiUrl'] = app.WIKI_URL
        section_data['donationsUrl'] = app.DONATIONS_URL
        section_data['sourceUrl'] = app.APPLICATION_URL
        section_data['downloadUrl'] = app.DOWNLOAD_URL
        section_data['subtitlesMulti'] = bool(app.SUBTITLES_MULTI)
        section_data['namingForceFolders'] = bool(app.NAMING_FORCE_FOLDERS)
        section_data['subtitles'] = NonEmptyDict()
        section_data['subtitles']['enabled'] = bool(app.USE_SUBTITLES)
        section_data['recentShows'] = app.SHOWS_RECENT

        section_data['showDefaults'] = {}
        section_data['showDefaults']['status'] = app.STATUS_DEFAULT
        section_data['showDefaults']['statusAfter'] = app.STATUS_DEFAULT_AFTER
        section_data['showDefaults']['quality'] = app.QUALITY_DEFAULT
        section_data['showDefaults']['subtitles'] = bool(app.SUBTITLES_DEFAULT)
        section_data['showDefaults']['seasonFolders'] = bool(app.SEASON_FOLDERS_DEFAULT)
        section_data['showDefaults']['anime'] = bool(app.ANIME_DEFAULT)
        section_data['showDefaults']['scene'] = bool(app.SCENE_DEFAULT)

        section_data['news'] = NonEmptyDict()
        section_data['news']['lastRead'] = app.NEWS_LAST_READ
        section_data['news']['latest'] = app.NEWS_LATEST
        section_data['news']['unread'] = app.NEWS_UNREAD

        section_data['logs'] = NonEmptyDict()
        section_data['logs']['loggingLevels'] = {k.lower(): v for k, v in iteritems(logger.LOGGING_LEVELS)}
        section_data['logs']['numErrors'] = len(classes.ErrorViewer.errors)
        section_data['logs']['numWarnings'] = len(classes.WarningViewer.errors)

        section_data['failedDownloads'] = NonEmptyDict()
        section_data['failedDownloads']['enabled'] = bool(app.USE_FAILED_DOWNLOADS)
        section_data['failedDownloads']['deleteFailed'] = bool(app.DELETE_FAILED)

        section_data['torrents'] = NonEmptyDict()
        section_data['torrents']['authType'] = app.TORRENT_AUTH_TYPE
        section_data['torrents']['dir'] = app.TORRENT_DIR
        section_data['torrents']['enabled'] = bool(app.USE_TORRENTS)
        section_data['torrents']['highBandwidth'] = app.TORRENT_HIGH_BANDWIDTH
        section_data['torrents']['host'] = app.TORRENT_HOST
        section_data['torrents']['label'] = app.TORRENT_LABEL
        section_data['torrents']['labelAnime'] = app.TORRENT_LABEL_ANIME
        section_data['torrents']['method'] = app.TORRENT_METHOD
        section_data['torrents']['path'] = app.TORRENT_PATH
        section_data['torrents']['paused'] = bool(app.TORRENT_PAUSED)
        section_data['torrents']['rpcurl'] = app.TORRENT_RPCURL
        section_data['torrents']['seedLocation'] = app.TORRENT_SEED_LOCATION
        section_data['torrents']['seedTime'] = app.TORRENT_SEED_TIME
        section_data['torrents']['username'] = app.TORRENT_USERNAME
        section_data['torrents']['verifySSL'] = bool(app.TORRENT_VERIFY_CERT)

        section_data['nzb'] = NonEmptyDict()
        section_data['nzb']['enabled'] = bool(app.USE_NZBS)
        section_data['nzb']['dir'] = app.NZB_DIR
        section_data['nzb']['method'] = app.NZB_METHOD
        section_data['nzb']['nzbget'] = NonEmptyDict()
        section_data['nzb']['nzbget']['category'] = app.NZBGET_CATEGORY
        section_data['nzb']['nzbget']['categoryAnime'] = app.NZBGET_CATEGORY_ANIME
        section_data['nzb']['nzbget']['categoryAnimeBacklog'] = app.NZBGET_CATEGORY_ANIME_BACKLOG
        section_data['nzb']['nzbget']['categoryBacklog'] = app.NZBGET_CATEGORY_BACKLOG
        section_data['nzb']['nzbget']['host'] = app.NZBGET_HOST
        section_data['nzb']['nzbget']['priority'] = app.NZBGET_PRIORITY
        section_data['nzb']['nzbget']['useHttps'] = bool(app.NZBGET_USE_HTTPS)
        section_data['nzb']['nzbget']['username'] = app.NZBGET_USERNAME

        section_data['nzb']['sabnzbd'] = NonEmptyDict()
        section_data['nzb']['sabnzbd']['category'] = app.SAB_CATEGORY
        section_data['nzb']['sabnzbd']['categoryAnime'] = app.SAB_CATEGORY_ANIME
        section_data['nzb']['sabnzbd']['categoryAnimeBacklog'] = app.SAB_CATEGORY_ANIME_BACKLOG
        section_data['nzb']['sabnzbd']['categoryBacklog'] = app.SAB_CATEGORY_BACKLOG
        section_data['nzb']['sabnzbd']['forced'] = bool(app.SAB_FORCED)
        section_data['nzb']['sabnzbd']['host'] = app.SAB_HOST
        section_data['nzb']['sabnzbd']['username'] = app.SAB_USERNAME

        section_data['layout'] = NonEmptyDict()
        section_data['layout']['schedule'] = app.COMING_EPS_LAYOUT
        section_data['layout']['history'] = app.HISTORY_LAYOUT
        section_data['layout']['home'] = app.HOME_LAYOUT
        section_data['layout']['show'] = NonEmptyDict()
        section_data['layout']['show']['allSeasons'] = bool(app.DISPLAY_ALL_SEASONS)
        section_data['layout']['show']['specials'] = bool(app.DISPLAY_SHOW_SPECIALS)
        section_data['layout']['show']['showListOrder'] = app.SHOW_LIST_ORDER

        section_data['selectedRootIndex'] = int(app.SELECTED_ROOT) if app.SELECTED_ROOT is not None else -1  # All paths

        section_data['backlogOverview'] = NonEmptyDict()
        section_data['backlogOverview']['period'] = app.BACKLOG_PERIOD
        section_data['backlogOverview']['status'] = app.BACKLOG_STATUS

        section_data['indexers'] = NonEmptyDict()
        section_data['indexers']['config'] = get_indexer_config()

        section_data['postProcessing'] = NonEmptyDict()
        section_data['postProcessing']['naming'] = NonEmptyDict()
        section_data['postProcessing']['naming']['pattern'] = app.NAMING_PATTERN
        section_data['postProcessing']['naming']['multiEp'] = int(app.NAMING_MULTI_EP)
        section_data['postProcessing']['naming']['patternAirByDate'] = app.NAMING_ABD_PATTERN
        section_data['postProcessing']['naming']['patternSports'] = app.NAMING_SPORTS_PATTERN
        section_data['postProcessing']['naming']['patternAnime'] = app.NAMING_ANIME_PATTERN
        section_data['postProcessing']['naming']['enableCustomNamingAirByDate'] = bool(app.NAMING_CUSTOM_ABD)
        section_data['postProcessing']['naming']['enableCustomNamingSports'] = bool(app.NAMING_CUSTOM_SPORTS)
        section_data['postProcessing']['naming']['enableCustomNamingAnime'] = bool(app.NAMING_CUSTOM_ANIME)
        section_data['postProcessing']['naming']['animeMultiEp'] = int(app.NAMING_ANIME_MULTI_EP)
        section_data['postProcessing']['naming']['animeNamingType'] = int(app.NAMING_ANIME)
        section_data['postProcessing']['naming']['stripYear'] = bool(app.NAMING_STRIP_YEAR)
        section_data['postProcessing']['showDownloadDir'] = app.TV_DOWNLOAD_DIR
        section_data['postProcessing']['processAutomatically'] = bool(app.PROCESS_AUTOMATICALLY)
        section_data['postProcessing']['postponeIfSyncFiles'] = bool(app.POSTPONE_IF_SYNC_FILES)
        section_data['postProcessing']['postponeIfNoSubs'] = bool(app.POSTPONE_IF_NO_SUBS)
        section_data['postProcessing']['renameEpisodes'] = bool(app.RENAME_EPISODES)
        section_data['postProcessing']['createMissingShowDirs'] = bool(app.CREATE_MISSING_SHOW_DIRS)
        section_data['postProcessing']['addShowsWithoutDir'] = bool(app.ADD_SHOWS_WO_DIR)
        section_data['postProcessing']['moveAssociatedFiles'] = bool(app.MOVE_ASSOCIATED_FILES)
        section_data['postProcessing']['nfoRename'] = bool(app.NFO_RENAME)
        section_data['postProcessing']['airdateEpisodes'] = bool(app.AIRDATE_EPISODES)
        section_data['postProcessing']['unpack'] = bool(app.UNPACK)
        section_data['postProcessing']['deleteRarContent'] = bool(app.DELRARCONTENTS)
        section_data['postProcessing']['noDelete'] = bool(app.NO_DELETE)
        section_data['postProcessing']['processMethod'] = app.PROCESS_METHOD
        section_data['postProcessing']['reflinkAvailable'] = bool(pkgutil.find_loader('reflink'))
        section_data['postProcessing']['autoPostprocessorFrequency'] = int(app.AUTOPOSTPROCESSOR_FREQUENCY)
        section_data['postProcessing']['syncFiles'] = app.SYNC_FILES
        section_data['postProcessing']['fileTimestampTimezone'] = app.FILE_TIMESTAMP_TIMEZONE
        section_data['postProcessing']['allowedExtensions'] = app.ALLOWED_EXTENSIONS
        section_data['postProcessing']['extraScripts'] = app.EXTRA_SCRIPTS
        section_data['postProcessing']['extraScriptsUrl'] = app.EXTRA_SCRIPTS_URL
        section_data['postProcessing']['multiEpStrings'] = common.MULTI_EP_STRINGS

        return section_data

    @staticmethod
    def data_qualities():
        """Qualities."""
        section_data = NonEmptyDict()

        section_data['values'] = NonEmptyDict()
        section_data['values']['na'] = common.Quality.NA
        section_data['values']['unknown'] = common.Quality.UNKNOWN
        section_data['values']['sdtv'] = common.Quality.SDTV
        section_data['values']['sddvd'] = common.Quality.SDDVD
        section_data['values']['hdtv'] = common.Quality.HDTV
        section_data['values']['rawhdtv'] = common.Quality.RAWHDTV
        section_data['values']['fullhdtv'] = common.Quality.FULLHDTV
        section_data['values']['hdwebdl'] = common.Quality.HDWEBDL
        section_data['values']['fullhdwebdl'] = common.Quality.FULLHDWEBDL
        section_data['values']['hdbluray'] = common.Quality.HDBLURAY
        section_data['values']['fullhdbluray'] = common.Quality.FULLHDBLURAY
        section_data['values']['uhd4ktv'] = common.Quality.UHD_4K_TV
        section_data['values']['uhd4kwebdl'] = common.Quality.UHD_4K_WEBDL
        section_data['values']['uhd4kbluray'] = common.Quality.UHD_4K_BLURAY
        section_data['values']['uhd8ktv'] = common.Quality.UHD_8K_TV
        section_data['values']['uhd8kwebdl'] = common.Quality.UHD_8K_WEBDL
        section_data['values']['uhd8kbluray'] = common.Quality.UHD_8K_BLURAY

        section_data['anySets'] = NonEmptyDict()
        section_data['anySets']['anyhdtv'] = common.Quality.ANYHDTV
        section_data['anySets']['anywebdl'] = common.Quality.ANYWEBDL
        section_data['anySets']['anybluray'] = common.Quality.ANYBLURAY

        section_data['presets'] = NonEmptyDict()
        section_data['presets']['any'] = common.ANY
        section_data['presets']['sd'] = common.SD
        section_data['presets']['hd'] = common.HD
        section_data['presets']['hd720p'] = common.HD720p
        section_data['presets']['hd1080p'] = common.HD1080p
        section_data['presets']['uhd'] = common.UHD
        section_data['presets']['uhd4k'] = common.UHD_4K
        section_data['presets']['uhd8k'] = common.UHD_8K

        section_data['strings'] = NonEmptyDict()
        section_data['strings']['values'] = common.Quality.qualityStrings
        section_data['strings']['anySets'] = common.Quality.combinedQualityStrings
        section_data['strings']['presets'] = common.qualityPresetStrings
        section_data['strings']['cssClass'] = common.Quality.cssClassStrings

        return section_data

    @staticmethod
    def data_statuses():
        """Statuses."""
        section_data = NonEmptyDict()

        section_data['values'] = NonEmptyDict()
        section_data['values']['unset'] = common.UNSET
        section_data['values']['unaired'] = common.UNAIRED
        section_data['values']['snatched'] = common.SNATCHED
        section_data['values']['wanted'] = common.WANTED
        section_data['values']['downloaded'] = common.DOWNLOADED
        section_data['values']['skipped'] = common.SKIPPED
        section_data['values']['archived'] = common.ARCHIVED
        section_data['values']['ignored'] = common.IGNORED
        section_data['values']['snatchedProper'] = common.SNATCHED_PROPER
        section_data['values']['subtitled'] = common.SUBTITLED
        section_data['values']['failed'] = common.FAILED
        section_data['values']['snatchedBest'] = common.SNATCHED_BEST
        section_data['strings'] = common.statusStrings

        return section_data

    @staticmethod
    def data_metadata():
        """Metadata."""
        section_data = NonEmptyDict()

        section_data['metadataProviders'] = NonEmptyDict()

        for provider in itervalues(app.metadata_provider_dict):
            json_repr = provider.to_json()
            section_data['metadataProviders'][json_repr['id']] = json_repr

        return section_data

    @staticmethod
    def data_search():
        """Search filters."""
        section_data = NonEmptyDict()

        section_data['general'] = NonEmptyDict()
        section_data['general']['randomizeProviders'] = bool(app.RANDOMIZE_PROVIDERS)
        section_data['general']['downloadPropers'] = bool(app.DOWNLOAD_PROPERS)
        section_data['general']['checkPropersInterval'] = app.CHECK_PROPERS_INTERVAL
        # This can be moved to the frontend. No need to keep in config. The selected option is stored in CHECK_PROPERS_INTERVAL.
        # {u'45m': u'45 mins', u'15m': u'15 mins', u'4h': u'4 hours', u'daily': u'24 hours', u'90m': u'90 mins'}
        # section_data['general']['propersIntervalLabels'] = app.PROPERS_INTERVAL_LABELS
        section_data['general']['propersSearchDays'] = int(app.PROPERS_SEARCH_DAYS)
        section_data['general']['backlogDays'] = int(app.BACKLOG_DAYS)
        section_data['general']['backlogFrequency'] = int(app.BACKLOG_FREQUENCY)
        section_data['general']['minBacklogFrequency'] = int(app.MIN_BACKLOG_FREQUENCY)
        section_data['general']['dailySearchFrequency'] = int(app.DAILYSEARCH_FREQUENCY)
        section_data['general']['minDailySearchFrequency'] = int(app.MIN_DAILYSEARCH_FREQUENCY)
        section_data['general']['removeFromClient'] = bool(app.REMOVE_FROM_CLIENT)
        section_data['general']['torrentCheckerFrequency'] = int(app.TORRENT_CHECKER_FREQUENCY)
        section_data['general']['minTorrentCheckerFrequency'] = int(app.MIN_TORRENT_CHECKER_FREQUENCY)
        section_data['general']['usenetRetention'] = int(app.USENET_RETENTION)
        section_data['general']['trackersList'] = app.TRACKERS_LIST
        section_data['general']['allowHighPriority'] = bool(app.ALLOW_HIGH_PRIORITY)
        section_data['general']['useFailedDownloads'] = bool(app.USE_FAILED_DOWNLOADS)
        section_data['general']['deleteFailed'] = bool(app.DELETE_FAILED)
        section_data['general']['cacheTrimming'] = bool(app.CACHE_TRIMMING)
        section_data['general']['maxCacheAge'] = int(app.MAX_CACHE_AGE)

        section_data['filters'] = NonEmptyDict()
        section_data['filters']['ignored'] = app.IGNORE_WORDS
        section_data['filters']['undesired'] = app.UNDESIRED_WORDS
        section_data['filters']['preferred'] = app.PREFERRED_WORDS
        section_data['filters']['required'] = app.REQUIRE_WORDS
        section_data['filters']['ignoredSubsList'] = app.IGNORED_SUBS_LIST
        section_data['filters']['ignoreUnknownSubs'] = bool(app.IGNORE_UND_SUBS)

        return section_data

    @staticmethod
    def data_notifiers():
        """Notifications."""
        section_data = NonEmptyDict()

        section_data['kodi'] = NonEmptyDict()
        section_data['kodi']['enabled'] = bool(app.USE_KODI)
        section_data['kodi']['alwaysOn'] = bool(app.KODI_ALWAYS_ON)
        section_data['kodi']['notifyOnSnatch'] = bool(app.KODI_NOTIFY_ONSNATCH)
        section_data['kodi']['notifyOnDownload'] = bool(app.KODI_NOTIFY_ONDOWNLOAD)
        section_data['kodi']['notifyOnSubtitleDownload'] = bool(app.KODI_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['kodi']['update'] = NonEmptyDict()
        section_data['kodi']['update']['library'] = bool(app.KODI_UPDATE_LIBRARY)
        section_data['kodi']['update']['full'] = bool(app.KODI_UPDATE_FULL)
        section_data['kodi']['update']['onlyFirst'] = bool(app.KODI_UPDATE_ONLYFIRST)
        section_data['kodi']['host'] = app.KODI_HOST
        section_data['kodi']['username'] = app.KODI_USERNAME
        section_data['kodi']['password'] = app.KODI_PASSWORD
        section_data['kodi']['libraryCleanPending'] = bool(app.KODI_LIBRARY_CLEAN_PENDING)
        section_data['kodi']['cleanLibrary'] = bool(app.KODI_CLEAN_LIBRARY)

        section_data['plex'] = NonEmptyDict()
        section_data['plex']['server'] = NonEmptyDict()
        section_data['plex']['server']['enabled'] = bool(app.USE_PLEX_SERVER)
        section_data['plex']['server']['updateLibrary'] = bool(app.PLEX_UPDATE_LIBRARY)
        section_data['plex']['server']['host'] = app.PLEX_SERVER_HOST
        section_data['plex']['server']['https'] = bool(app.PLEX_SERVER_HTTPS)
        section_data['plex']['server']['username'] = app.PLEX_SERVER_USERNAME
        section_data['plex']['server']['password'] = app.PLEX_SERVER_PASSWORD
        section_data['plex']['server']['token'] = app.PLEX_SERVER_TOKEN
        section_data['plex']['client'] = NonEmptyDict()
        section_data['plex']['client']['enabled'] = bool(app.USE_PLEX_CLIENT)
        section_data['plex']['client']['username'] = app.PLEX_CLIENT_USERNAME
        section_data['plex']['client']['host'] = app.PLEX_CLIENT_HOST
        section_data['plex']['client']['notifyOnSnatch'] = bool(app.PLEX_NOTIFY_ONSNATCH)
        section_data['plex']['client']['notifyOnDownload'] = bool(app.PLEX_NOTIFY_ONDOWNLOAD)
        section_data['plex']['client']['notifyOnSubtitleDownload'] = bool(app.PLEX_NOTIFY_ONSUBTITLEDOWNLOAD)

        section_data['emby'] = NonEmptyDict()
        section_data['emby']['enabled'] = bool(app.USE_EMBY)
        section_data['emby']['host'] = app.EMBY_HOST
        section_data['emby']['apiKey'] = app.EMBY_APIKEY

        section_data['nmj'] = NonEmptyDict()
        section_data['nmj']['enabled'] = bool(app.USE_NMJ)
        section_data['nmj']['host'] = app.NMJ_HOST
        section_data['nmj']['database'] = app.NMJ_DATABASE
        section_data['nmj']['mount'] = app.NMJ_MOUNT

        section_data['nmjv2'] = NonEmptyDict()
        section_data['nmjv2']['enabled'] = bool(app.USE_NMJv2)
        section_data['nmjv2']['host'] = app.NMJv2_HOST
        section_data['nmjv2']['dbloc'] = app.NMJv2_DBLOC
        section_data['nmjv2']['database'] = app.NMJv2_DATABASE

        section_data['synologyIndex'] = NonEmptyDict()
        section_data['synologyIndex']['enabled'] = bool(app.USE_SYNOINDEX)

        section_data['synology'] = NonEmptyDict()
        section_data['synology']['enabled'] = bool(app.USE_SYNOLOGYNOTIFIER)
        section_data['synology']['notifyOnSnatch'] = bool(app.SYNOLOGYNOTIFIER_NOTIFY_ONSNATCH)
        section_data['synology']['notifyOnDownload'] = bool(app.SYNOLOGYNOTIFIER_NOTIFY_ONDOWNLOAD)
        section_data['synology']['notifyOnSubtitleDownload'] = bool(app.SYNOLOGYNOTIFIER_NOTIFY_ONSUBTITLEDOWNLOAD)

        section_data['pyTivo'] = NonEmptyDict()
        section_data['pyTivo']['enabled'] = bool(app.USE_PYTIVO)
        section_data['pyTivo']['host'] = app.PYTIVO_HOST
        section_data['pyTivo']['name'] = app.PYTIVO_TIVO_NAME
        section_data['pyTivo']['shareName'] = app.PYTIVO_SHARE_NAME

        section_data['growl'] = NonEmptyDict()
        section_data['growl']['enabled'] = bool(app.USE_GROWL)
        section_data['growl']['host'] = app.GROWL_HOST
        section_data['growl']['password'] = app.GROWL_PASSWORD
        section_data['growl']['notifyOnSnatch'] = bool(app.GROWL_NOTIFY_ONSNATCH)
        section_data['growl']['notifyOnDownload'] = bool(app.GROWL_NOTIFY_ONDOWNLOAD)
        section_data['growl']['notifyOnSubtitleDownload'] = bool(app.GROWL_NOTIFY_ONSUBTITLEDOWNLOAD)

        section_data['prowl'] = NonEmptyDict()
        section_data['prowl']['enabled'] = bool(app.USE_PROWL)
        section_data['prowl']['api'] = app.PROWL_API
        section_data['prowl']['messageTitle'] = app.PROWL_MESSAGE_TITLE
        section_data['prowl']['priority'] = int(app.PROWL_PRIORITY)
        section_data['prowl']['notifyOnSnatch'] = bool(app.PROWL_NOTIFY_ONSNATCH)
        section_data['prowl']['notifyOnDownload'] = bool(app.PROWL_NOTIFY_ONDOWNLOAD)
        section_data['prowl']['notifyOnSubtitleDownload'] = bool(app.PROWL_NOTIFY_ONSUBTITLEDOWNLOAD)

        section_data['libnotify'] = NonEmptyDict()
        section_data['libnotify']['enabled'] = bool(app.USE_LIBNOTIFY)
        section_data['libnotify']['notifyOnSnatch'] = bool(app.LIBNOTIFY_NOTIFY_ONSNATCH)
        section_data['libnotify']['notifyOnDownload'] = bool(app.LIBNOTIFY_NOTIFY_ONDOWNLOAD)
        section_data['libnotify']['notifyOnSubtitleDownload'] = bool(app.LIBNOTIFY_NOTIFY_ONSUBTITLEDOWNLOAD)

        section_data['pushover'] = NonEmptyDict()
        section_data['pushover']['enabled'] = bool(app.USE_PUSHOVER)
        section_data['pushover']['apiKey'] = app.PUSHOVER_APIKEY
        section_data['pushover']['userKey'] = app.PUSHOVER_USERKEY
        section_data['pushover']['device'] = app.PUSHOVER_DEVICE
        section_data['pushover']['sound'] = app.PUSHOVER_SOUND
        section_data['pushover']['priority'] = int(app.PUSHOVER_PRIORITY)
        section_data['pushover']['notifyOnSnatch'] = bool(app.PUSHOVER_NOTIFY_ONSNATCH)
        section_data['pushover']['notifyOnDownload'] = bool(app.PUSHOVER_NOTIFY_ONDOWNLOAD)
        section_data['pushover']['notifyOnSubtitleDownload'] = bool(app.PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD)

        section_data['boxcar2'] = NonEmptyDict()
        section_data['boxcar2']['enabled'] = bool(app.USE_BOXCAR2)
        section_data['boxcar2']['notifyOnSnatch'] = bool(app.BOXCAR2_NOTIFY_ONSNATCH)
        section_data['boxcar2']['notifyOnDownload'] = bool(app.BOXCAR2_NOTIFY_ONDOWNLOAD)
        section_data['boxcar2']['notifyOnSubtitleDownload'] = bool(app.BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['boxcar2']['accessToken'] = app.BOXCAR2_ACCESSTOKEN

        section_data['pushalot'] = NonEmptyDict()
        section_data['pushalot']['enabled'] = bool(app.USE_PUSHALOT)
        section_data['pushalot']['notifyOnSnatch'] = bool(app.PUSHALOT_NOTIFY_ONSNATCH)
        section_data['pushalot']['notifyOnDownload'] = bool(app.PUSHALOT_NOTIFY_ONDOWNLOAD)
        section_data['pushalot']['notifyOnSubtitleDownload'] = bool(app.PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['pushalot']['authToken'] = app.PUSHALOT_AUTHORIZATIONTOKEN

        section_data['pushbullet'] = NonEmptyDict()
        section_data['pushbullet']['enabled'] = bool(app.USE_PUSHBULLET)
        section_data['pushbullet']['notifyOnSnatch'] = bool(app.PUSHBULLET_NOTIFY_ONSNATCH)
        section_data['pushbullet']['notifyOnDownload'] = bool(app.PUSHBULLET_NOTIFY_ONDOWNLOAD)
        section_data['pushbullet']['notifyOnSubtitleDownload'] = bool(app.PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['pushbullet']['api'] = app.PUSHBULLET_API
        section_data['pushbullet']['device'] = app.PUSHBULLET_DEVICE

        section_data['join'] = NonEmptyDict()
        section_data['join']['enabled'] = bool(app.USE_JOIN)
        section_data['join']['notifyOnSnatch'] = bool(app.JOIN_NOTIFY_ONSNATCH)
        section_data['join']['notifyOnDownload'] = bool(app.JOIN_NOTIFY_ONDOWNLOAD)
        section_data['join']['notifyOnSubtitleDownload'] = bool(app.JOIN_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['join']['api'] = app.JOIN_API
        section_data['join']['device'] = app.JOIN_DEVICE

        section_data['freemobile'] = NonEmptyDict()
        section_data['freemobile']['enabled'] = bool(app.USE_FREEMOBILE)
        section_data['freemobile']['notifyOnSnatch'] = bool(app.FREEMOBILE_NOTIFY_ONSNATCH)
        section_data['freemobile']['notifyOnDownload'] = bool(app.FREEMOBILE_NOTIFY_ONDOWNLOAD)
        section_data['freemobile']['notifyOnSubtitleDownload'] = bool(app.FREEMOBILE_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['freemobile']['api'] = app.FREEMOBILE_APIKEY
        section_data['freemobile']['id'] = app.FREEMOBILE_ID

        section_data['telegram'] = NonEmptyDict()
        section_data['telegram']['enabled'] = bool(app.USE_TELEGRAM)
        section_data['telegram']['notifyOnSnatch'] = bool(app.TELEGRAM_NOTIFY_ONSNATCH)
        section_data['telegram']['notifyOnDownload'] = bool(app.TELEGRAM_NOTIFY_ONDOWNLOAD)
        section_data['telegram']['notifyOnSubtitleDownload'] = bool(app.TELEGRAM_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['telegram']['api'] = app.TELEGRAM_APIKEY
        section_data['telegram']['id'] = app.TELEGRAM_ID

        section_data['twitter'] = NonEmptyDict()
        section_data['twitter']['enabled'] = bool(app.USE_TWITTER)
        section_data['twitter']['notifyOnSnatch'] = bool(app.TWITTER_NOTIFY_ONSNATCH)
        section_data['twitter']['notifyOnDownload'] = bool(app.TWITTER_NOTIFY_ONDOWNLOAD)
        section_data['twitter']['notifyOnSubtitleDownload'] = bool(app.TWITTER_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['twitter']['dmto'] = app.TWITTER_DMTO
        section_data['twitter']['username'] = app.TWITTER_USERNAME
        section_data['twitter']['password'] = app.TWITTER_PASSWORD
        section_data['twitter']['prefix'] = app.TWITTER_PREFIX
        section_data['twitter']['directMessage'] = bool(app.TWITTER_USEDM)

        section_data['trakt'] = NonEmptyDict()
        section_data['trakt']['enabled'] = bool(app.USE_TRAKT)
        section_data['trakt']['pinUrl'] = app.TRAKT_PIN_URL
        section_data['trakt']['username'] = app.TRAKT_USERNAME
        section_data['trakt']['accessToken'] = app.TRAKT_ACCESS_TOKEN
        section_data['trakt']['timeout'] = int(app.TRAKT_TIMEOUT)
        section_data['trakt']['defaultIndexer'] = int(app.TRAKT_DEFAULT_INDEXER)
        section_data['trakt']['sync'] = bool(app.TRAKT_SYNC)
        section_data['trakt']['syncRemove'] = bool(app.TRAKT_SYNC_REMOVE)
        section_data['trakt']['syncWatchlist'] = bool(app.TRAKT_SYNC_WATCHLIST)
        section_data['trakt']['methodAdd'] = int(app.TRAKT_METHOD_ADD)
        section_data['trakt']['removeWatchlist'] = bool(app.TRAKT_REMOVE_WATCHLIST)
        section_data['trakt']['removeSerieslist'] = bool(app.TRAKT_REMOVE_SERIESLIST)
        section_data['trakt']['removeShowFromApplication'] = bool(app.TRAKT_REMOVE_SHOW_FROM_APPLICATION)
        section_data['trakt']['startPaused'] = bool(app.TRAKT_START_PAUSED)
        section_data['trakt']['blacklistName'] = app.TRAKT_BLACKLIST_NAME

        section_data['email'] = NonEmptyDict()
        section_data['email']['enabled'] = bool(app.USE_EMAIL)
        section_data['email']['notifyOnSnatch'] = bool(app.EMAIL_NOTIFY_ONSNATCH)
        section_data['email']['notifyOnDownload'] = bool(app.EMAIL_NOTIFY_ONDOWNLOAD)
        section_data['email']['notifyOnSubtitleDownload'] = bool(app.EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD)
        section_data['email']['host'] = app.EMAIL_HOST
        section_data['email']['port'] = app.EMAIL_PORT
        section_data['email']['from'] = app.EMAIL_FROM
        section_data['email']['tls'] = bool(app.EMAIL_TLS)
        section_data['email']['username'] = app.EMAIL_USER
        section_data['email']['password'] = app.EMAIL_PASSWORD
        section_data['email']['addressList'] = app.EMAIL_LIST
        section_data['email']['subject'] = app.EMAIL_SUBJECT

        section_data['slack'] = NonEmptyDict()
        section_data['slack']['enabled'] = bool(app.USE_SLACK)
        section_data['slack']['notifyOnSnatch'] = bool(app.SLACK_NOTIFY_SNATCH)
        section_data['slack']['notifyOnDownload'] = bool(app.SLACK_NOTIFY_DOWNLOAD)
        section_data['slack']['notifyOnSubtitleDownload'] = bool(app.SLACK_NOTIFY_SUBTITLEDOWNLOAD)
        section_data['slack']['webhook'] = app.SLACK_WEBHOOK

        return section_data
