# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

import logging
import uuid
import datetime

import httplib2
import webapp2
import html2text
import dateutil

from apiclient import errors
from apiclient.discovery import build
from oauth2client.client import SignedJwtAssertionCredentials
from gdata.spreadsheets.client import SpreadsheetsClient
from gdata.gauth import OAuth2TokenFromCredentials
from gdata.spreadsheets.data import ListEntry
from gdata.spreadsheets.client import ListQuery
from google.appengine.api import mail
from google.appengine.api import taskqueue

import config
import utils
import helpers


_gdata_client = None
_drive_service = None
_http = None


def get_google_service_clients():
    """Returns (gdata_client, drive_service, httplib2_instance).
    """

    # Cache the services if we've already created them
    global _gdata_client, _drive_service, _http
    if _gdata_client and _drive_service and _http:
        return (_gdata_client, _drive_service, _http)


    keyfile = open(config.SERVICE_ACCOUNT_PEM_FILE_PATH, 'rb')
    key = keyfile.read()
    keyfile.close()

    credentials = SignedJwtAssertionCredentials(config.SERVICE_ACCOUNT_EMAIL,
                                                key,
                                                scope=config.SCOPE)
    token = OAuth2TokenFromCredentials(credentials)

    _gdata_client = SpreadsheetsClient()
    token.authorize(_gdata_client)

    _http = httplib2.Http()
    _http = credentials.authorize(_http)
    _drive_service = build('drive', 'v2', http=_http)

    return _gdata_client, _drive_service, _http


def is_user_authorized(user):
    """Takes an authenticated user and return True if that user is allowed to
    access this service, False otherwise.
    """

    # Check if this user (i.e., email) is already authorized
    querystring = '%s=="%s"' % (config.AUTHORIZED_FIELDS.email.name,
                                user.email())
    auth_user = _get_single_list_entry(querystring,
                                       spreadsheet_key=config.AUTHORIZED_SPREADSHEET_KEY,
                                       worksheet_key=config.AUTHORIZED_WORKSHEET_KEY)
    if auth_user:
        return True

    return False


def member_dict_from_request(request, actor, join_or_renew):
    """Creates and returns a dict of member info from the request.
    new_or_renew should be "join" if this is (or expected to be) for a new
    member, or "renew" for a member being renewed.
    """

    logging.info('member_dict_from_request')
    logging.info(request.params.items())

    # Make sure the user/form/request isn't trying to mess with fields that it
    # shouldn't be.
    for name, field in config.MEMBER_FIELDS._asdict().items():
        if not field.form_field and request.POST.get(name) is not None:
            # This causes the request processing to stop
            webapp2.abort(400, detail='invalid field')

    member = config.validate_member(request.POST)

    if not member:
        # This causes the request processing to stop
        webapp2.abort(400, detail='invalid input')

    # We didn't validate the geoposition above, so do it now
    geoposition = request.POST.get('geoposition', '')  # TODO: don't hardcode field name
    geoposition_required = config.MEMBER_FIELDS.joined_latlong.required \
                            if join_or_renew == 'join' else \
                            config.MEMBER_FIELDS.renewed_latlong.required
    if not utils.latlong_validator(geoposition, geoposition_required):
        webapp2.abort(400, detail='invalid input')
    geoaddress = helpers.address_from_latlong(geoposition)

    if join_or_renew == 'join':
        # Set the GUID field
        member[config.MEMBER_FIELDS.id.name] = str(uuid.uuid4())
        # Set the timestamps
        member[config.MEMBER_FIELDS.joined.name] = utils.current_datetime()
        member[config.MEMBER_FIELDS.joined_by.name] = actor
        member[config.MEMBER_FIELDS.joined_latlong.name] = geoposition
        member[config.MEMBER_FIELDS.joined_address.name] = geoaddress

    # These get set regardless of mode
    member[config.MEMBER_FIELDS.renewed.name] = utils.current_datetime()
    member[config.MEMBER_FIELDS.renewed_by.name] = actor
    member[config.MEMBER_FIELDS.renewed_latlong.name] = geoposition
    member[config.MEMBER_FIELDS.renewed_address.name] = geoaddress

    member[config.MEMBER_FIELDS.address_latlong.name] = helpers.latlong_for_member(member)

    return member


