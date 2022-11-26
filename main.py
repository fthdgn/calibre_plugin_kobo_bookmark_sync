from __future__ import absolute_import, division, print_function, unicode_literals
import json
from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import info_dialog
from calibre.gui2 import error_dialog
from calibre.gui2 import question_dialog
from contextlib import closing
from PyQt5.QtWidgets import QMenu


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


def row_factory(cursor, row):
    return {k[0]: row[i] for i, k in enumerate(cursor.getdescription())}


class InterfacePlugin(InterfaceAction):
    name = 'Kobo Bookmark Sync'
    action_spec = ('Kobo Bookmark Sync', None, "Utils", None)

    def genesis(self):
        icon = get_icons('images/icon.png')

        self.menu = QMenu(self.gui)
        self.create_menu_action(self.menu, "backup",
                                "Backup", triggered=self.backup_action)
        self.create_menu_action(self.menu, "restore",
                                "Restore", triggered=self.restore_action)

        self.qaction.setMenu(self.menu)
        self.qaction.setIcon(icon)

    def backup_action(self):
        self.device_path = self.get_device_path()
        if self.device_path is None:
            return error_dialog(self.gui, 'Cannot back up bookmarks',
                                'No device is detected.', show=True)

        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            return error_dialog(self.gui, 'Cannot back up bookmarks',
                                'No books selected', show=True)
        ids = list(map(self.gui.library_view.model().id, rows))
        db = self.gui.current_db.new_api
        for book_id in ids:
            mi = db.get_metadata(book_id)
            custom_cols = db.field_metadata.custom_field_metadata()
            col = custom_cols["#bookmarks"]
            device_bookmarks = self.get_bookmarks_from_device(
                self.get_book_relative_path(book_id))
            library_bookmarks = self.get_bookmarks_from_metadata(book_id)
            merged = self.merge_bookmarks(
                device_bookmarks, library_bookmarks, mi.title)
            if merged is None:
                col['#value#'] = ""
            else:
                col['#value#'] = merged.to_json()
            mi.set_user_metadata("#bookmarks", col)
            db.set_metadata(book_id, mi)

        info_dialog(self.gui, 'Backup',
                    'Backed up the bookmarks of %d book(s)' % len(ids),
                    show=True)

    def merge_bookmarks(self, device_bookmarks, library_bookmarks, title):
        if device_bookmarks is None or device_bookmarks.bookmarks is None:
            device_bookmarks = Bookmarks([])
        if library_bookmarks is None or library_bookmarks.bookmarks is None:
            library_bookmarks = Bookmarks([])

        bookmarks = []
        for device_version in device_bookmarks.bookmarks:
            library_version = self.find_bookmark(
                library_bookmarks.bookmarks, device_version.BookmarkID)
            if library_version is None:
                bookmarks.append(device_version)
            else:
                if library_version != device_version:
                    if question_dialog(self.gui, "Update %s" % title,
                                       "This bookmark is changed, do you want to update library "
                                       "version?\nDevice:%s\n\nLibrary:%s" % (
                                           device_version.to_json(),
                                           library_version.to_json())):
                        bookmarks.append(device_version)
                    else:
                        bookmarks.append(library_version)
                else:
                    bookmarks.append(device_version)

        for library_version in library_bookmarks.bookmarks:
            device_version = self.find_bookmark(
                device_bookmarks.bookmarks, library_version.BookmarkID)
            if device_version is None:
                if not question_dialog(self.gui, "Delete %s" % title, "This bookmark is deleted from device, do you "
                                                                      "want to "
                                                                      "delete it from library "
                                                                      "?\nLibrary:%s" % (
                                                                          library_version.to_json())):
                    bookmarks.append(library_version)

        if len(bookmarks) == 0:
            return None

        return Bookmarks(bookmarks)

    def find_bookmark(self, bookmarks_list, bookmark_id):
        for b in bookmarks_list:
            if b.BookmarkID == bookmark_id:
                return b
        return None

    def restore_action(self):
        self.device_path = self.get_device_path()
        if self.device_path is None:
            return error_dialog(self.gui, 'Cannot restore bookmarks',
                                'No device is detected.', show=True)
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            return error_dialog(self.gui, 'Cannot restore bookmarks',
                                'No books selected', show=True)
        ids = list(map(self.gui.library_view.model().id, rows))
        db = self.gui.current_db.new_api
        for book_id in ids:
            self.restore_book(book_id)

        info_dialog(self.gui, 'Restore',
                    'Restored bookmarks of %d book(s)' % len(ids),
                    show=True)

    def restore_book(self, book_id):
        bookmarks = self.get_bookmarks_from_metadata(book_id)
        if bookmarks is None:
            return
        book_relative_path = self.get_book_relative_path(book_id)
        if book_relative_path is None:
            return
        for bookmark in bookmarks.bookmarks:
            self.restore_bookmark(book_relative_path, bookmark)

    def get_bookmarks_from_metadata(self, book_id):
        mi = self.gui.current_db.new_api.get_metadata(book_id)
        json_string = mi.get_user_metadata(
            '#bookmarks', make_copy=False)["#value#"]
        if json_string is None:
            return None
        return Bookmarks.from_json(json_string)

    def restore_bookmark(self, book_path, bookmark):
        with closing(self.device_database_connection(use_row_factory=True)) as connection:
            if self.is_bookmark_exists_on_device(bookmark.BookmarkID):
                return

            columns = []
            values = []

            columns.append("BookmarkID")
            values.append(bookmark.BookmarkID)

            columns.append("VolumeId")
            values.append('file:///mnt/onboard/%s' % book_path)

            columns.append("ContentID")
            values.append('/mnt/onboard/%s%s' %
                          (book_path, bookmark.ContentID))

            columns.append("StartContainerPath")
            values.append(bookmark.StartContainerPath)

            columns.append("StartContainerChildIndex")
            values.append(bookmark.StartContainerChildIndex)

            columns.append("StartOffset")
            values.append(bookmark.StartOffset)

            columns.append("EndContainerPath")
            values.append(bookmark.EndContainerPath)

            columns.append("EndContainerChildIndex")
            values.append(bookmark.EndContainerChildIndex)

            columns.append("EndOffset")
            values.append(bookmark.EndOffset)

            if bookmark.Text is not None:
                columns.append("Text")
                values.append(bookmark.Text)

            if bookmark.Annotation is not None:
                columns.append("Annotation")
                values.append(bookmark.Annotation)

            if bookmark.DateCreated is not None:
                columns.append("DateCreated")
                values.append(bookmark.DateCreated)

            columns.append("ChapterProgress")
            values.append(bookmark.ChapterProgress)

            columns.append("Hidden")
            values.append(bookmark.Hidden)

            if bookmark.Version is not None:
                columns.append("Version")
                values.append(bookmark.Version)

            if bookmark.DateModified is not None:
                columns.append("DateModified")
                values.append(bookmark.DateModified)

            if bookmark.Creator is not None:
                columns.append("Creator")
                values.append(bookmark.Creator)

            if bookmark.UUID is not None:
                columns.append("UUID")
                values.append(bookmark.UUID)

            if bookmark.UserID is not None:
                columns.append("UserID")
                values.append(bookmark.UserID)

            if bookmark.SyncTime is not None:
                columns.append("SyncTime")
                values.append(bookmark.SyncTime)

            columns.append("Published")
            values.append(bookmark.Published)

            if bookmark.ContextString is not None:
                columns.append("ContextString")
                values.append(bookmark.ContextString)

            if bookmark.Type is not None:
                columns.append("Type")
                values.append(bookmark.Type)

            question_marks = map(lambda x: '?', columns)

            shelves_query = """INSERT INTO Bookmark (%s) VALUES (%s)""" % (
                ",".join(columns), ",".join(question_marks))

            cursor = connection.cursor()
            cursor.execute(shelves_query, values)

    def is_bookmark_exists_on_device(self, bookmark_id):
        with closing(self.device_database_connection(use_row_factory=True)) as connection:
            query = """SELECT * 
                             FROM Bookmark 
                             WHERE BookmarkID = '%s'""" % bookmark_id
            cursor = connection.cursor()
            cursor.execute(query)
            for _, _ in enumerate(cursor):
                cursor.close()
                return True
            cursor.close()
        return False

    def get_book_relative_path(self, book_id):
        device_path_of_book = self.get_device_path_from_id(book_id)
        if device_path_of_book is None:
            return None
        device_path = self.device_path
        if device_path is None:
            return None
        relative_path = remove_prefix(device_path_of_book, device_path)
        return relative_path.replace('\\', '/')

    def get_device_path_from_id(self, book_id):
        paths = []
        for x in ('memory', 'card_a', 'card_b'):
            x = getattr(self.gui, x + '_view').model()
            paths += x.paths_for_db_ids(set([book_id]), as_map=True)[book_id]
        return paths[0].path if paths else None

    def get_device_path(self):
        device_path = None
        try:
            device_connected = self.gui.library_view.model().device_connected
        except:
            device_connected = None

        if device_connected is not None:
            try:
                device_path = self.gui.device_manager.connected_device._main_prefix
            except:
                device_path = None

        return device_path

    def device_database_path(self):
        return self.gui.device_manager.connected_device.normalize_path(
            self.device_path + '.kobo/KoboReader.sqlite')

    def device_database_connection(self, use_row_factory=False):
        try:
            db_connection = self.gui.device_manager.connected_device.device_database_connection()
        except AttributeError:
            import apsw
            db_connection = apsw.Connection(self.device_database_path())

        if use_row_factory:
            db_connection.setrowtrace(row_factory)

        return db_connection

    def get_bookmarks_from_device(self, book_path):
        with closing(self.device_database_connection(use_row_factory=True)) as connection:
            shelves = []
            escaped_book_path = book_path.replace(
                "_", "\\_").replace("%", "\\%")
            shelves_query = """SELECT * 
                             FROM Bookmark 
                             WHERE Hidden = 'false' AND VolumeId LIKE 'file:///mnt/onboard/%s' ESCAPE '\\' AND
                             ContentId LIKE '/mnt/onboard/%s%%' ESCAPE '\\'""" % (escaped_book_path, escaped_book_path)
            cursor = connection.cursor()
            cursor.execute(shelves_query)
            for i, row in enumerate(cursor):
                shelves.append(Bookmark(
                    row["BookmarkID"],
                    remove_prefix(row["ContentID"],
                                  "/mnt/onboard/%s" % book_path),
                    row["StartContainerPath"],
                    row["StartContainerChildIndex"],
                    row["StartOffset"],
                    row["EndContainerPath"],
                    row["EndContainerChildIndex"],
                    row["EndOffset"],
                    row["Text"],
                    row["Annotation"],
                    row["DateCreated"],
                    row["ChapterProgress"],
                    row["Hidden"],
                    row["Version"],
                    row["DateModified"],
                    row["Creator"],
                    row["UUID"],
                    row["UserID"],
                    row["SyncTime"],
                    row["Published"],
                    row["ContextString"],
                    row["Type"]
                ))
            cursor.close()
        return Bookmarks(shelves)


