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
from dateutil.relativedelta import relativedelta

from google.appengine.api import mail
from google.appengine.api import taskqueue
from google.appengine.api import urlfetch

from googledata import GoogleData, ListEntry
import config
import utils
import helpers
import mailchimp


def is_user_authorized(user):
    """Takes an authenticated user and return True if that user is allowed to
    access this service, False otherwise.
    """

    # DEMO ONLY
    return True

    # Check if this user (i.e., email) is already authorized
    querystring = '%s=="%s"' % (config.AUTHORIZED_FIELDS.email.name,
                                user.email())
    auth_user = _get_single_list_entry(querystring,
                                       config.AUTHORIZED_SPREADSHEET_KEY,
                                       config.AUTHORIZED_WORKSHEET_KEY)
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

        if field.values is not None and request.POST.get(name) is not None \
           and not set(request.POST.get(name).split(config.MULTIVALUE_DIVIDER)).issubset(field.values):
            # This causes the request processing to stop
            webapp2.abort(400, detail='invalid field value')

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

    member[config.MEMBER_FIELDS.address_latlong.name] = helpers.latlong_for_record(
                                                            config.MEMBER_FIELDS,
                                                            member)

    # We want the "MailChimp Updated" field to be cleared, regardless of mode
    member[config.MEMBER_FIELDS.mailchimp_updated.name] = ''

    return member


def volunteer_dict_from_request(request, actor):
    """Creates and returns a dict of volunteer info from the request.
    """

    logging.debug('volunteer_dict_from_request')
    logging.debug(request.params.items())

    # Make sure the user/form/request isn't trying to mess with fields that it
    # shouldn't be.
    for name, field in config.VOLUNTEER_FIELDS._asdict().items():
        if not field.form_field and request.POST.get(name) is not None:
            # This causes the request processing to stop
            webapp2.abort(400, detail='invalid field')

        if field.values is not None and request.POST.get(name) is not None \
           and not set(request.POST.get(name).split(config.MULTIVALUE_DIVIDER)).issubset(field.values):
            # This causes the request processing to stop
            webapp2.abort(400, detail='invalid field value')

    volunteer = config.validate_volunteer(request.POST)

    if not volunteer:
        # This causes the request processing to stop
        webapp2.abort(400, detail='invalid input')

    # We didn't validate the geoposition above, so do it now
    geoposition = request.POST.get('geoposition', '')  # TODO: don't hardcode field name
    geoposition_required = config.VOLUNTEER_FIELDS.joined_latlong.required
    if not utils.latlong_validator(geoposition, geoposition_required):
        webapp2.abort(400, detail='invalid input')
    geoaddress = helpers.address_from_latlong(geoposition)

    # Set the GUID field
    volunteer[config.VOLUNTEER_FIELDS.id.name] = str(uuid.uuid4())
    # Set the timestamps
    volunteer[config.VOLUNTEER_FIELDS.joined.name] = utils.current_datetime()
    volunteer[config.VOLUNTEER_FIELDS.joined_by.name] = actor
    volunteer[config.VOLUNTEER_FIELDS.joined_latlong.name] = geoposition
    volunteer[config.VOLUNTEER_FIELDS.joined_address.name] = geoaddress

    volunteer[config.VOLUNTEER_FIELDS.address_latlong.name] = \
        helpers.latlong_for_record(config.VOLUNTEER_FIELDS, volunteer)

    return volunteer


