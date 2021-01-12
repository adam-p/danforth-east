# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : https://adampritchard.mit-license.org/
#

from typing import Optional, List
import os
import logging
import uuid
import datetime
import flask
import dateutil
from dateutil.relativedelta import relativedelta
from google.cloud import tasks_v2

import config
import utils
import helpers
import mailchimp
import sheetdata


# This will make our life a little easier in this file.
_S = config.SHEETS

# This will be set by the JavaScript in common.js
_GEOPOSITION_VALUE_KEY = 'geoposition'


def is_user_authorized(email: str) -> bool:
    """Takes an authenticated user and returns True if that user is allowed to
    access this service, False otherwise.
    """

    if config.DEMO:
        return True

    if not email:
        return False

    # Check if this user (i.e., email) is already authorized
    row = sheetdata.Row.find(
        _S.authorized,
        lambda d: d[_S.authorized.fields.email.name] == email)

    if row:
        return True

    return False


def member_dict_from_request(request: flask.Request, actor: str, join_or_renew: str) -> dict:
    """Creates and returns a dict of member info from the request.
    new_or_renew should be "join" if this is (or expected to be) for a new
    member, or "renew" for a member being renewed.
    `actor` is the ID/email of the person or entity that is triggering this.
    """

    logging.info('member_dict_from_request')
    logging.info(list(request.values.items()))

    # Make sure the user/form/request isn't trying to mess with fields that it
    # shouldn't be.
    for name, field in _S.member.fields._asdict().items():
        if not field.form_field and request.values.get(name) is not None:
            # There is a field provided in the request that isn't one that's allowed to be
            # set via the form. This can be achieved by an attacker by modifying the page
            # elements. This causes the request processing to stop.
            flask.abort(400, description='invalid field')

        if field.values is not None and request.values.get(name) is not None \
            and not set(request.values.get(name).split(config.MULTIVALUE_DIVIDER)).issubset(field.values):
            # This field has a restricted set of allowed values, and the form has provided
            # one that isn't allowed. This causes the request processing to stop.
            flask.abort(400, description='invalid field value')

    member = config.validate_member(request.values)

    if not member:
        logging.warning('gapps.member_dict_from_request: config.validate_member failed')
        # This causes the request processing to stop
        flask.abort(400, description='invalid input')

    # We didn't validate the geoposition above, so do it now
    geoposition = request.values.get(_GEOPOSITION_VALUE_KEY, '')
    geoposition_required = _S.member.fields.joined_latlong.required \
                            if join_or_renew == 'join' else \
                            _S.member.fields.renewed_latlong.required
    if not utils.latlong_validator(geoposition, geoposition_required):
        logging.warning('gapps.member_dict_from_request: utils.latlong_validator failed')
        flask.abort(400, description='invalid input')
    geoaddress = helpers.address_from_latlong(geoposition)

    if join_or_renew == 'join':
        # Set the GUID field
        member[_S.member.fields.id.name] = str(uuid.uuid4())
        # Set the timestamps
        member[_S.member.fields.joined.name] = utils.current_datetime()
        member[_S.member.fields.joined_by.name] = actor
        member[_S.member.fields.joined_latlong.name] = geoposition
        member[_S.member.fields.joined_address.name] = geoaddress

    # These get set regardless of mode
    member[_S.member.fields.renewed.name] = utils.current_datetime()
    member[_S.member.fields.renewed_by.name] = actor
    member[_S.member.fields.renewed_latlong.name] = geoposition
    member[_S.member.fields.renewed_address.name] = geoaddress

    member[_S.member.fields.address_latlong.name] = helpers.latlong_for_record(
                                                            _S.member.fields,
                                                            member)

    # We want the "MailChimp Updated" field to be cleared, regardless of mode
    member[_S.member.fields.mailchimp_updated.name] = ''

    # Fields clear if we're in demo mode. We don't want to record a demo user's email address.
    if config.DEMO:
        member[_S.member.fields.joined_by.name] = 'demo@example.com'
        member[_S.member.fields.renewed_by.name] = 'demo@example.com'
        member[_S.member.fields.joined_latlong.name] = ''
        member[_S.member.fields.joined_address.name] = 'Demo'
        member[_S.member.fields.renewed_latlong.name] = ''
        member[_S.member.fields.renewed_address.name] = 'Demo'

    return member


