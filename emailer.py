# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
Functions for sending email. Uses SMTP.
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.headerregistry import Address

import html2text
import logging
from typing import Optional, Tuple, Union
import config


def send(
        recipients: Union[Tuple[Tuple[str, str]], Tuple[str, str]],
        subject: str,
        body_html: Optional[str],
        body_text: str) -> bool:
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

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = str(Address(display_name=config.MASTER_EMAIL_SEND_NAME, addr_spec=config.MASTER_EMAIL_ADDRESS))
    msg['To'] = ', '.join([str(Address(display_name=r[1], addr_spec=r[0])) for r in recipients])

    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype='html')

    context = ssl.create_default_context()
    try:
        # Note that using SMTP_SSL here, rather than SMTP+starttls, results in an error: `ssl.SSLError: [SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1131)`
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(config.MASTER_EMAIL_ADDRESS, config.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        logging.error(f"emailer.send fail: {e}")
        return False

    logging.info(f"emailer.send success")
    return True


def send_to_admins(subject: str, body_text: str) -> bool:
    """Send an email to the configured admin(s).
    """
    return send((config.MASTER_EMAIL_ADDRESS, config.MASTER_EMAIL_SEND_NAME),
                subject, None, body_text)
