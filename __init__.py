from __future__ import absolute_import, division, print_function, unicode_literals
from calibre.customize import InterfaceActionBase


class InterfacePluginDemo(InterfaceActionBase):
    name = 'Kobo Bookmark Sync'
    description = 'Kobo Bookmark Sync'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Fatih Doğan'
    version = (0, 0, 1)
    minimum_calibre_version = (0, 7, 53)

    actual_plugin = 'calibre_plugins.kobo_bookmark_sync.main:InterfacePlugin'
