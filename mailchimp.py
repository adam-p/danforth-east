# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2015
# MIT License : http://adampritchard.mit-license.org/
#

import base64
import httplib2
import logging
import webapp2
from webapp2_extras import json

import config


_TIMEOUT = 45
_RETRIES = 1  # disabling retries for now

_api_url_base = 'https://us11.api.mailchimp.com/3.0/lists/%s/' % config.MAILCHIMP_MEMBERS_LIST_ID

_headers = {
        'Authorization': 'Basic %s' % base64.b64encode('username:' + config.MAILCHIMP_API_KEY)
    }

_EMAIL_ADDRESS = 'email_address'
_MERGE_FIELDS = 'merge_fields'
_STATUS_FIELD = 'status'
_STATUS_VALUE = 'subscribed'


def upsert_member_info(member_dict):
    """Create or update the MailChimp record corresponding to the given Member.
    Will raise with `webapp2.abort` on error.
    """

    list_member = _find_list_member(member_dict.get(config.MEMBER_FIELDS.id.name), config.MEMBER_FIELDS)

    if list_member and \
       (config.MAILCHIMP_MEMBER_TYPE_MEMBER !=
        list_member.get(_MERGE_FIELDS, {}).get(config.MAILCHIMP_MEMBER_TYPE_MERGE_TAG)):
        # The matched list item is not a Member (vs. Volunteer)
        logging.error('upsert_member_info: wrong type: %s', member_dict)
        webapp2.abort(500, detail='bad data in sheet')

    _upsert_member_or_volunteer_info(list_member, member_dict, config.MEMBER_FIELDS, config.MAILCHIMP_MEMBER_TYPE_MEMBER)


def upsert_volunteer_info(volunteer_dict):
    """Create or update the MailChimp record corresponding to the given Volunteer.
    Will raise with `webapp2.abort` on error.
    """

    list_member = _find_list_member(volunteer_dict.get(config.VOLUNTEER_FIELDS.id.name), config.VOLUNTEER_FIELDS)

    if list_member and \
       (config.MAILCHIMP_MEMBER_TYPE_VOLUNTEER !=
        list_member.get(_MERGE_FIELDS, {}).get(config.MAILCHIMP_MEMBER_TYPE_MERGE_TAG)):
        # The matched list item is not a Volunteer (vs. Member)
        logging.error('upsert_volunteer_info: wrong type: %s', volunteer_dict)
        webapp2.abort(500, detail='bad data in sheet')

    _upsert_member_or_volunteer_info(list_member, volunteer_dict, config.VOLUNTEER_FIELDS, config.MAILCHIMP_MEMBER_TYPE_VOLUNTEER)
    return True


def _upsert_member_or_volunteer_info(list_member, sheet_dict, fields, typename):
    """Helper for `upsert_member_info()` and `upsert_volunteer_info()`.
    """
    if list_member:
        # Update existing
        _update_mailchimp_record_from_dict(list_member, sheet_dict, fields, typename)
        url = 'members/%s' % list_member['id']
        logging.info('MailChimp: updating %s from %s', list_member, sheet_dict)
        _make_request(url, 'PATCH', body=json.encode(list_member))
    else:
        # Create new
        list_member = _create_mailchimp_record_from_dict(sheet_dict, fields, typename)
        url = 'members'
        logging.info('MailChimp: creating %s from %s', list_member, sheet_dict)
        _make_request(url, 'POST', body=json.encode(list_member))


def _find_list_member(member_id, fields):
    """Returns the list member dict that matches the given email address.
    Returns None if not found.
    """
    # TODO: Some day MailChimp will add support for filtering, and this can be
    # made less brute-force.

    if not member_id:
        logging.error('mailchimp._find_list_member called with empty member_id')
        webapp2.abort(500, detail='bad data in sheet')

    # We may need to page through results to find the member we want.
    offset = 0
    while True:
        url = 'members?count=100&offset=%d' % (offset,)
        res = _make_request(url, 'GET')

        offset += len(res['members'])

        total = res['total_items']

        if offset >= total or not res['members']:
            # We paged all the way through
            break

        for member in res['members']:
            if member[_MERGE_FIELDS][fields.id.mailchimp_merge_tag] == member_id:
                return member

    return None


def _make_request(url, method, body=None):
    http = httplib2.Http(timeout=_TIMEOUT)

    attempt = 0
    while attempt < _RETRIES:
        attempt += 1

        url = _api_url_base + url
        logging.debug('%s: %s', method, url)

        response, content = http.request(url, method=method, headers=_headers, body=body)

        # This is pretty dirty. But PUT entry-creation reqs give a status
        # of 201, and basically all 20x statuses are successes, so...
        if not response['status'].startswith('20'):
            # Fail. Retry.
            logging.debug(response)
            logging.debug(content)
            continue

        return json.decode(content)

    # If we got to here, then the request failed repeatedly.
    webapp2.abort(int(response['status']), detail=content)


def _update_mailchimp_record_from_dict(mailchimp_record, sheet_dict, fields, typename):
    """Update a MailChimp list record object from a Member or Volunteer dict.
    Modifies `mailchimp_record` directly. No return value.
    """
    for field in fields:
        if not field.mailchimp_merge_tag:
            # Not a field for us to update
            continue
        mailchimp_record[_MERGE_FIELDS][field.mailchimp_merge_tag] = sheet_dict.get(field.name) or ''
    mailchimp_record[_EMAIL_ADDRESS] = sheet_dict[fields.email.name]
    mailchimp_record[_MERGE_FIELDS][config.MAILCHIMP_MEMBER_TYPE_MERGE_TAG] = typename


def _create_mailchimp_record_from_dict(sheet_dict, fields, typename):
    """Create a MailChimp list record object from a Member or Volunteer dict.
    Returns the MailChimp object.
    """
    mailchimp_record = { _MERGE_FIELDS: {} }
    _update_mailchimp_record_from_dict(mailchimp_record, sheet_dict, fields, typename)
    mailchimp_record[_STATUS_FIELD] = _STATUS_VALUE
    return mailchimp_record