class Bookmarks(object):
    def __init__(self, bookmarks, *args, **kwargs):
        self.bookmarks = bookmarks

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, indent=4, ensure_ascii=False)

    @staticmethod
    def from_json(json_string):
        dictionary = json.loads(json_string)
        bookmarks = []
        for bookmark_dict in dictionary["bookmarks"]:
            bookmarks.append(Bookmark(
                bookmark_dict["BookmarkID"],
                bookmark_dict["ContentID"],
                bookmark_dict["StartContainerPath"],
                bookmark_dict["StartContainerChildIndex"],
                bookmark_dict["StartOffset"],
                bookmark_dict["EndContainerPath"],
                bookmark_dict["EndContainerChildIndex"],
                bookmark_dict["EndOffset"],
                bookmark_dict["Text"],
                bookmark_dict["Annotation"],
                bookmark_dict["DateCreated"],
                bookmark_dict["ChapterProgress"],
                bookmark_dict["Hidden"],
                bookmark_dict["Version"],
                bookmark_dict["DateModified"],
                bookmark_dict["Creator"],
                bookmark_dict["UUID"],
                bookmark_dict["UserID"],
                bookmark_dict["SyncTime"],
                bookmark_dict["Published"],
                bookmark_dict.get("ContextString", None),
                bookmark_dict.get("Type", None)
            ))
        return Bookmarks(bookmarks)