def _update_record(fields, list_entry, update_dict):
    """Updates the spreadsheet entry for `list_entry` with the data in
    `update_dict`. Also modifies/fills in `update_dict` with data from
    `list_entry`.
    `update_dict` will be modified with actual data.
    """

    # Update the values in list_entry
    for name, value in list_entry.to_dict().items():
        field = next((f for f in fields if f.name == name), None)
        if not field:
            # Field in list entry is not found in config fields. This can
            # happen if we have added a column to the spreadsheet that isn't
            # yet in the deployed config.
            logging.warning('field in spreadsheet not found in config')
            continue

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
        conflict_list_entry = _get_single_list_entry(querystring,
                                                     config.MEMBERS_SPREADSHEET_KEY,
                                                     config.MEMBERS_WORKSHEET_KEY)

    if conflict_list_entry:
        logging.debug('found conflicting entry; updating')
        _update_record(config.MEMBER_FIELDS, conflict_list_entry, member_dict)
        return 'renew'
    else:
        logging.debug('no conflict found; creating')
        _add_new_row(member_dict,
                     config.MEMBERS_SPREADSHEET_KEY,
                     config.MEMBERS_WORKSHEET_KEY)
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
    list_entry = _get_single_list_entry(querystring,
                                        config.MEMBERS_SPREADSHEET_KEY,
                                        config.MEMBERS_WORKSHEET_KEY)

    if not list_entry:
        webapp2.abort(400, detail='user ID lookup failed')

    _update_record(config.MEMBER_FIELDS, list_entry, member_dict)


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
    list_entry = _get_single_list_entry(querystring,
                                        config.MEMBERS_SPREADSHEET_KEY,
                                        config.MEMBERS_WORKSHEET_KEY)

    # TODO: Refactor this duplication
    member_dict[config.MEMBER_FIELDS.renewed.name] = utils.current_datetime()
    member_dict[config.MEMBER_FIELDS.renewed_by.name] = config.PAYPAL_ACTOR_NAME
    member_dict[config.MEMBER_FIELDS.renewed_latlong.name] = ''
    member_dict[config.MEMBER_FIELDS.renewed_address.name] = ''

    # HACK: In theory we should be updating the address geoposition here. But
    # we "know" that the address isn't changing. Make sure this is better when
    # we refactor this stuff.
    #member_dict[config.MEMBER_FIELDS.address_latlong.name] = helpers.latlong_for_record(config.MEMBER_FIELDS, member_dict)

    # We're not bothering to clear the "MailChimp Updated" field here, since we
    # know that no interesting fields are changing in the member row

    if list_entry:
        _update_record(config.MEMBER_FIELDS, list_entry, member_dict)
        return True

    return False


def join_volunteer_from_dict(volunteer_dict):
    """Add the new volunteer.
    `volunteer_dict` will be modified with actual data.
    """

    conflict_list_entry = None
    if volunteer_dict.get(config.VOLUNTEER_FIELDS.email.name):
        # Check if this volunteer email already exists
        querystring = '%s=="%s"' % (config.VOLUNTEER_FIELDS.email.name,
                                    volunteer_dict.get(config.VOLUNTEER_FIELDS.email.name))
        conflict_list_entry = _get_single_list_entry(querystring,
                                                     config.VOLUNTEERS_SPREADSHEET_KEY,
                                                     config.VOLUNTEERS_WORKSHEET_KEY)

    if conflict_list_entry:
        logging.debug('found conflicting record; updating')
        _update_record(config.VOLUNTEER_FIELDS, conflict_list_entry, volunteer_dict)
    else:
        _add_new_row(volunteer_dict,
                     config.VOLUNTEERS_SPREADSHEET_KEY,
                     config.VOLUNTEERS_WORKSHEET_KEY)


def get_volunteer_interests():
    return _get_all_rows(config.VOLUNTEER_INTERESTS_SPREADSHEET_KEY,
                         config.VOLUNTEER_INTERESTS_WORKSHEET_KEY)


def get_skills_categories():
    return _get_all_rows(config.SKILLS_CATEGORIES_SPREADSHEET_KEY,
                         config.SKILLS_CATEGORIES_WORKSHEET_KEY)


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
                                           config.AUTHORIZED_SPREADSHEET_KEY,
                                           config.AUTHORIZED_WORKSHEET_KEY)
    if existing_user:
        # This causes the request processing to stop
        webapp2.abort(400, detail='user email address already authorized')

    # Set the GUID field
    new_user[config.AUTHORIZED_FIELDS.id.name] = str(uuid.uuid4())
    # Set the timestamps
    new_user[config.AUTHORIZED_FIELDS.created.name] = utils.current_datetime()
    new_user[config.AUTHORIZED_FIELDS.created_by.name] = 'useremail@example.com' # DEMO: user.email()

    _add_new_row(new_user,
                 config.AUTHORIZED_SPREADSHEET_KEY,
                 config.AUTHORIZED_WORKSHEET_KEY)