def _update_member(list_entry, update_dict):
    """Updates the spreadsheet entry for `list_entry` with the data in
    `update_dict`. Also modifies/fills in `update_dict` with data from
    `list_entry`.
    `update_dict` will be modified with actual data.
    """

    # Update the values in list_entry
    for name, value in list_entry.to_dict().items():
        field = (f for f in config.MEMBER_FIELDS if f.name == name).next()
        if field.mutable and update_dict.get(name) is not None:
            list_entry.set_value(name, update_dict.get(name))
        else:
            update_dict[name] = value

    _update_list_entry(list_entry)

    return update_dict


def join_or_renew_member_from_dict(member_dict):
    """Renews the member if the email address already exists, otherwise joins
    the member as brand new. Returns 'renew' in the former case, 'join' in the
    latter.
    `member_dict` will be modified with actual data.
    """

    conflict_list_entry = None
    if member_dict.get(config.MEMBER_FIELDS.email.name):
        # Check if this member email already exists
        querystring = '%s=="%s"' % (config.MEMBER_FIELDS.email.name,
                                    member_dict.get(config.MEMBER_FIELDS.email.name))
        conflict_list_entry = _get_single_list_entry(querystring)

    if conflict_list_entry:
        _update_member(conflict_list_entry, member_dict)
        return 'renew'
    else:
        _add_new_row(member_dict)
        return 'join'


def renew_member_from_dict(member_dict):
    """Renew the membership of an existing member, while updating any info
    about them.
    `member_dict` will be modified with actual data.
    """

    # Retrieve the record from the spreadsheet
    # NOTE: We're not putting quotes around the second %s because if we do,
    # and the ID is numeric, the match will fail. Dumb.
    querystring = '%s==%s' % (config.MEMBER_FIELDS.id.name,
                              member_dict[config.MEMBER_FIELDS.id.name])
    list_entry = _get_single_list_entry(querystring)

    if not list_entry:
        webapp2.abort(400, detail='user ID lookup failed')

    _update_member(list_entry, member_dict)


def renew_member_by_email_or_paypal_id(email, paypal_payer_id, member_dict):
    """Looks in any email fields for the given email address and in the payer
    ID field for `paypal_payer_id`. Updates member entry from `member_dict`.
    Returns True if the member was found and renewed.
    """
    querystring = '%s=="%s" or %s=="%s" or %s=="%s"' % (
                    config.MEMBER_FIELDS.paypal_payer_id.name,
                    paypal_payer_id,
                    config.MEMBER_FIELDS.email.name,
                    email,
                    config.MEMBER_FIELDS.paypal_email.name,
                    email)
    list_entry = _get_single_list_entry(querystring)

    # TODO: Refactor this duplication
    member_dict[config.MEMBER_FIELDS.renewed.name] = utils.current_datetime()
    member_dict[config.MEMBER_FIELDS.renewed_by.name] = config.PAYPAL_ACTOR_NAME
    member_dict[config.MEMBER_FIELDS.renewed_latlong.name] = ''
    member_dict[config.MEMBER_FIELDS.renewed_address.name] = ''

    # HACK: In theory we should be updating the address geoposition here. But
    # we "know" that the address isn't changing. Make sure this is better when
    # we refactor this stuff.
    #member_dict[config.MEMBER_FIELDS.address_latlong.name] = helpers.latlong_for_member(member_dict)

    if list_entry:
        _update_member(list_entry, member_dict)
        return True

    return False


def get_volunteer_interests():
    rows = _get_all_rows(config.VOLUNTEER_SPREADSHEET_KEY,
                         config.VOLUNTEER_WORKSHEET_KEY)
    res = [row[config.VOLUNTEER_FIELDS.interest.name] for row in rows]
    return set(res)


