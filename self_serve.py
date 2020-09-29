# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
This module contains request handlers related to our public-facing
self-registration page and functionality. A big part of this is integration
with Paypal payment processing.
"""

from __future__ import annotations
import logging
import datetime
from urllib.parse import urlparse
import pprint
import requests
import flask
from google.cloud import ndb

import config
import helpers
import gapps
import emailer
import main


'''
This is the flow, mostly as it regards Paypal subscriptions:

1. Our member form gets loaded in an iframe on the DECA main site.
   - Same form for create and renew. We'll use email match to decide which to do.

2. User fills form, indicating payment preference, and clicks submit.
   - For now our flow only includes the Paypal payment preference.

3. Form JS sends AJAX POST to our server with user data.

4. Server generates "invoice" token for request. Stores token and user data in
   NDB. Creates Paypal URL that includes the "invoice" values. Responds 200
   with Paypal URL in body.

5. Form JS sets `window.top.location` to Paypal URL. Page redirects there.

6a. User completes the Paypal process successfully.
    - At this point the user probably goes back to the DECA main site for thanks.

7. Our server gets a Paypal IPN request indicating the payment is complete.
   This request includes our "invoice" token.
   - Renewal variation: when a subsequent automatic Paypal payment is made, we
     will receive a IPN that it occured, but there will be no "invoice" value.
     (I think. Haven't seen it happen yet.) We will use the payer ID to
     renew the correct member.

8. Our server does the counter-request to Paypal to ensure authenticity of the
   IPN request.

9a. IPN counter-request is successful.

10. We will send a taskqueue request to ourselves with the token and some of
    the Paypal payer info (the payer ID, in particular).

11. Server taskqueue handler uses the invoice token to retrieve (and remove)
    the user data in NDB.
    - If the member info is not found in NDB, attempt to use Paypal email to
      find correct member.

12. Server creates (or renews) the user. (And starts the welcome email process.)

13. The end.

--

6b. User does *not* complete the Paypal process successfully.

7. Server expires the user data in NDB after some amount of time.

8. The end.

--

9b. IPN counter-request is *not* successful.

10. Our server does not proceed.

11. If there is actually any real user data associated with the IPN request
    (which there probably isn't, because someone is messing with us), it will
    expire in NDB after some amount of time.

12. The end.

'''


self_serve = flask.Blueprint('self_serve', __name__)

# TODO: Flask-WTF CSRF check is sometimes failing, even though the form field and the
# header are obviously present. I'm going to disable that check and leave the additional
# checks in place.
main.csrf.exempt(self_serve)

self_serve.before_request(main.additional_csrf_checks)

# This will be set by the JavaScript in common.js
_EMBEDDER_VALUE_KEY = '_embedder'

_PAYMENT_METHOD_VALUE_KEY = 'payment_method'


class MemberCandidate(ndb.Model):
    """Used to store member info that hasn't yet been confirmed for full
    creation (i.e., they haven't paid yet).
    We will expire and delete these records if they don't get processed.
    """
    member_json = ndb.StringProperty()
    created = ndb.DateTimeProperty(auto_now_add=True)
    expire = ndb.DateTimeProperty()

    _ndb_client = ndb.Client()

    @classmethod
    def pop(cls, keystring: str) -> MemberCandidate:
        """Fetch and remove from the datastore the member candidate at `keystring.`
        """
        with cls._ndb_client.context():
            member_candidate_key = ndb.Key(urlsafe=keystring)
            member_candidate = member_candidate_key.get()
            member_candidate_key.delete()
            return member_candidate

    @classmethod
    def clear_expireds(cls) -> int:
        """Remove all member candidiates from the datastore that have expired.
        Returns the count of records removed.
        """
        now = datetime.datetime.now()
        with cls._ndb_client.context():
            expireds = MemberCandidate.query(MemberCandidate.expire <= now).fetch()
            if not expireds:
                return 0
            ndb.delete_multi([expired.key for expired in expireds])
            return len(expireds)

    def store(self):
        """Store the current member candidate object in the datastore.
        """
        with self._ndb_client.context():
            return self.put()


@self_serve.before_request
def check_request_embedder():
    """Checks if the page embedding our form is allowed. Calls flask.abort(403) if it's not.
    Called before every request in this blueprint.

    Note that the referrer is sometimes not available, depending on browser and embedder
    settings. If you need to embed in a site that has the `Referrer-Policy: no-referrer`
    set, you will need to change this check to allow blank referrer. But note that this
    means that anyone can embed these forms.
    """
    if config.DEBUG:
        logging.warning('self_serve.check_request_embedder: skipping check due to DEBUG=True')
        return

    if flask.request.method == 'POST':
        # When our embedded page is posting its form, it includes a field that indicates
        # the referrer of the page it's embedded in.
        embedder = urlparse(flask.request.values.get(_EMBEDDER_VALUE_KEY))
    else: # GET
        # When our embedded page is initially being retrieved, we need to look at the
        # `Referer` header.
        embedder = urlparse(flask.request.referrer)

    if not embedder.scheme or not embedder.hostname:
        logging.warning('self_serve.check_request_embedder: got empty embedder: %s', list(flask.request.values.items()))
        flask.abort(403, description='missing embed origin')

    embedder_origin = f'{embedder.scheme}://{embedder.hostname}'
    if embedder.port:
        embedder_origin += f':{embedder.port}'

    if embedder_origin not in config.SELF_SERVE_ALLOWED_EMBED_ORIGINS:
        logging.warning('self_serve.check_request_embedder: embedder_origin "%s" not in SELF_SERVE_ALLOWED_EMBED_ORIGINS "%s"', embedder_origin, config.SELF_SERVE_ALLOWED_EMBED_ORIGINS)
        flask.abort(403, description='bad embed origin')

@self_serve.route('/self-serve/join', methods=['GET'])
def join():
    """This is the page that new members will fill out in order to join.
    """
    logging.info('self_serve.join')
    logging.info('headers: %s', list(flask.request.headers.items()))
    logging.info('values: %s', list(flask.request.values.items()))

    volunteer_interests = gapps.get_volunteer_interests()
    skills_categories = gapps.get_skills_categories()

    resp = flask.make_response(flask.render_template(
        'self-serve-join.jinja',
        app_config=config,
        volunteer_interests=volunteer_interests,
        skills_categories=skills_categories))

    return resp

@self_serve.route('/self-serve/join', methods=['POST'])
def submit_join():
    """Handle submission of the embedded member self-registration form.
    """
    logging.info('self_serve.submit_join')
    logging.info('headers: %s', list(flask.request.headers.items()))
    logging.info('values: %s', list(flask.request.values.items()))

    referrer = flask.request.values.get(_EMBEDDER_VALUE_KEY) or flask.request.referrer or flask.request.origin

    # Create a dict of the member info.
    new_member = gapps.member_dict_from_request(flask.request,
                                                referrer,
                                                'join')

    # "Paid" field shouldn't be set by form in self-serve.
    new_member[config.SHEETS.member.fields.paid.name] = 'N'
    if flask.request.values.get(_PAYMENT_METHOD_VALUE_KEY) == 'paypal':
        new_member[config.SHEETS.member.fields.paid.name] = 'paypal'

    # Write the member info to the member candidate store.
    # This will be retrieved for processing by process_member_worker()
    member_candidate = MemberCandidate(
        member_json=flask.json.dumps(new_member),
        created=datetime.datetime.now(),
        expire=datetime.datetime.now()+datetime.timedelta(days=1))
    member_candidate_key = member_candidate.store()

    invoice_id = member_candidate_key.urlsafe().decode('ascii')

    # If the payment method is "cheque" create the new member directly,
    # otherwise start the PayPal process.
    if flask.request.values.get(_PAYMENT_METHOD_VALUE_KEY) == 'cheque':
        params = {'invoice': invoice_id}
        gapps.enqueue_task('/self-serve/process-member-worker', params)
        return 'success'

    logging.debug('self_serve.submit_join: awaiting PayPal IPN')

    # We put the key value into the URL so we can retrieve this member
    # after payment.
    paypal_url = config.PAYPAL_PAYMENT_URL % (invoice_id,)

    # If this is the demo server, then we skip PayPal and just create the user.
    if config.DEMO:
        params = {
            'payer_email': new_member.get(config.SHEETS.member.fields.email.name),
            'payer_id': 'FAKE-ID',
            'first_name': new_member.get(config.SHEETS.member.fields.first_name.name),
            'last_name': new_member.get(config.SHEETS.member.fields.last_name.name),
            'invoice': invoice_id,
        }
        gapps.enqueue_task('/self-serve/process-member-worker', params)
        return 'demo'

    # Write the URL in the response so it can be shown to the user for follow-up
    return paypal_url

@self_serve.route('/self-serve/volunteer', methods=['GET'])
def volunteer():
    """This is the page that new volunteers will fill out in order to join.
    """
    logging.info('self_serve.volunteer')
    logging.info('headers: %s', list(flask.request.headers.items()))
    logging.info('values: %s', list(flask.request.values.items()))

    volunteer_interests = gapps.get_volunteer_interests()
    skills_categories = gapps.get_skills_categories()

    resp = flask.make_response(flask.render_template(
        'self-serve-volunteer.jinja',
        app_config=config,
        volunteer_interests=volunteer_interests,
        skills_categories=skills_categories))

    return resp

@self_serve.route('/self-serve/volunteer', methods=['POST'])
def submit_volunteer():
    """Handle submission of the embedded volunteer self-registration form.
    """
    logging.info('self_serve.submit_volunteer')
    logging.info('headers: %s', list(flask.request.headers.items()))
    logging.info('values: %s', list(flask.request.values.items()))

    referrer = flask.request.values.get(_EMBEDDER_VALUE_KEY) or flask.request.referrer or flask.request.origin

    # Create a dict of the volunteer info.
    new_volunteer = gapps.volunteer_dict_from_request(flask.request,
                                                      referrer)

    gapps.join_volunteer_from_dict(new_volunteer)

    # Enqueue the welcome email
    gapps.enqueue_task('/tasks/new-volunteer-mail', new_volunteer)

    return 'success'

@self_serve.route('/self-serve/combo', methods=['GET'])
def combo():
    """This page has multiple registration types on it (i.e., member and
    volunteer).
    """
    logging.info('self_serve.combo')
    logging.info('headers: %s', list(flask.request.headers.items()))
    logging.info('values: %s', list(flask.request.values.items()))

    volunteer_interests = gapps.get_volunteer_interests()
    skills_categories = gapps.get_skills_categories()

    resp = flask.make_response(flask.render_template(
        'self-serve-combo.jinja',
        app_config=config,
        volunteer_interests=volunteer_interests,
        skills_categories=skills_categories))

    return resp


# Use a different blueprint for tasks related to self-serve pages. This allows us to
# exclude them from CSRF and embedder checks, for example.
self_serve_tasks = flask.Blueprint('self_serve_tasks', __name__)

# These aren't routes submitted to by users, and there are checks to ensure that.
main.csrf.exempt(self_serve_tasks)

@self_serve_tasks.route('/self-serve/process-member-worker', methods=['POST'])
def process_member_worker():
    """Creates or renews a member when payment has been received.
    """
    logging.debug('self_serve.process_member_worker hit')

    params = gapps.validate_queue_task(flask.request)

    payer_email = params.get('payer_email', '')
    payer_id = params.get('payer_id', '')
    payer_name = ''
    if params.get('first_name') and params.get('last_name'):
        payer_name = f"{params.get('first_name')} {params.get('last_name')}"

    # member_keystring should be considered untrusted. The user could have
    # removed or altered it before Paypal sent it to us. The rest of the
    # values came directly from Paypal (fwiw).
    # This value might also be empty because of an automatic renewal.
    member_keystring = params.get('invoice', '')

    # There are two scenarios here:
    #  1. This is a brand new member. We have their info in NDB and should
    #     now fully create them in the spreadsheet.
    #  2. This is an automatic renewal payment for an existing member. We
    #     should renew them in the spreadsheet.

    member_dict = {}
    candidate_found = False
    try:
        member_candidate = MemberCandidate.pop(member_keystring)

        # Get the member data we stored
        member_dict = flask.json.loads(member_candidate.member_json)
        candidate_found = True
        logging.info('found member candidate')
    except:
        logging.info('did not find member candidate')

    # Add the Paypal info, regardless
    member_dict[config.SHEETS.member.fields.paypal_name.name] = payer_name
    member_dict[config.SHEETS.member.fields.paypal_email.name] = payer_email
    member_dict[config.SHEETS.member.fields.paypal_payer_id.name] = payer_id

    join_or_renew = 'renew'

    if candidate_found:
        join_or_renew = gapps.join_or_renew_member_from_dict(member_dict)
    else:
        #
        # Renew an existing member.
        # We will try to find an existing user by looking up the payer_email
        # value in either the "Paypal Email" field or the "Email" field.
        #

        renew_success = gapps.renew_member_by_email_or_paypal_id(
                                payer_email,
                                payer_id,
                                member_dict)

        if not renew_success:
            # We failed to renew this paying member.
            # Alert our admins about this.
            subject = 'ALERT: failed to renew valid payer'
            body = f'''
We received a valid PayPal transaction but were unable to match the \
transaction to a member. In other words, we got someone's money, and it looks \
legit, but we can't figure out who they are in order to actually join or renew \
them.

Maybe they're in the spreadsheet under another email address?

Here are the transaction values:
{pprint.pformat(list(params))}

Current URL:
{flask.request.path}

[This email was sent automatically.]
'''

            emailer.send_to_admins(subject, body)

            logging.critical('failed to renew payer')
            return flask.make_response('', 200)

    # Enqueue the welcome email
    if join_or_renew == 'renew':
        gapps.enqueue_task('/tasks/renew-member-mail', member_dict)
        logging.info('renewed member')
        logging.info(member_dict)
    else:
        gapps.enqueue_task('/tasks/new-member-mail', member_dict)
        logging.info('joined member')
        logging.info(member_dict)

    return flask.make_response('', 200)

@self_serve_tasks.route('/self-serve/expire-member-candidates')
def expire_member_candidates():
    """This is a cron job that removes any expired member candidates from NDB.
    This is not expected to ever find anything to delete, as there's no reason
    for them to not be successfully processed and removed.
    (But if they haven't been successfully processed after a day, they're not
    going to be, and we don't want stuff in our datastore that will be never removed.)
    """
    logging.debug('self_serve.expire_member_candidates hit')
    gapps.validate_cron_task(flask.request)
    num_expired = MemberCandidate.clear_expireds()
    logging.info(f'Expiring {num_expired} MemberCandidate items')
    return flask.make_response('', 200)

@self_serve_tasks.route('/self-serve/paypal-ipn', methods=['POST'])
def paypal_ipn():
    """This is the Paypal IPN address. Paypal will make calls to it for various
    events, including and especially a successful payment.
    https://developer.paypal.com/webapps/developer/docs/classic/ipn/gs_IPN/
    """

    logging.info('self_serve_tasks.paypal_ipn')
    logging.info('self_serve_tasks.paypal_ipn: headers: %s', list(flask.request.headers.items()))

    # get_data MUST be called before accessing the form fields, or else the data won't
    # be available. https://flask.palletsprojects.com/en/1.1.x/api/#flask.Request.get_data
    req_data = flask.request.get_data(as_text=True)
    logging.info('self_serve_tasks.paypal_ipn: values: %s', list(flask.request.values.items()))

    # First check with Paypal to see if this notification is legit
    validation_url = config.PAYPAL_IPN_VALIDATION_URL % req_data
    validation_response = requests.post(validation_url)
    if validation_response.status_code != 200 or validation_response.text != 'VERIFIED':
        # NOT LEGIT
        logging.warning('self_serve_tasks.paypal_ipn: invalid IPN request; %d; %s', validation_response.status_code, validation_response.text)
        flask.abort(403)

    # Check if this actually represents a payment
    if flask.request.values.get('payment_status') != 'Completed':
        # Not a completed payment, but some intermediate event. We don't
        # do anything with these.
        logging.info('self_serve_tasks.paypal_ipn: rejecting IPN with status: %s',
                     flask.request.values.get('payment_status'))
        return flask.make_response('', 200)

    # Check if this is a membership payment. We want to ignore any other kind of payment.
    if flask.request.values.get('item_name') != config.PAYPAL_TXN_item_name:
        logging.info('self_serve_tasks.paypal_ipn: rejecting IPN with item_name: %s; %s',
                     flask.request.values.get('item_name'), list(flask.request.values.items()))
        return flask.make_response('', 200)

    # Check if the payment values are valid
    if flask.request.values.get('receiver_email') != config.PAYPAL_TXN_receiver_email:
        # Alert our admins about this
        subject = 'ALERT: bad values in PayPal transaction'
        body = f'''
We received a valid PayPal IPN transaction that contained incorrect or
unexpected values. Specifically, the PayPal recipient email address doesn't
match ours; should be '{config.PAYPAL_TXN_receiver_email}', got '{flask.request.values.get('receiver_email')}'.

Here are the transaction values:
{pprint.pformat(list(flask.request.values.items()))}

Current URL:
{flask.request.full_path}

[This email was sent automatically.]
'''
        emailer.send_to_admins(subject, body)

        logging.info('self_serve_tasks.paypal_ipn: IPN had bad values')
        return flask.make_response('', 200)

    logging.info('self_serve_tasks.paypal_ipn: IPN validated, enqueuing process-member-worker')

    # Launch a task to actually create or renew the member.
    # We'll pass the Paypal params straight through.
    gapps.enqueue_task('/self-serve/process-member-worker', dict(flask.request.values))

    return flask.make_response('', 200)
