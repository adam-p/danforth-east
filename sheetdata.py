# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
Functions and classes to be used for accessing the data stored in Google Sheets.

Google is inconsistent with terminology for "sheets" stuff. We're going to use
"sheet" or "spreadsheet" to mean the whole document/file and "worksheet" to mean the
tabs of data in a spreadsheet.

Note that nothing here is terribly robust. For example, sheet rows are gathered and then
modified or deleted based on the row number at the time of extraction. But if another
deletion happened in between, the number would be off and the wrong rows would be changed
after. This is okay for our very small user-base with very limited middle-of-the-night
deletion occurring, but isn't good enough for a real application.
"""

from __future__ import annotations
from typing import Tuple, Callable, Optional, Union, List
import itertools
import json
import logging
from googleapiclient.discovery import build
from googleapiclient.discovery_cache.base import Cache
from google.oauth2 import service_account

import config


# from https://github.com/googleapis/google-api-python-client/issues/325#issuecomment-274349841
class MemoryCache(Cache):
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content


class Row(object):
    """Represents a row from a sheet.
    Which properties are filled in depend on whether the Row was constructed in code or
    retrieved from a sheet. It makes no sense for `dict` or `sheet` to not be set, but
    `num` or `headings` could be unset.
    `num` is 1-based (although this shouldn't matter to external callers).
    """
    def __init__(self, dct: dict = {}, sheet: config.Spreadsheet = None, num: int = 0, headings: List[str] = None):
        self.dict = dct
        self.sheet = sheet
        self.num = num # 0 is invalid
        self.headings = headings

    @staticmethod
    def find(sheet: config.Spreadsheet, matcher: Callable[[dict], bool]) -> Optional[Row]:
        """Find the (first) matching row in the given sheet.
        """
        match = find_rows(sheet, matcher, 1)
        if not match:
            return None
        return match[0]

    def _to_tuple(self):
        """Convert the dict of data into a tuple, appropriate for API operations.
        """
        return _row_dict_to_tuple(
            self.sheet.spreadsheet_id,
            self.sheet.worksheet_title,
            self.dict,
            self.headings)

    def append(self):
        """Append the current row to the given sheet.
        WARNING: If you directly construct a list of new Rows -- with no `headings` set --
        and then `append()` them in a loop, you'll be incurring two network operations
        each -- one to fetch headings, and one to append. We don't do that right now, but
        one day we might need batch operation that is more efficient.
        """
        _add_row(
            self.sheet.spreadsheet_id, self.sheet.worksheet_title,
            self._to_tuple())

    def update(self):
        """Update the current row in the sheet.
        """
        if self.num <= 0:
            # We need to find the location of the row to update
            match_row = Row.find(
                self.sheet,
                lambda d: d[self.sheet.id_field().name] == self.dict[self.sheet.id_field().name])
            if not match_row:
                raise Exception('could not find own row to update')
            self.num = match_row.num

        update_rows(self.sheet, [self])


_service_account_info = json.load(open(config.SERVICE_ACCOUNT_CREDS_JSON_FILE_PATH))

def _sheets_service():
    """Get the Google Sheets service.
    """
    # Using the "default" (derived from App Engine env) credentials doesn't seem to work.
    # It results in the error "Request had insufficient authentication scopes."
    credentials = service_account.Credentials.from_service_account_info(_service_account_info)
    return build('sheets', 'v4', credentials=credentials, cache=MemoryCache()).spreadsheets()


def _drive_service():
    """Get the Google Drive service.
    """
    credentials = service_account.Credentials.from_service_account_info(_service_account_info)
    return build('drive', 'v3', credentials=credentials, cache=MemoryCache())


def _add_row(spreadsheet_id: str, worksheet_title: str, row_values: List):
    """Add a row to the given sheet.
    """
    body = {
        'values': [row_values]
    }
    ss = _sheets_service()
    ss.values().append(spreadsheetId=spreadsheet_id,
                       range=worksheet_title,
                       body=body,
                       insertDataOption='INSERT_ROWS',
                       valueInputOption='USER_ENTERED').execute()


def update_rows(sheet: config.Spreadsheet, rows: List[Row]):
    """Update all of the given rows in the sheet.
    Note that the `num` property of the rows must be populated (so these row objects
    should have retrieved from the sheet).
    """
    if not rows:
        return

    body = { 'valueInputOption': 'USER_ENTERED', 'data': [] }
    for r in rows:
        if r.num <= 0:
            raise ValueError('row.num not populated')
        elif r.num == 1:
            # This is an attempt to overwrite the headings. Disallow.
            msg = f'sheetdata.update_rows: attempt to overwrite headings prevented; {r}'
            logging.error(msg)
            raise ValueError(msg)

        logging.debug('sheetdata.update_rows: %s::%d', type(sheet.fields), r.num)

        body['data'].append({
                'range': f'A{r.num}',
                'majorDimension': 'ROWS',
                'values': [r._to_tuple()],
            })

    ss = _sheets_service()
    ss.values().batchUpdate(spreadsheetId=sheet.spreadsheet_id, body=body).execute()


def delete_rows(sheet: config.Spreadsheet, row_nums: List[int]):
    """Deletes rows at the given numbers from the sheet.
    Note that row numbers are 1-based.
    """
    if not row_nums:
        return

    # To account for rows shifting as they're deleted, we have to do it from the bottom up
    row_nums.sort(reverse=True)

    body = { 'requests': [] }
    for n in row_nums:
        row_idx = n - 1 # deleteDimension uses 0-based rows
        body['requests'].append({
                'deleteDimension': {
                    'range': {
                        'dimension': 'ROWS',
                        'sheetId': sheet.worksheet_id,
                        'startIndex': row_idx,
                        'endIndex': row_idx+1
                    }
                }
            })

    ss = _sheets_service()
    ss.batchUpdate(spreadsheetId=sheet.spreadsheet_id, body=body).execute()


def _get_sheet_data(spreadsheet_id: str, worksheet_title: str, row_num_start: int = None, row_num_end: int = None) -> List[List]:
    """Get data in the sheet, bounded by the given start and end (which are 1-based and inclusive).
    If the start and end are None, the entire sheet will be retrieved (including headings).
    """
    rng = worksheet_title
    if row_num_start:
        rng += f'!{row_num_start}'
    if row_num_end:
        if not row_num_start:
            rng += f'!1'
        rng += f':{row_num_end}'

    ss = _sheets_service()
    result = ss.values().get(spreadsheetId=spreadsheet_id,
                             range=rng,
                             dateTimeRenderOption='FORMATTED_STRING',
                             majorDimension='ROWS',
                             valueRenderOption='UNFORMATTED_VALUE').execute()
    if not result.get('values'):
        # This can happen if the spreadsheet is empty
        logging.error('_get_sheet_data: not values present')
        return []
    return result['values']


def find_rows(sheet: config.Spreadsheet, matcher: Callable[[dict], bool], max_matches: int = None) -> List[Row]:
    """Find matching rows in the sheet. The number of rows returned will be up to `max_matches`,
    unless it is None, in which case all matches will be turned.
    If matcher is None, all rows will be returned.
    """
    tuples = _get_sheet_data(sheet.spreadsheet_id, sheet.worksheet_title)
    if len(tuples) == 0:
        # There aren't any headings in the spreadsheet. Game over.
        msg = f'spreadsheet is missing headings: {sheet.spreadsheet_id}::{sheet.worksheet_title}'
        logging.critical(msg)
        raise Exception(msg)

    headings = tuples[0]
    matches = []
    for i in range(1, len(tuples)):
        row_num = i + 1 # 1-based
        t = tuples[i]
        row_dict = _row_tuple_to_dict(sheet.spreadsheet_id, sheet.worksheet_title, t, headings)
        if not matcher or matcher(row_dict):
            matches.append(Row(row_dict, sheet=sheet, num=row_num, headings=headings))
            if max_matches and len(matches) >= max_matches:
                break

    logging.debug(f'sheetdata.find_rows: {type(sheet.fields)}: matches len is {len(matches)} of {max_matches}')

    return matches


def copy_drive_file(file_id: str, new_title: str, new_description: str):
    """Copy a Google Drive file, with a new title and description.
    """
    drive = _drive_service()

    # Make the copy
    request_body = { 'name': new_title, 'description': new_description }
    new_file_info = drive.files().copy(fileId=file_id, body=request_body).execute()

    # The service account will be the owner of the new file, so we need to transfer it to
    # the owner of the original file.
    orig_file_info = drive.files().get(fileId=file_id, fields="owners").execute()
    orig_owner_permission_id = orig_file_info['owners'][0]['permissionId']
    drive.permissions().update(
        fileId=new_file_info['id'],
        permissionId=orig_owner_permission_id,
        transferOwnership=True,
        body={'role': 'owner'}).execute()


def get_first_sheet_properties(spreadsheet_id: str) -> dict:
    """Returns the properties dict of the first sheet in the spreadsheet.
    This includes 'title', for use in A1 range notation, and 'id'.
    Throws exception if not found.
    """
    ss = _sheets_service()
    result = ss.get(spreadsheetId=spreadsheet_id).execute()
    return result['sheets'][0]['properties']


def _get_sheet_headings(spreadsheet_id: str, worksheet_title: str) -> List:
    """Get the headings from the given sheet.
    """
    return _get_sheet_data(spreadsheet_id, worksheet_title, 1, 1)[0]


def _row_dict_to_tuple(spreadsheet_id: str, worksheet_title: str, row_dict: dict, headings: List) -> List:
    """Convert a dict with a row of sheet data into a tuple suitable for API operations.
    If none, `headings` will be fetched, but results in an additional network operation.
    """
    if not headings:
        headings = _get_sheet_headings(spreadsheet_id, worksheet_title)
    return [row_dict.get(h) for h in headings]


def _row_tuple_to_dict(spreadsheet_id: str, worksheet_title: str, row_tuple: List, headings: List) -> dict:
    """Convert a tuple of sheet data into a dict.
    If none, `headings` will be fetched, but results in an additional network operation.
    """
    if not headings:
        headings = _get_sheet_headings(spreadsheet_id, worksheet_title)
    return dict(itertools.zip_longest(headings, row_tuple))