def send_email(to_address, to_name, subject, body_html):
    """Sends an email from the configured address.
    Does not check for address validity.
    """

    if config.ALLOWED_EMAIL_TO_ADDRESSES is not None and \
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

    all_reps = _get_all_rows(config.VOLUNTEER_INTERESTS_SPREADSHEET_KEY,
                             config.VOLUNTEER_INTERESTS_WORKSHEET_KEY)

    member_interests = member_data.get(config.MEMBER_FIELDS.volunteer_interests.name, '')\
                                  .split(config.MULTIVALUE_DIVIDER)

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

    older_than = datetime.datetime.now() - relativedelta(years=2, months=1)

    cull_entries = _get_members_renewed_ago(None, older_than)

    if not cull_entries:
        return

    for entry in cull_entries:
        logging.info('cull_members_sheet: deleting: %s' % entry.to_dict())
        _delete_list_entry(entry)

        # Queue up another call
        taskqueue.add(url='/tasks/member-sheet-cull')

        # We've done one and queued up another -- stop
        return


def archive_members_sheet(member_sheet_year):
    """Makes an archival copy of the members sheet.
    Returns the new current year if sheet has been archived, None otherwise.
    """

    next_archive_date = datetime.date(
                            member_sheet_year + 1,
                            config.MEMBER_SHEET_ARCHIVE_MONTH,
                            config.MEMBER_SHEET_ARCHIVE_DAY)

    today = datetime.date.today()

    if today < next_archive_date:
        logging.info('archive_member_sheet: not archving; next date: %s', next_archive_date)
        return None

    logging.info('archive_member_sheet: archving!')

    year_now = today.year

    # Make a copy of the current members sheet
    _copy_drive_file(config.MEMBERS_SPREADSHEET_KEY,
                     'Archive: Members %d' % member_sheet_year,
                     'Archive of the Members spreadsheet at the end of %d' % member_sheet_year)

    return year_now


def get_members_expiring_soon():
    """Returns a list of list-entries of members expiring soon.
    """

    # We want members whose membership will be expiring in a week. This means
    # getting members who were last renewed one year less a week ago. We
    # check daily, so we'll get members in a day-long window.
    after_datetime = datetime.datetime.now() + relativedelta(years=-1, days=6)
    before_datetime = datetime.datetime.now() + relativedelta(years=-1, days=7)

    expiring_entries = _get_members_renewed_ago(after_datetime, before_datetime)

    return expiring_entries or []


def process_mailchimp_updates():
    """Checks Members and Volunteers spreadsheets for records that need updating
    in MailChimp.
    """

    # See comment in `cull_members_sheet()` for why we're using `taskqueue`
    # to process these records one at a time.

    googledata = GoogleData()

    for fields, spreadsheet_key, worksheet_key, mailchimp_upsert in (
            (config.MEMBER_FIELDS, config.MEMBERS_SPREADSHEET_KEY, config.MEMBERS_WORKSHEET_KEY, mailchimp.upsert_member_info),
            (config.VOLUNTEER_FIELDS, config.VOLUNTEERS_SPREADSHEET_KEY, config.VOLUNTEERS_WORKSHEET_KEY, mailchimp.upsert_volunteer_info),
        ):

        querystring = '%s==""' % (fields.mailchimp_updated.name,)
        list_entries = googledata.get_list_entries(spreadsheet_key,
                                                   worksheet_key,
                                                   query=querystring)

        for entry in list_entries:
            entry_dict = entry.to_dict()

            if not entry_dict.get(fields.id.name):
                logging.error('Member missing ID value: %s', entry_dict)
                continue

            # Updated MailChimp
            mailchimp_upsert(entry_dict)

            # Set the MailChimp update datetime
            entry.set_value(fields.mailchimp_updated.name,
                            utils.current_datetime())

            # Update the spreadsheet
            _update_list_entry(entry)

            # We've updated one record successfully. Enqueue another run and exit.
            taskqueue.add(url='/tasks/process-mailchimp-updates')
            return


#
# Low-ish-level helpers
#

def _update_list_entry(list_entry):
    """Updates the given list_entry, which must have been first retrieved with
    get_list_feed. Calls webapp2.abort on failure.
    """

    googledata = GoogleData()
    googledata.update_list_entry(list_entry)


def _delete_list_entry(list_entry):
    """Updates the given list_entry, which must have been first retrieved with
    get_list_feed. Calls webapp2.abort on failure.
    """

    googledata = GoogleData()
    googledata.delete_list_entry(list_entry)