class Bookmark(object):
    def __init__(self,
                 BookmarkID,
                 ContentID,
                 StartContainerPath,
                 StartContainerChildIndex,
                 StartOffset,
                 EndContainerPath,
                 EndContainerChildIndex,
                 EndOffset,
                 Text,
                 Annotation,
                 DateCreated,
                 ChapterProgress,
                 Hidden,
                 Version,
                 DateModified,
                 Creator,
                 UUID,
                 UserID,
                 SyncTime,
                 Published,
                 ContextString,
                 Type,
                 *args, **kwargs):
        self.BookmarkID = BookmarkID
        self.ContentID = ContentID
        self.StartContainerPath = StartContainerPath
        self.StartContainerChildIndex = StartContainerChildIndex
        self.StartOffset = StartOffset
        self.EndContainerPath = EndContainerPath
        self.EndContainerChildIndex = EndContainerChildIndex
        self.EndOffset = EndOffset
        self.Text = Text
        self.Annotation = Annotation
        self.DateCreated = DateCreated
        self.ChapterProgress = ChapterProgress
        self.Hidden = Hidden
        self.Version = Version
        self.DateModified = DateModified
        self.Creator = Creator
        self.UUID = UUID
        self.Creator = Creator
        self.UserID = UserID
        self.SyncTime = SyncTime
        self.Published = Published
        self.ContextString = ContextString
        self.Type = Type

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, indent=4, ensure_ascii=False)

    def __eq__(self, other):
        return (self.BookmarkID == other.BookmarkID and
                self.ContentID == other.ContentID and
                self.StartContainerPath == other.StartContainerPath and
                self.StartContainerChildIndex == other.StartContainerChildIndex and
                self.StartOffset == other.StartOffset and
                self.EndContainerPath == other.EndContainerPath and
                self.EndContainerChildIndex == other.EndContainerChildIndex and
                self.EndOffset == other.EndOffset and
                self.Text == other.Text and
                self.Annotation == other.Annotation and
                self.DateCreated == other.DateCreated and
                self.ChapterProgress == other.ChapterProgress and
                self.Hidden == other.Hidden and
                self.Version == other.Version and
                self.DateModified == other.DateModified and
                self.Creator == other.Creator and
                self.UUID == other.UUID and
                self.Creator == other.Creator and
                self.UserID == other.UserID and
                self.SyncTime == other.SyncTime and
                self.Published == other.Published and
                self.ContextString == other.ContextString and
                self.Type == other.Type)

    def __ne__(self, other):
        return not self.__eq__(other)