def volunteer_dict_from_request(request: flask.Request, actor: str) -> dict:
    """Creates and returns a dict of volunteer info from the request.
    `actor` is the ID/email of the person or entity that is triggering this.
    """

    logging.debug('gapps.volunteer_dict_from_request: %s', list(request.values.items()))

    # Make sure the user/form/request isn't trying to mess with fields that it
    # shouldn't be.
    for name, field in _S.volunteer.fields._asdict().items():
        if not field.form_field and request.values.get(name) is not None:
            # This causes the request processing to stop
            flask.abort(400, description='invalid field')

        if field.values is not None and request.values.get(name) is not None \
           and not set(request.values.get(name).split(config.MULTIVALUE_DIVIDER)).issubset(field.values):
            # This causes the request processing to stop
            flask.abort(400, description='invalid field value')

    volunteer = config.validate_volunteer(request.values)

    if not volunteer:
        logging.warning('gapps.volunteer_dict_from_request: config.validate_volunteer failed')
        # This causes the request processing to stop
        flask.abort(400, description='invalid input')

    # We didn't validate the geoposition above, so do it now
    geoposition = request.values.get(_GEOPOSITION_VALUE_KEY, '')
    geoposition_required = _S.volunteer.fields.joined_latlong.required
    if not utils.latlong_validator(geoposition, geoposition_required):
        logging.warning('gapps.volunteer_dict_from_request: utils.latlong_validator failed')
        flask.abort(400, description='invalid input')
    geoaddress = helpers.address_from_latlong(geoposition)

    # Set the GUID field
    volunteer[_S.volunteer.fields.id.name] = str(uuid.uuid4())
    # Set the timestamps
    volunteer[_S.volunteer.fields.joined.name] = utils.current_datetime()
    volunteer[_S.volunteer.fields.joined_by.name] = actor
    volunteer[_S.volunteer.fields.joined_latlong.name] = geoposition
    volunteer[_S.volunteer.fields.joined_address.name] = geoaddress

    volunteer[_S.volunteer.fields.address_latlong.name] = \
        helpers.latlong_for_record(_S.volunteer.fields, volunteer)

    return volunteer


def join_or_renew_member_from_dict(member_dict: dict) -> str:
    """Renews the member if the email address already exists, otherwise joins
    the member as brand new. Returns 'renew' in the former case, 'join' in the
    latter.
    `member_dict` will be modified with actual data.
    """

    conflict_row = None
    if member_dict.get(_S.member.fields.email.name):
        # Check if this member email already exists
        conflict_row = sheetdata.Row.find(
            _S.member,
            lambda d: d[_S.member.fields.email.name] == member_dict.get(_S.member.fields.email.name))

    if conflict_row:
        logging.debug('found conflicting entry; updating')

        # Clear the fields that should not be set when renewing.
        # TODO: This is a hack. It would be better to not fill in the fields in the first
        # place. Instead we need to make sure the fields set in member_dict_from_request()
        # are the same ones we clear here. We should find a better way.
        member_dict[_S.member.fields.id.name] = None
        member_dict[_S.member.fields.joined.name] = None
        member_dict[_S.member.fields.joined_by.name] = None
        member_dict[_S.member.fields.joined_latlong.name] = None
        member_dict[_S.member.fields.joined_address.name] = None

        conflict_row.dict.update(member_dict)
        conflict_row.update()
        return 'renew'
    else:
        logging.debug('no conflict found; creating')
        sheetdata.Row(member_dict, sheet=_S.member).append()
        return 'join'


