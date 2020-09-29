# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
Functions for sending email. Uses Sendgrid.

This file is named "emailer" rather than "email" because that name causes the sendgrid
library to fail. See https://github.com/sendgrid/sendgrid-python/issues/586
"""

from typing import Tuple, Optional, Union
import os
import logging
import config
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, Subject, PlainTextContent, HtmlContent, SendGridException
import html2text


def send(recipients: Union[Tuple[Tuple[str, str]], Tuple[str, str]], subject: str, body_html: Optional[str], body_text: str) -> bool:
    """Send an email from the configured address.
    `recipients` is a list of tuples like `[(address, name),...]` or just a single
    tuple like `(address, name)`.
    Does not check for address validity.
    If `body_text` is None, it will be derived from `body_html`.
    if `body_html` is None but `body_text` is provided, no HTML part will be sent.
    Returns True on success, false otherwise. Does not throw exception.
    """

    if config.DEMO:
        # Emails to users are disabled to prevent abuse.
        return True

    if not recipients:
        return True

    if isinstance(recipients[0], str):
        # We were passed just `(address, name)`.s
        recipients = [recipients]

    if not body_text and not body_html:
        raise Exception('emailer.send: body_text or body_html must be provided')
    elif body_html and not body_text:
        h2t = html2text.HTML2Text()
        h2t.body_width = 0
        body_text = h2t.handle(body_html)

    sg = SendGridAPIClient(api_key=config.SENDGRID_API_KEY)

    to = []
    for r in recipients:
        to.append(To(r[0], r[1]))

    message = Mail(from_email=From(config.MASTER_EMAIL_SEND_ADDRESS, name=config.MASTER_EMAIL_SEND_NAME),
                   to_emails=to,
                   subject=Subject(subject),
                   plain_text_content=PlainTextContent(body_text),
                   html_content=HtmlContent(body_html) if body_html else None)

    response = sg.client.mail.send.post(request_body=message.get())

    if response.status_code not in (200, 202):
        # The expected response code is actually 202, but not checking for 200 as well feels weird.
        logging.error(f"emailer.send fail: {response.status_code} | {response.body} | {response.headers}")
        return False

    # Body is expected to be empty on success, but we'll check it anyway.
    logging.info(f"emailer.send success: {response.status_code} | {response.body}")
    return True


def send_to_admins(subject: str, body_text: str) -> bool:
    """Send an email to the configured admin(s).
    """
    return send((config.MASTER_EMAIL_SEND_ADDRESS, config.MASTER_EMAIL_SEND_NAME),
                subject, None, body_text)


# WARNING: Untested.
class SendgridHandler(logging.StreamHandler):
    app_id = os.getenv('GAE_APPLICATION')

    def emit(self, record):
        if record.level < logging.ERROR:
            return

        msg = self.format(record)
        send_to_admins(
            f'{self.app_id} ERROR',
            msg)
