# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

import urllib
import httplib2
import logging
import webapp2

from google.appengine.api import urlfetch
import apiclient.discovery
from oauth2client.client import SignedJwtAssertionCredentials
import atom.core
import gdata.spreadsheets.client
import gdata.spreadsheets.data

import config


_TIMEOUT = 45
_RETRIES = 5

_WORKSHEETS_URL = gdata.spreadsheets.client.WORKSHEETS_URL
_LISTS_URL = gdata.spreadsheets.client.LISTS_URL


# Expose this class from GData
ListEntry = gdata.spreadsheets.data.ListEntry


class GoogleData(object):
    def __init__(self):
        try:
            urlfetch.set_default_fetch_deadline(_TIMEOUT)
        except:
            # urlfetch.set_default_fetch_deadline may not exist
            pass

        self._http = httplib2.Http(timeout=_TIMEOUT)

        with open(config.SERVICE_ACCOUNT_PEM_FILE_PATH, 'rb') as keyfile:
            key = keyfile.read()

        credentials = SignedJwtAssertionCredentials(
            config.SERVICE_ACCOUNT_EMAIL,
            key,
            scope=config.SCOPE)

        self._http = credentials.authorize(self._http)

        self._headers = {'Content-type': 'application/atom+xml',}

        self._drive_service = None


    #
    # Worksheets operations
    #

    def get_worksheets(self, spreadsheet_key):
        """Returns a list of entries of the worksheets for this spreadsheet.
        """

        url = _WORKSHEETS_URL % spreadsheet_key
        response = self._make_request(url, 'GET')
        parsed_response = atom.core.parse(response,
                                          gdata.spreadsheets.data.WorksheetsFeed)

        return parsed_response.entry


    #
    # Drive operations
    #

    def get_drive_service(self):
        """Just returns the Drive Service object, allowing direct use of it.
        Exposing this is a bit of cop-out.
        """

        if not self._drive_service:
            self._drive_service = apiclient.discovery.build('drive', 'v2',
                                                            http=self._http)

        return self._drive_service


    #
    # Spreadsheets List Feed operations
    #

    def get_list_entries(self, spreadsheet_key, worksheet_key,
                         query=None, order_by=None, reverse=False):
        """Get list entries (rows) for the given worksheet, with optional
        filtering and sorting.
        For detailed info, including valid query and order_by values, see the
        GData lib source and official API docs:
        https://code.google.com/p/gdata-python-client/source/browse/src/gdata/spreadsheets/client.py#548
        https://developers.google.com/google-apps/spreadsheets/#working_with_list-based_feeds
        """

        url = _LISTS_URL % (spreadsheet_key, worksheet_key)

        query_params = {}
        if query:
            query_params['sq'] = query
        if order_by:
            query_params['orderby'] = order_by
        if reverse:
            query_params['reverse'] = reverse

        if query_params:
            url += '?' + urllib.urlencode(query_params)

        response = self._make_request(url, 'GET')
        parsed_response = atom.core.parse(response,
                                         gdata.spreadsheets.data.ListsFeed)

        return parsed_response.entry

    def add_list_entry(self, list_entry, spreadsheet_key, worksheet_key):
        """Update the list entry in its spreadsheet with the values in the
        parameter.
        """

        req_body = list_entry.to_string()\
                             .replace('"&quot;', '\'"')\
                             .replace('&quot;"', '"\'')

        url = _LISTS_URL % (spreadsheet_key, worksheet_key)

        # This will throw on failure
        logging.debug(url)
        logging.debug(req_body)
        self._make_request(url, 'POST', body=req_body)

    def update_list_entry(self, list_entry):
        """Update the list entry in its spreadsheet with the values in the
        parameter.
        """

        req_body = list_entry.to_string()\
                             .replace('"&quot;', '\'"')\
                             .replace('&quot;"', '"\'')

        url = list_entry.get_edit_link().href

        # This will throw on failure
        self._make_request(url, 'PUT', body=req_body)

    def delete_list_entry(self, list_entry):
        """Delete the list entry from its spreadsheet.
        """

        headers = self._headers.copy()

        # This will cause the request to fail if the entry has been changed since
        # it was retrieved. This is bad, since, we don't have retries, but...
        # probably the best choice.
        # UPDATE: This doesn't seem to do anything at all. See:
        # http://stackoverflow.com/questions/24127369/google-spreadsheet-api-if-match-does-not-take-affect
        # https://groups.google.com/forum/#!topic/google-spreadsheets-api/8jUpojDdr3Y
        headers['If-Match'] = list_entry.etag

        url = list_entry.get_edit_link().href

        # This will throw on failure
        self._make_request(url, 'DELETE', headers=headers)

    def _make_request(self, url, method, headers=None, body=None):
        """Helper for making API requests, including retries. On success,
        returns the content of the response. On failure, throws HTTPException.
        """

        if not headers:
            headers = self._headers

        attempt = 0
        while attempt < _RETRIES:
            attempt += 1

            logging.debug('%s: %s', method, url)

            response, content = self._http.request(url, method=method,
                                                   headers=headers,
                                                   body=body)

            # This is pretty dirty. But PUT entry-creation reqs give a status
            # of 201, and basically all 20x statuses are successes, so...
            if not response['status'].startswith('20'):
                # Fail. Retry.
                logging.debug(response)
                logging.debug(content)
                continue

            return content

        # If we got to here, then the request failed repeatedly.
        webapp2.abort(int(response['status']), detail=content)
