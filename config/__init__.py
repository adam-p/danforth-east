# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : https://adampritchard.mit-license.org/
#

from typing import NamedTuple
from collections import namedtuple
import logging
import types
import os

import utils

from .private import *


# DO NOT forget to set this to False when deploying for real.
# When it is True, some security checks are skipped.
DEBUG = False

# Set to true if you want to set up a public demo.
# It prevents auth checks and doesn't send email.
DEMO = False

try:
    import overrides
    DEMO = overrides.DEMO
except:
    pass

#
# Project config and environment
#

PROJECT_NAME = os.getenv('GOOGLE_CLOUD_PROJECT')
# You can find this out for you project by using `gcloud app describe` and looking here:
# https://cloud.google.com/compute/docs/regions-zones#locations
PROJECT_REGION = 'us-central1'

# This needs to have been created with `gcloud tasks queues create {name}`.
# (AFAIK, the name isn't important, so you don't actually need to change it.)
TASK_QUEUE_NAME = 'mmbrmgmt-task-queue'

TIMEZONE = 'America/Toronto'

# This is repeated in static/js/common.js
# TODO: Get rid of this duplication. Maybe run our JS files through jinja (once -- not on every request).
MULTIVALUE_DIVIDER = '; '


#
# Payment and PayPal info
#

PAYPAL_ACTOR_NAME = 'PAYPAL'

# This is where we send the counter-request to validate IPN notifications.
# NOTE: When testing, make sure this is www.sandbox.paypal.com!
PAYPAL_IPN_VALIDATION_URL = 'https://ipnpb.paypal.com/cgi-bin/webscr?cmd=_notify-validate&%s'
#PAYPAL_IPN_VALIDATION_URL = 'https://ipnpb.sandbox.paypal.com/cgi-bin/webscr?cmd=_notify-validate&%s'


#
# Spreadsheet archive date
#

# Once a year the members spreadsheet gets copied into an "archive" document,
# for historical reference. This is the day on which that happens.
# Tip: Don't pick a leap year day.
MEMBER_SHEET_ARCHIVE_MONTH = 11
MEMBER_SHEET_ARCHIVE_DAY = 1


#
# Spreadsheet field info
#

class Field(object):
    def __init__(self,
                 name,
                 required=False,
                 is_id=False,
                 validator=utils.basic_validator,
                 form_field=True,
                 mutable=True,
                 values=None,
                 mailchimp_merge_tag=None):
        self.name = name
        self.is_id = is_id
        self.required = required
        self.validator = validator
        self.form_field = form_field
        self.mutable = mutable
        self.values = values
        self.mailchimp_merge_tag = mailchimp_merge_tag

    def as_dict(self, json_safe):
        res = {}
        for key, val in self.__dict__.items():
            if type(val) is not types.FunctionType:
                res[key] = val

        return res


class Spreadsheet(object):
    def __init__(self,
                 spreadsheet_id: str,
                 worksheet_title: str,
                 worksheet_id: int,
                 fields: NamedTuple):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_title = worksheet_title
        self.worksheet_id = worksheet_id
        self.fields = fields

    def id_field(self):
        f = [f for f in self.fields if f.is_id]
        if not f:
            raise Exception('Spreadsheet has no ID field')
        return f[0]


AUTHORIZED_SHEET = Spreadsheet(AUTHORIZED_SPREADSHEET_ID,
                               AUTHORIZED_WORKSHEET_TITLE,
                               AUTHORIZED_WORKSHEET_ID,
                               namedtuple('AUTHORIZED_FIELDS', [
                                'id',
                                'created',
                                'created_by',
                                'email',
                                'name'])(
    Field('ID', is_id=True, validator=lambda *args: True, form_field=False, mutable=False),
    Field('Created', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Created By', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Email', required=True, validator=utils.email_validator),
    Field('Name', required=True)
))

MEMBER_SHEET = Spreadsheet(MEMBERS_SPREADSHEET_ID,
                           MEMBERS_WORKSHEET_TITLE,
                           MEMBERS_WORKSHEET_ID,
                           namedtuple('MEMBER_FIELDS', [
                                'id',
                                'joined',
                                'joined_by',
                                'renewed',
                                'renewed_by',
                                'paid',
                                'first_name',
                                'last_name',
                                'email',
                                'phone_num',
                                'apt_num',
                                'street_num',
                                'street_name',
                                'city',
                                'postal_code',
                                'address_latlong',
                                'family_names',
                                'join_location',
                                'volunteer_interests',
                                'skills',
                                'joined_latlong',
                                'joined_address',
                                'renewed_latlong',
                                'renewed_address',
                                'paypal_name',
                                'paypal_email',
                                'paypal_payer_id',
                                'paypal_auto_renewing',
                                'paid_amount',
                                'mailchimp_updated',
                            ])(
    Field('ID', is_id=True, validator=lambda *args: True, form_field=True, mutable=False),
    Field('Joined', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Joined By', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Renewed', validator=lambda *args: True, form_field=False),
    Field('Renewed By', validator=lambda *args: True, form_field=False),
    Field('Paid?'),  # This is a form field in managment interface, but not self-serve
    Field('First Name', required=True, mailchimp_merge_tag='FNAME'),
    Field('Last Name', required=True, mailchimp_merge_tag='LNAME'),
    Field('Email', required=True, validator=utils.email_validator),  # We don't use a mailchimp_merge_tag for this
    Field('Phone Number'),
    Field('Apartment Number'),
    Field('Street Number', required=True),
    Field('Street Name', required=True),
    Field('City', required=True),
    Field('Postal Code', required=True),
    Field('Address LatLong', form_field=False),
    Field('Family Member Names'),
    Field('Join Location'),
    Field('Volunteer Interests', mailchimp_merge_tag='VOLUNTEER'),
    Field('Skills', mailchimp_merge_tag='SKILLS'),
    Field('Joined LatLong', form_field=False),
    Field('Joined Address', form_field=False),
    Field('Renewed LatLong', form_field=False),
    Field('Renewed Address', form_field=False),
    Field('Paypal Name', form_field=False),
    Field('Paypal Email', form_field=False),
    Field('Paypal Payer ID', form_field=False),
    Field('Paypal Auto-Renewing', form_field=False),
    Field('Paid Amount', form_field=False),
    Field('MailChimp Updated', form_field=False),
))