def _get_all_rows(spreadsheet_key, worksheet_key, sort_name=None):
    """Returns a list of dicts of row data.
    """

    order_by = None
    if sort_name:
        order_by = 'column:%s' % sort_name

    googledata = GoogleData()
    list_entries = googledata.get_list_entries(spreadsheet_key,
                                               worksheet_key,
                                               order_by=order_by)

    return [entry.to_dict() for entry in list_entries]


def _add_new_row(row_dict, spreadsheet_key, worksheet_key):

    entry = ListEntry()
    entry.from_dict(row_dict)

    googledata = GoogleData()
    googledata.add_list_entry(entry,  spreadsheet_key,  worksheet_key)

def _get_single_list_entry(querystring, spreadsheet_key, worksheet_key):
    """Returns a matching ListEntry or None if not found.
    """

    googledata = GoogleData()
    list_entries = googledata.get_list_entries(spreadsheet_key,
                                               worksheet_key,
                                               query=querystring)

    if not list_entries:
        return None

    return list_entries[0]


def _get_first_worksheet_id(spreadsheet_key):
    """Mostly used as a hand-run function to get the ID of the first worksheet
    in a spreadsheet (which is otherwise remarkably difficult to figure out).
    """

    googledata = GoogleData()
    worksheets = googledata.get_worksheets(spreadsheet_key)

    if not worksheets:
        logging.error('No worksheet found?!?')
        return None

    url = worksheets[0].get_self_link().href

    # There is surely a less hacky way to do this.
    worksheet_id = url.split('/')[-1]

    return worksheet_id


def _copy_drive_file(file_id, new_title, description):
    """Makes a copy of the given Google Drive file (i.e., spreadsheet), with a
    new title.
    """
    googledata = GoogleData()
    drive_service = googledata.get_drive_service()

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


def _get_members_renewed_ago(after_datetime, before_datetime):
    """Get the members who were last renewed within the given window.
    Args:
        after_datetime (datetime): Members must have been renewed *after* this
            date. Optional.
        before_datetime (datetime): Members must have been renewed *before*
            this date. Optional.
    Returns:
        List of member list entries. (Caller can get dict with `.to_dict()`.)
    """

    # Note that dates get returned from the spreadsheet as locale-formatted
    # strings, so we can't do a list-feed query to get just the rows we want.
    # Instead we're going to have to go through the whole set and filter them
    # from there.

    assert(after_datetime or before_datetime)

    googledata = GoogleData()
    list_entries = googledata.get_list_entries(config.MEMBERS_SPREADSHEET_KEY,
                                               config.MEMBERS_WORKSHEET_KEY)

    results = []

    for entry in list_entries:
        entry_dict = entry.to_dict()

        renewed_date = entry_dict.get(config.MEMBER_FIELDS.renewed.name)

        # Use Joined date if Renewed is empty
        if not renewed_date:
            renewed_date = entry_dict.get(config.MEMBER_FIELDS.joined.name)

        # Convert date string to datetime
        if renewed_date:
            try:
                renewed_date = dateutil.parser.parse(renewed_date)
            except:
                renewed_date = None

        # If we still don't have a renewed date... the user is probably
        # very old or invalid. Set the date to a long time ago, so it gets
        # culled out.
        if not renewed_date:
            renewed_date = datetime.datetime(1970, 1, 1)

        if after_datetime and not (after_datetime <= renewed_date):
            continue

        if before_datetime and not (before_datetime >= renewed_date):
            continue

        # If we passed those two checks, then it's a hit.

        results.append(entry)

    return results


def _update_all_members_address_latlong():
    """One-off helper to fill in the `address_latlong` field for legacy members.
    """

    googledata = GoogleData()
    list_entries = googledata.get_list_entries(config.MEMBERS_SPREADSHEET_KEY,
                                               config.MEMBERS_WORKSHEET_KEY)

    for list_entry in list_entries:
        member_dict = list_entry.to_dict()

        if member_dict.get(config.MEMBER_FIELDS.address_latlong.name):
            continue

        latlong = helpers.latlong_for_record(config.MEMBER_FIELDS, member_dict)

        if not latlong:
            continue

        list_entry.set_value(config.MEMBER_FIELDS.address_latlong.name,
                             latlong)

        _update_list_entry(list_entry)