def get_all_members():
    """Returns a list of dicts of member data.
    """
    return _get_all_rows(config.MEMBERS_SPREADSHEET_KEY,
                         config.MEMBERS_WORKSHEET_KEY,
                         sort_name=config.MEMBER_FIELDS.last_name.name)


def authorize_new_user(request, user):
    """Creates a new member with the data in the reqeust.
    """

    logging.info('authorize_user')
    logging.info(request.params.items())

    new_user = config.validate_obj_against_fields(request.POST,
                                                  config.AUTHORIZED_FIELDS)

    if not new_user:
        # This causes the request processing to stop
        webapp2.abort(400, detail='invalid input')

    # Check if this user (i.e., email) is already authorized
    # NOTE: We're putting "" around the second %s because otherwise the query
    # gives an error.
    querystring = '%s=="%s"' % (config.AUTHORIZED_FIELDS.email.name,
                                request.POST.get(config.AUTHORIZED_FIELDS.email.name))
    existing_user = _get_single_list_entry(querystring,
                                           spreadsheet_key=config.AUTHORIZED_SPREADSHEET_KEY,
                                           worksheet_key=config.AUTHORIZED_WORKSHEET_KEY)
    if existing_user:
        # This causes the request processing to stop
        webapp2.abort(400, detail='user email address already authorized')

    # Set the GUID field
    new_user[config.AUTHORIZED_FIELDS.id.name] = str(uuid.uuid4())
    # Set the timestamps
    new_user[config.AUTHORIZED_FIELDS.created.name] = utils.current_datetime()
    new_user[config.AUTHORIZED_FIELDS.created_by.name] = user.email()

    _add_new_row(new_user,
                 spreadsheet_key=config.AUTHORIZED_SPREADSHEET_KEY,
                 worksheet_key=config.AUTHORIZED_WORKSHEET_KEY)


def send_email(to_address, to_name, subject, body_html):
    """Sends an email from the configured address.
    Does not check for address validity.
    """

    if config.ALLOWED_EMAIL_TO_ADDRESSES and \
       to_address not in config.ALLOWED_EMAIL_TO_ADDRESSES:
        # Not allowed to send to this address
        logging.info('send_email: not allowed to send to: %s' % to_address)
        return

    full_to_address = '%s <%s>' % (to_name, to_address)

    h2t = html2text.HTML2Text()
    h2t.body_width = 0
    body_text = h2t.handle(body_html)

    message = mail.EmailMessage(sender=config.MASTER_EMAIL_SEND_ADDRESS,
                                subject=subject,
                                to=full_to_address,
                                body=body_text,
                                html=body_html)

    message.send()


def get_volunteer_interest_reps_for_member(member_data):
    """Gets the reps for the volunteer interest areas that the user has
    indicated. Returns a dict that looks like this:
        {
            'Pop-ups': [{'name': 'Jill Smith',
                         'email': 'jsmith@gmail.com'}],
            'Trees': [{'name': 'Jill Smith',
                       'email': 'jsmith@gmail.com'},
                      {'name': 'John Jones',
                       'email': 'jjones@gmail.com'}]
        }
    `user_data` is a dict-like object of member info.
    Returns {} if no reps found.
    """

    all_reps = _get_all_rows(config.VOLUNTEER_SPREADSHEET_KEY,
                             config.VOLUNTEER_WORKSHEET_KEY)

    member_interests = member_data.get(config.MEMBER_FIELDS.volunteer_interests.name, '')\
                                  .split(config.VOLUNTEER_INTERESTS_DIVIDER)

    interest_reps = {}

    for member_interest in member_interests:
        reps = [rep for rep in all_reps if rep.get('interest') == member_interest and rep.get('email')]
        if reps:
            interest_reps[member_interest] = reps

    return interest_reps