VOLUNTEER_SHEET = Spreadsheet(VOLUNTEERS_SPREADSHEET_ID,
                              VOLUNTEERS_WORKSHEET_TITLE,
                              VOLUNTEERS_WORKSHEET_ID,
                               namedtuple('VOLUNTEER_FIELDS', [
                                'id',
                                'joined',
                                'joined_by',
                                'first_name',
                                'last_name',
                                'email',
                                'phone_num',
                                'apt_num',
                                'street_num',
                                'street_name',
                                'city',
                                'postal_code',
                                'address_latlong',
                                'join_location',
                                'volunteer_interests',
                                'skills',
                                'joined_latlong',
                                'joined_address',
                                'mailchimp_updated',
                               ])(
    Field('ID', is_id=True, validator=lambda *args: True, form_field=True, mutable=False),
    Field('Joined', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Joined By', validator=lambda *args: True, form_field=False, mutable=False),
    Field('First Name', required=True, mailchimp_merge_tag='FNAME'),
    Field('Last Name', required=True, mailchimp_merge_tag='LNAME'),
    Field('Email', required=True, validator=utils.email_validator),  # We don't use a mailchimp_merge_tag for this
    Field('Phone Number'),
    Field('Apartment Number'),
    Field('Street Number', required=True),
    Field('Street Name', required=True),
    Field('City', required=True),
    Field('Postal Code', required=True),
    Field('Address LatLong', form_field=False),
    Field('Join Location'),
    Field('Volunteer Interests', mailchimp_merge_tag='VOLUNTEER'),
    Field('Skills', mailchimp_merge_tag='SKILLS'),
    Field('Joined LatLong', form_field=False),
    Field('Joined Address', form_field=False),
    Field('MailChimp Updated', form_field=False),
))


VOLUNTEER_INTERESTS_SHEET = Spreadsheet(VOLUNTEER_INTERESTS_SPREADSHEET_ID,
                                        VOLUNTEER_INTERESTS_WORKSHEET_TITLE,
                                        VOLUNTEER_INTERESTS_WORKSHEET_ID,
                                        namedtuple('VOLUNTEER_INTERESTS_FIELDS', [
                                            'interest',
                                            'email',
                                            'name'])(
    Field('Interest', required=True),
    Field('Email', validator=utils.email_validator),
    Field('Name'),
))


SKILLS_CATEGORIES_SHEET = Spreadsheet(SKILLS_CATEGORIES_SPREADSHEET_ID,
                                      SKILLS_CATEGORIES_WORKSHEET_TITLE,
                                      SKILLS_CATEGORIES_WORKSHEET_ID,
                                      namedtuple('SKILLS_CATEGORIES_FIELDS', [
                                        'category'])(
    Field('Category', required=True),
))


SHEETS = namedtuple('SHEETS', ['authorized', 'member',
                               'volunteer_interest', 'volunteer',
                               'skills_category'])(
    AUTHORIZED_SHEET, MEMBER_SHEET,
    VOLUNTEER_INTERESTS_SHEET, VOLUNTEER_SHEET,
    SKILLS_CATEGORIES_SHEET
)


def validate_obj_against_fields(obj: dict, fields: NamedTuple) -> dict:
    """Validates the object, possibly with partial fields, against the field data.
    Returns a dict with the proper fields on success, or False on failure.
    """
    result = {}

    for field in fields._asdict().values():
        # It's important to default to None here. When we update a row in the spreadsheet,
        # None (null) is interpreted as "leave the existing value". If we defaulted to '',
        # the value in the sheet would be replaced.
        result[field.name] = obj.get(field.name, None)

        if not field.validator(result[field.name], field.required):
            logging.warn('Bad input: %s : %s' % (field.name, result[field.name]))
            return False

    return result


def validate_member(member: dict) -> dict:
    """Validates the given member dict, possibly with partial fields.
    Returns a dict with the proper fields on success, or False on failure.
    """
    return validate_obj_against_fields(member, SHEETS.member.fields)


def validate_volunteer(member: dict) -> dict:
    """Validates the given volunteer dict, possibly with partial fields.
    Returns a dict with the proper fields on success, or False on failure.
    """
    return validate_obj_against_fields(member, SHEETS.volunteer.fields)


def fields_to_dict(fields: NamedTuple) -> dict:
    """Returns partial fields information (suitable for JSON encoding).
    """

    res = {}
    for name, field in fields._asdict().items():
        res[name] = field.as_dict(True)

    return res