def renew_member_from_dict(member_dict: dict):
    """Renew the membership of an existing member, while updating any info
    about them.
    `member_dict` will be modified with actual data.
    """

    # Retrieve the record from the spreadsheet
    row = sheetdata.Row.find(_S.member,
        lambda d: d[_S.member.id_field().name] == member_dict[_S.member.id_field().name])

    if not row:
        flask.abort(400, description='user lookup failed')

    row.dict.update(member_dict)
    row.update()


def renew_member_by_email_or_paypal_id(email: str, paypal_payer_id: str, member_dict: dict) -> bool:
    """Looks in any email fields for the given email address and in the payer
    ID field for `paypal_payer_id`. Updates member entry from `member_dict`.
    Returns True if the member was found and renewed.
    """

    if not email and not paypal_payer_id:
        logging.warning('gapps.renew_member_by_email_or_paypal_id: email and paypal_payer_id empty')
        return False

    def matcher(d):
        if paypal_payer_id and (d[_S.member.fields.paypal_payer_id.name] == paypal_payer_id):
            return True
        if email and (d[_S.member.fields.email.name] == email) or (d[_S.member.fields.paypal_email.name] == email):
            return True
        return False

    row = sheetdata.Row.find(_S.member, matcher)

    if not row:
        return False

    member_dict[_S.member.fields.renewed.name] = utils.current_datetime()
    member_dict[_S.member.fields.renewed_by.name] = config.PAYPAL_ACTOR_NAME
    member_dict[_S.member.fields.renewed_latlong.name] = ''
    member_dict[_S.member.fields.renewed_address.name] = ''

    # HACK: In theory we should be updating the address geoposition here. But
    # we "know" that the address isn't changing. Make sure this is better when
    # we refactor this stuff.
    #member_dict[_S.member.fields.address_latlong.name] = helpers.latlong_for_record(_S.member.fields, member_dict)

    # We're not bothering to clear the "MailChimp Updated" field here, since we
    # know that no interesting fields are changing in the member row

    row.dict.update(member_dict)
    row.update()
    return True


def join_volunteer_from_dict(volunteer_dict: dict):
    """Add the new volunteer.
    `volunteer_dict` will be modified with actual data.
    """

    conflict_row = None
    if volunteer_dict.get(_S.volunteer.fields.email.name):
        # Check if this volunteer email already exists
        conflict_row = sheetdata.Row.find(
            _S.volunteer,
            lambda d: d[_S.volunteer.fields.email.name] == volunteer_dict.get(_S.volunteer.fields.email.name))

    if conflict_row:
        logging.debug('found conflicting record; updating')

        # Clear the fields that should not be set when updating.
        # See comment in join_or_renew_member_from_dict for why this is a hack.
        volunteer_dict[_S.volunteer.fields.id.name] = None
        volunteer_dict[_S.volunteer.fields.joined.name] = None
        volunteer_dict[_S.volunteer.fields.joined_by.name] = None
        volunteer_dict[_S.volunteer.fields.joined_latlong.name] = None
        volunteer_dict[_S.volunteer.fields.joined_address.name] = None

        conflict_row.dict.update(volunteer_dict)
        conflict_row.update()
    else:
        logging.debug('no conflict found; creating')
        sheetdata.Row(volunteer_dict, sheet=_S.volunteer).append()


def get_volunteer_interests() -> List[str]:
    """Get a list of all volunteer interests from the sheet.
    """
    rows = sheetdata.find_rows(_S.volunteer_interest, matcher=None)
    return [r.dict for r in rows]


def get_skills_categories() -> List[str]:
    """Get a list of all skills categories from the sheet.
    """
    rows = sheetdata.find_rows(_S.skills_category, matcher=None)
    return [r.dict for r in rows]


def get_all_members() -> List[dict]:
    """Returns a list of dicts of member data.
    """
    rows = sheetdata.find_rows(_S.member, matcher=None)
    # Putting "||" between the first and last name to get a proper sort is not great, but sufficient
    rows.sort(key=lambda r: str.lower(f'{r.dict[_S.member.fields.last_name.name]}||{r.dict[_S.member.fields.first_name.name]}'))
    return [r.dict for r in rows]