def cull_members_sheet():
    """Deletes defunct members from the members sheet.
    """

    # NOTE: The Google Spreadsheet API for deleting a row is stupid,
    # inconsistent, and dangerous. It's incredibly easy to accidentally
    # delete rows that you didn't intend to delete.
    # For example, see the comment about `If-Match` in _delete_list_entry().
    # So we're going to do this in the safest, dumbest way possible: We're
    # going to retrieve the entire spreadsheet, find a single row to delete,
    # delete it, and then re-fetch the entire spreadsheet again, etc.
    # We're going to make this even dumber by sending a taskqueue request to
    # ourself instead of actually looping. We're doing it that because I'm
    # afraid that this approach is so slow and dumb that it will exceed the
    # task time limit. (Although it probably won't.) And because maybe it's
    # more robust that way.
    #
    # The fact that this task can be triggered by cron *and* by taskqueue
    # probably means that there's a possibility of multiple threads of them
    # running at the same time. Which would be bad. But improbable. Remember
    # that in a normal run there will be at most one member to delete.

    gdata_client, _, _ = get_google_service_clients()

    list_feed = gdata_client.get_list_feed(config.MEMBERS_SPREADSHEET_KEY,
                                           config.MEMBERS_WORKSHEET_KEY)

    now = datetime.datetime.now()

    for entry in list_feed.entry:
        entry_dict = entry.to_dict()
        renewed_date = entry_dict.get(config.MEMBER_FIELDS.renewed.name)

        # Use Joined date if Renewed is empty
        if not renewed_date:
            renewed_date = entry_dict.get(config.MEMBER_FIELDS.joined.name)

        renewed_ago = datetime.timedelta.max
        if renewed_date:
            renewed_ago = now - dateutil.parser.parse(renewed_date)

        if renewed_ago.days > 800:  # two years and a bit
            logging.info('cull_members_sheet: deleting: %s' % entry_dict)
            _delete_list_entry(entry)

            # Queue up another call
            taskqueue.add(url='/tasks/member-sheet-cull')

            # We've done one and queued up another -- stop
            break


def archive_members_sheet(member_sheet_year):
    """Makes an archival copy of the members sheet.
    Returns the new current year if sheet has been archived, None otherwise.
    """

    year_now = datetime.date.today().year

    if member_sheet_year == year_now:
        logging.info('archive_member_sheet: not archving')
        return None

    logging.info('archive_member_sheet: archving!')

    # Make a copy of the current members sheet
    _copy_drive_file(config.MEMBERS_SPREADSHEET_KEY,
                     'Members %d' % member_sheet_year,
                     'Archive of the Members spreadsheet at the end of %d' % member_sheet_year)

    return year_now


#
# Low-ish-level helpers
#

def _update_list_entry(list_entry):
    """Updates the given list_entry, which must have been first retrieved with
    get_list_feed. Calls webapp2.abort on failure.
    For some reason, this functionality isn't in the GData client, so we'll
    need to roll it ourselves.
    """

    gdata_client, _, http = get_google_service_clients()

    headers = {'Content-type': 'application/atom+xml',
               'GData-Version': gdata_client.api_version}

    req_body = list_entry.to_string()\
                         .replace('"&quot;', '\'"')\
                         .replace('&quot;"', '"\'')

    url = list_entry.get_edit_link().href

    resp, _ = http.request(url, method='PUT', headers=headers, body=req_body)

    if resp.status != 200:
        webapp2.abort(500, detail='update member request failed')


def _delete_list_entry(list_entry):
    """Updates the given list_entry, which must have been first retrieved with
    get_list_feed. Calls webapp2.abort on failure.
    For some reason, this functionality isn't in the GData client, so we'll
    need to roll it ourselves.
    """

    gdata_client, _, http = get_google_service_clients()

    headers = {'Content-type': 'application/atom+xml',
               'GData-Version': gdata_client.api_version}

    # This will cause the request to fail if the entry has been changed since
    # it was retrieved. This is bad, since, we don't have retries, but...
    # probably the best choice.
    # UPDATE: This doesn't seem to do anything at all. See:
    # http://stackoverflow.com/questions/24127369/google-spreadsheet-api-if-match-does-not-take-affect
    # https://groups.google.com/forum/#!topic/google-spreadsheets-api/8jUpojDdr3Y
    headers['If-Match'] = list_entry.etag

    url = list_entry.get_edit_link().href

    resp, _ = http.request(url, method='DELETE', headers=headers)

    if resp.status != 200:
        webapp2.abort(500, detail='delete member request failed')


