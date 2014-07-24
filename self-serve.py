# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

"""
This module contains request handlers related to our public-facing
self-registration page and functionality. A big part of this is integration
with Paypal payment processing.
"""


# pylint: disable=E1101,E1103


import os
import logging
import datetime
import pprint

import httplib2
import jinja2
import webapp2
from google.appengine.ext import ndb
import webapp2_extras.json
from google.appengine.api import taskqueue, mail

import config
import helpers
import gapps


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


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__),
                                                'templates')),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class MemberCandidate(ndb.Model):
    """Used to store member info that hasn't yet been confirmed for full
    creation (i.e., they haven't paid yet).
    We will expire and delete these records if they don't get processed.
    """
    member_json = ndb.StringProperty(indexed=False)
    created = ndb.DateTimeProperty(auto_now_add=True)
    expire = ndb.DateTimeProperty()


class SelfJoinPage(helpers.BaseHandler):
    """This is the page that new members will fill out in order to join.
    """

    def get(self):
        """Serve the form page.
        """
        logging.info('SelfJoinPage.GET')
        logging.info('headers: %s' % self.request.headers.items())
        logging.info('params: %s' % self.request.params.items())
        logging.info('body: %s' % self.request.body)

        # Make sure (as best we can) that this is being requested from a site
        # that's allowed to embed our join form.
        # This is such a weak check that I'm not sure it's worth it.
        #if not config.DEBUG:
        #    if not self.request.referer or \
        #       urlparse(self.request.referer).hostname not in config.ALLOWED_EMBED_REFERERS:
        #        webapp2.abort(403, detail='bad referer')

        csrf = helpers.create_csrf_token()

        volunteer_interests = gapps.get_volunteer_interests()

        template_values = {
            'FIELDS': config.FIELDS,
            'csrf': csrf,
            'volunteer_interests': volunteer_interests,
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('self-serve-join.jinja')

        self.response.set_cookie('csrf', csrf, path=self.request.path)
        self.response.write(template.render(template_values))

    def post(self):
        """Create the new member.
        """
        logging.info('SelfJoinPage.POST')
        logging.info('headers: %s' % self.request.headers.items())
        logging.info('params: %s' % self.request.params.items())
        logging.info('body: %s' % self.request.body)

        # Make sure (as best we can) that this is being requested from a site
        # that's allowed to embed our join form.
        # This is such a weak check that I'm not sure it's worth it.
        #if not config.DEBUG:
        #    if not self.request.referer or \
        #       urlparse(self.request.referer).hostname not in config.ALLOWED_EMBED_REFERERS:
        #        webapp2.abort(403, detail='bad referer')

        helpers.check_csrf(self.request)

        # TODO: Don't hardcode key
        referrer = self.request.params.get('_referrer') or self.request.referer

        # Create a dict of the member info.
        new_member = gapps.member_dict_from_request(self.request,
                                                    referrer,
                                                    'join')

        # Write the member info to the member candidate store.
        member_candidate = MemberCandidate(
            member_json=webapp2_extras.json.encode(new_member),
            created=datetime.datetime.now(),
            expire=datetime.datetime.now()+datetime.timedelta(days=1))
        member_candidate_key = member_candidate.put()

        # We put the key value into the URL so we can retrieve this member
        # after payment.
        paypal_url = config.PAYPAL_PAYMENT_URL % (member_candidate_key.urlsafe(),)

        self.response.write(paypal_url)


class PaypalIpnHandler(helpers.BaseHandler):
    """This is the Paypal IPN address. Paypal will make calls to it for various
    events, including and especially a successful payment.
    https://developer.paypal.com/webapps/developer/docs/classic/ipn/gs_IPN/
    """

    def post(self):
        """Serve the form page.
        """
        logging.info('PaypalIpnHandler.POST')
        logging.info('headers: %s' % self.request.headers.items())
        logging.info('params: %s' % self.request.params.items())

        # First check with Paypal to see if this notification is legit
        validation_url = config.PAYPAL_IPN_VALIDATION_URL % (self.request.body,)
        http = httplib2.Http()
        resp, body = http.request(validation_url, method='POST')
        if resp.status != 200 or body != 'VERIFIED':
            # NOT LEGIT
            logging.warning('invalid IPN request')
            logging.warning('%d; %s' % (resp.status, body))
            webapp2.abort(403)

        # Check if this actually represents a payment
        if self.request.params.get('payment_status') != 'Completed':
            # Not a completed payment, but some intermediate event. We don't
            # do anything with these.
            logging.info('IPN with status: %s' % self.request.params.get('payment_status'))
            return  # 200

        # Check if the payment values are valid
        if not self._paypal_txn_values_okay():
            # Alert our admins about this
            subject = 'ALERT: bad values in PayPal transaction'
            body = '''
We received a valid PayPal IPN transaction that contained incorrect or
unexpected values. Specifically, either the recipient email address doesn't
match ours (should be: %s), the value of the transaction was insufficient
(should be: %s), or it was in an incorrect currency (should be: %s).

Here are the transaction values:
%s

Current URL:
%s

[This email was sent automatically.]
''' % (config.PAYPAL_TXN_receiver_email,
       config.PAYPAL_TXN_mc_gross_FLOAT,
       config.PAYPAL_TXN_mc_currency_SET,
       pprint.pformat(self.request.params.items()),
       self.request.host_url)

            mail.send_mail_to_admins(config.MASTER_EMAIL_SEND_ADDRESS,
                                     subject,
                                     body)

            logging.info('IPN had bad values')
            return  # 200


        # Launch a task to actually create or renew the member.
        # We'll pass the Paypal params straight through.
        taskqueue.add(url='/self-serve/process-member-worker',
                      params=self.request.params)

        # return 200

    def _paypal_txn_values_okay(self):
        if self.request.params.get('receiver_email') != config.PAYPAL_TXN_receiver_email:
            return False

        if self.request.params.get('mc_currency') not in config.PAYPAL_TXN_mc_currency_SET:
            return False

        try:
            mc_gross = float(self.request.params.get('mc_gross', '0'))
            if mc_gross < config.PAYPAL_TXN_mc_gross_FLOAT:
                return False
        except ValueError:
            return False

        return True




class ProcessMemberWorker(helpers.BaseHandler):
    """Creates or renews a member when payment has been receieved.
    """

    def post(self):
        payer_email = self.request.params.get('payer_email', '')
        payer_id = self.request.params.get('payer_id', '')
        payer_name = ''
        if self.request.params.get('first_name') and \
           self.request.params.get('last_name'):
            payer_name = '%s %s' % (self.request.params.get('first_name'),
                                    self.request.params.get('last_name'))

        # member_keystring should be considered untrusted. The user could have
        # removed or altered it before Paypal sent it to us. The rest of the
        # values came directly from Paypal (fwiw).
        # This value might also be empty because of an automatic renewal.
        member_keystring = self.request.params.get('invoice', '')

        # There are two scenarios here:
        #  1. This is a brand new member. We have their info in NDB and should
        #     now fully create them in the spreadsheet.
        #  2. This is an automatic renewal payment for an existing member. We
        #     should renew them in the spreadsheet.

        member_dict = {}
        candidate_found = False
        try:
            member_candidate_key = ndb.Key(urlsafe=member_keystring)
            member_candidate = member_candidate_key.get()
            member_candidate_key.delete()

            # Get the member data we stored
            member_dict = webapp2_extras.json.decode(member_candidate.member_json)
            candidate_found = True
            logging.info('found member candidate')
        except:
            logging.info('did not find member candidate')

        # Add the Paypal info, regardless
        member_dict[config.MEMBER_FIELDS.paypal_name.name] = payer_name
        member_dict[config.MEMBER_FIELDS.paypal_email.name] = payer_email
        member_dict[config.MEMBER_FIELDS.paypal_payer_id.name] = payer_id

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
                body = '''
We received a valid PayPal transaction but were unable to match the
transaction to a member. In other words, we got someone's money, and it looks
legit, but we can't figure out who they are in order to actual join or renew
them.

Maybe they're in the spreadsheet under another email address?

Here are the transaction values:
%s

Current URL:
%s

[This email was sent automatically.]
''' % (pprint.pformat(self.request.params.items()),
       self.request.host_url)

                mail.send_mail_to_admins(config.MASTER_EMAIL_SEND_ADDRESS,
                                         subject,
                                         body)

                logging.critical('failed to renew payer')
                return

        # Queue the welcome email
        if join_or_renew == 'renew':
            taskqueue.add(url='/tasks/renew-member-mail', params=member_dict)
            logging.info('renewed member')
            logging.info(member_dict)
        else:
            taskqueue.add(url='/tasks/new-member-mail', params=member_dict)
            logging.info('joined member')
            logging.info(member_dict)


class ExpireMemberCandidates(helpers.BaseHandler):
    """Clean up expired MemberCandidate entries from NDB.
    """
    def get(self):
        logging.debug('ExpireMemberCandidates.get hit')
        now = datetime.datetime.now()
        expireds = MemberCandidate.query(MemberCandidate.expire <= now).fetch()
        if expireds:
            logging.info('Expiring %d MemberCandidate items' % (len(expireds),))
            ndb.delete_multi([expired.key for expired in expireds])


app = webapp2.WSGIApplication([  # pylint: disable=C0103
    ('/self-serve/join', SelfJoinPage),
    ('/self-serve/paypal-ipn', PaypalIpnHandler),
    ('/self-serve/process-member-worker', ProcessMemberWorker),
    ('/self-serve/expire-member-candidates', ExpireMemberCandidates),
], debug=config.DEBUG)