def authorize_new_user(request: flask.Request, current_user_email: str):
    """Creates a new member with the data in the request.
    Calls flask.abort on bad input.
    """

    logging.info('authorize_new_user')
    logging.info(list(request.values.items()))

    new_user = config.validate_obj_against_fields(request.values, _S.authorized.fields)

    if not new_user:
        logging.warning('gapps.authorize_new_user: config.validate_obj_against_fields failed')
        # This causes the request processing to stop
        flask.abort(400, description='invalid input')

    # Check if this user (i.e., email) is already authorized
    if is_user_authorized(request.values.get(_S.authorized.fields.email.name)):
        # This causes the request processing to stop
        flask.abort(400, description='user email address already authorized')

    # Set the GUID field
    new_user[_S.authorized.fields.id.name] = str(uuid.uuid4())
    # Set the timestamps
    new_user[_S.authorized.fields.created.name] = utils.current_datetime()
    new_user[_S.authorized.fields.created_by.name] = current_user_email

    # Don't record a demo user's email address
    if config.DEMO:
        new_user[_S.authorized.fields.created_by.name] = 'user@example.com'

    sheetdata.Row(dct=new_user, sheet=_S.authorized).append()


def get_volunteer_interest_reps_for_member(member_data: dict) -> dict:
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

    all_reps = get_volunteer_interests()

    member_interests = member_data.get(_S.member.fields.volunteer_interests.name, '').split(config.MULTIVALUE_DIVIDER)

    interest_reps = {}
    for member_interest in member_interests:
        reps = [rep for rep in all_reps if rep.get(_S.volunteer_interest.fields.interest.name) == member_interest and rep.get(_S.volunteer_interest.fields.email.name)]
        if reps:
            interest_reps[member_interest] = reps

    return interest_reps


def cull_members_sheet():
    """Deletes defunct members from the members sheet.
    """

    older_than = datetime.datetime.now() - relativedelta(years=2, months=1)

    cull_rows = _get_members_renewed_ago(None, older_than)

    if not cull_rows:
        return

    logging.info('cull_members_sheet: deleting: %s', [r.dict for r in cull_rows])

    sheetdata.delete_rows(_S.member, [r.num for r in cull_rows])


def archive_members_sheet(member_sheet_year: int) -> Optional[int]:
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
    sheetdata.copy_drive_file(
        _S.member.spreadsheet_id,
        'Archive: Members %d' % member_sheet_year,
        'Archive of the Members spreadsheet at the end of %d' % member_sheet_year)

    return year_now


def get_members_expiring_soon() -> List[sheetdata.Row]:
    """Returns a list of rows of members expiring soon.
    """

    # We want members whose membership will be expiring in a week. This means
    # getting members who were last renewed one year less a week ago. We
    # check daily, so we'll get members in a day-long window.
    after_datetime = datetime.datetime.now() + relativedelta(years=-1, days=6)
    before_datetime = datetime.datetime.now() + relativedelta(years=-1, days=7)

    expiring_rows = _get_members_renewed_ago(after_datetime, before_datetime)

    return expiring_rows or []


def process_mailchimp_updates():
    """Checks Members and Volunteers spreadsheets for records that need updating
    in MailChimp.
    """

    for sheet, mailchimp_upsert in (
            (_S.member, mailchimp.upsert_member_info),
            (_S.volunteer, mailchimp.upsert_volunteer_info),
        ):

        rows = sheetdata.find_rows(
            sheet,
            lambda d: not d[sheet.fields.mailchimp_updated.name])

        rows_to_update = []

        for row in rows:
            if not row.dict.get(sheet.fields.id.name):
                logging.error('Member or Volunteer missing ID value: %s', row.dict)
                continue

            if not row.dict.get(sheet.fields.email.name):
                # If there's no email, we don't add to MailChimp
                continue

            # Set the MailChimp update datetime
            row.dict[sheet.fields.mailchimp_updated.name] = utils.current_datetime()

            # Update MailChimp. Note that this involves a network call.
            # TODO: Is there a bulk upsert for Mailchimp?
            mailchimp_upsert(row.dict)

            rows_to_update.append(row)

        sheetdata.update_rows(sheet, rows_to_update)