def _get_all_rows(spreadsheet_key, worksheet_key, sort_name=None):
    """Returns a list of dicts of row data.
    """

    gdata_client, _, _ = get_google_service_clients()

    query = None
    if sort_name:
        query = ListQuery(order_by=sort_name)


    list_feed = gdata_client.get_list_feed(spreadsheet_key,
                                           worksheet_key,
                                           query=query)

    return [entry.to_dict() for entry in list_feed.entry]


def _add_new_row(row_dict,
                 spreadsheet_key=config.MEMBERS_SPREADSHEET_KEY,
                 worksheet_key=config.MEMBERS_WORKSHEET_KEY):

    entry = ListEntry()
    entry.from_dict(row_dict)

    gdata_client, _, _ = get_google_service_clients()

    gdata_client.add_list_entry(entry,
                                spreadsheet_key,
                                worksheet_key)


def _get_single_list_entry(querystring,
                           spreadsheet_key=config.MEMBERS_SPREADSHEET_KEY,
                           worksheet_key=config.MEMBERS_WORKSHEET_KEY):
    """Returns a matching ListEntry or None if not found.
    """

    query = ListQuery(sq=querystring)

    gdata_client, _, _ = get_google_service_clients()

    list_feed = gdata_client.get_list_feed(spreadsheet_key,
                                           worksheet_key,
                                           query=query)

    if len(list_feed.entry) == 0:
        return None

    return list_feed.entry[0]


def _get_first_worksheet_id(spreadsheet_key):
    """Mostly used as a hand-run function to get the ID of the first worksheet
    in a spreadsheet (which is otherwise remarkably difficult to figure out).
    """

    gdata_client, _, _ = get_google_service_clients()

    worksheets_feed = gdata_client.get_worksheets(spreadsheet_key)

    if len(worksheets_feed.entry) == 0:
        logging.error('No worksheet found?!?')
        return None

    url = worksheets_feed.entry[0].get_self_link().href

    # There is surely a less hacky way to do this.
    worksheet_id = url.split('/')[-1]

    return worksheet_id


def _copy_drive_file(file_id, new_title, description):
    """Makes a copy of the given Google Drive file (i.e., spreadsheet), with a
    new title.
    """
    _, drive_service, _ = get_google_service_clients()
    drive_files = drive_service.files()              # pylint: disable=E1103
    drive_permissions = drive_service.permissions()  # pylint: disable=E1103

    # Get the parent folder(s)
    # (this is essential to maintain share permissions)
    file_info = drive_files.get(fileId=file_id).execute()

    # Make the copy
    request_body = {
        'title': new_title,
        'description': description,
        'parents': file_info['parents'],
        }
    req = drive_files.copy(fileId=file_id, body=request_body)
    new_file_info = req.execute()

    # Transfer ownership from the service account to the real user account
    req = drive_permissions.getIdForEmail(email=config.MASTER_EMAIL_ADDRESS)
    master_permissions_info = req.execute()

    req = drive_permissions.update(
        fileId=new_file_info['id'],
        permissionId=master_permissions_info['id'],
        transferOwnership=True,
        body={'role': 'owner'})
    req.execute()


def _update_all_members_address_latlong():
    """One-off helper to fill in the `address_latlong` field for legacy members.
    """

    gdata_client, _, _ = get_google_service_clients()

    list_feed = gdata_client.get_list_feed(config.MEMBERS_SPREADSHEET_KEY,
                                           config.MEMBERS_WORKSHEET_KEY)

    for list_entry in list_feed.entry:
        member_dict = list_entry.to_dict()

        if member_dict.get(config.MEMBER_FIELDS.address_latlong.name):
            continue

        latlong = helpers.latlong_for_member(member_dict)

        if not latlong:
            continue

        list_entry.set_value(config.MEMBER_FIELDS.address_latlong.name,
                             latlong)

        _update_list_entry(list_entry)