_TASK_QUEUE_SECRET_PARAM = 'secret'

def enqueue_task(url: str, params: dict):
    """Enqueue an App Engine task.
    `url` is relative. It must have no query params. The request will use the POST method.
    `params` must be something that can be JSON-encoded.
    """
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(config.PROJECT_NAME, config.PROJECT_REGION, config.TASK_QUEUE_NAME)

    task = tasks_v2.Task()
    task.app_engine_http_request = tasks_v2.AppEngineHttpRequest()
    task.app_engine_http_request.http_method = tasks_v2.HttpMethod.POST
    task.app_engine_http_request.relative_uri = f'{url}?{_TASK_QUEUE_SECRET_PARAM}={config.FLASK_SECRET_KEY}'
    task.app_engine_http_request.body = flask.json.dumps(params).encode()
    task.app_engine_http_request.app_engine_routing = tasks_v2.AppEngineRouting()
    task.app_engine_http_request.app_engine_routing.version = os.getenv('GAE_VERSION')

    response = client.create_task(parent=parent, task=task)
    logging.info(f'enqueued task to {url}')
    logging.info(response.name)

def validate_queue_task(request: flask.Request) -> dict:
    """Check that the incoming request is a legitimate queue task.
    Calls flask.abort(401) if it's not valid.
    The documentation assures us that this should just be a matter of checking for the
    presence of one of a number of headers (https://cloud.google.com/tasks/docs/creating-appengine-handlers#reading_app_engine_task_request_headers),
    but to be extra safe we're going to pass and check a secret.
    (The concern is that an attacker will make requests to our queue tasks directly.)
    """
    logging.info(f'gapps.validate_queue_task: validating request to {request.base_url}')
    if not request.headers.get('X-AppEngine-QueueName'):
        logging.error('gapps.validate_queue_task: queue task request missing X-AppEngine-QueueName')
        flask.abort(401)
    if request.args.get(_TASK_QUEUE_SECRET_PARAM) != config.FLASK_SECRET_KEY:
        logging.error('gapps.validate_queue_task: queue task request missing correct secret')
        flask.abort(401)

    logging.info(f'gapps.validate_queue_task: request is valid to {request.base_url}')
    params = flask.json.loads(request.get_data(as_text=True))
    return params

def validate_cron_task(request: flask.Request):
    """Check that the incoming request is a legitimate cron task.
    Calls flask.abort(401) if it's not valid.
    Unlike in the queue task validation, there's no additional secret we can pass to
    double-check. This _should_ be fine.
    https://cloud.google.com/appengine/docs/flexible/python/scheduling-jobs-with-cron-yaml#validating_cron_requests
    """
    logging.info(f'validating cron task request to {request.base_url}')
    if not request.headers.get('X-Appengine-Cron') == 'true':
        logging.error('queue task request missing X-Appengine-Cron')
        flask.abort(401)


#
# Low-ish-level helpers
#

def _get_members_renewed_ago(
    after_datetime: Optional[datetime.datetime],
    before_datetime: Optional[datetime.datetime]) -> List[sheetdata.Row]:
    """Get the members who were last renewed within the given window.
    Args:
        after_datetime (datetime): Members must have been renewed *after* this
            date. Optional.
        before_datetime (datetime): Members must have been renewed *before*
            this date. Optional.
    Returns:
        List of member rows.
    """

    # Note that dates get returned from the spreadsheet as locale-formatted
    # strings, so we can't do a list-feed query to get just the rows we want.
    # Instead we're going to have to go through the whole set and filter them
    # from there.

    assert after_datetime or before_datetime

    all_rows = sheetdata.find_rows(_S.member, matcher=None)

    results = []

    for row in all_rows:
        renewed_date = row.dict.get(_S.member.fields.renewed.name)

        # Use Joined date if Renewed is empty
        if not renewed_date:
            renewed_date = row.dict.get(_S.member.fields.joined.name)

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

        results.append(row)

    return results
