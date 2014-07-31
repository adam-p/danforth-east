# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

from collections import namedtuple
import logging
import types

import utils

from private import *


DEBUG = True

if not DEBUG:
    ALLOWED_EMAIL_TO_ADDRESSES = None

SCOPE = ['https://spreadsheets.google.com/feeds/',
         'https://www.googleapis.com/auth/drive']

TIMEZONE = 'America/Toronto'

# This is repeated in static/js/common.js
# TODO: Get rid of this duplication. Maybe run our JS files through jinja
# (once -- not on every request).
VOLUNTEER_INTERESTS_DIVIDER = '; '

APP_STATE_NDB_ENTITY_GROUP = 'AppState'


#
# Payment and PayPal info
#

PAYPAL_ACTOR_NAME = 'PAYPAL'

# This is where we send the counter-request to validate IPN notifications.
# NOTE: When testing, make sure this is www.sandbox.paypal.com!
PAYPAL_IPN_VALIDATION_URL = 'https://www.sandbox.paypal.com/cgi-bin/webscr?cmd=_notify-validate&%s'
#PAYPAL_IPN_VALIDATION_URL = 'https://www.paypal.com/cgi-bin/webscr?cmd=_notify-validate&%s'


#
# Spreadsheet field info
#

class Field(object):
    def __init__(self,
                 title,
                 required=False,
                 validator=utils.basic_validator,
                 form_field=True,
                 mutable=True):
        self.title = title
        self.name = utils.title_to_name(title)
        self.required = required
        self.validator = validator
        self.form_field = form_field
        self.mutable = mutable

    def as_dict(self, json_safe):
        res = {}
        for key, val in self.__dict__.items():
            if type(val) is not types.FunctionType:
                res[key] = val

        return res


# TODO: Probably better use classes than namedtuple for these sets of fields
AUTHORIZED_FIELDS = namedtuple('AUTHORIZED_FIELDS',
                               ['id',
                                'created',
                                'created_by',
                                'email',
                                'name'])(
    Field('ID', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Created', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Created By', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Email', True, utils.email_validator),
    Field('Name', True)
)


MEMBER_FIELDS = namedtuple('MEMBER_FIELDS',
                           ['id',
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
                            'other_volunteer_interests',
                            'joined_latlong',
                            'joined_address',
                            'renewed_latlong',
                            'renewed_address',
                            'paypal_name',
                            'paypal_email',
                            'paypal_payer_id',
                            ])(
    Field('ID', validator=lambda *args: True, form_field=True, mutable=False),
    Field('Joined', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Joined By', validator=lambda *args: True, form_field=False, mutable=False),
    Field('Renewed', validator=lambda *args: True, form_field=False),
    Field('Renewed By', validator=lambda *args: True, form_field=False),
    Field('Paid?'),  # This is a form field in managment interface, but not self-serve
    Field('First Name', required=True),
    Field('Last Name', required=True),
    Field('Email', required=True, validator=utils.email_validator),
    Field('Phone Number'),
    Field('Apartment Number'),
    Field('Street Number'),
    Field('Street Name'),
    Field('City'),
    Field('Postal Code'),
    Field('Address LatLong', form_field=False),
    Field('Family Member Names'),
    Field('Join Location'),
    Field('Volunteer Interests'),
    Field('Other Volunteer Interests'),
    Field('Joined LatLong', form_field=False),
    Field('Joined Address', form_field=False),
    Field('Renewed LatLong', form_field=False),
    Field('Renewed Address', form_field=False),
    Field('Paypal Name', form_field=False),
    Field('Paypal Email', form_field=False),
    Field('Paypal Payer ID', form_field=False),
)


VOLUNTEER_FIELDS = namedtuple('VOLUNTEER_FIELDS',
                               ['interest',
                                'email',
                                'name'])(
    Field('Interest', required=True),
    Field('Email', validator=utils.email_validator),
    Field('Name')
)


FIELDS = namedtuple('FIELDS', ['authorized', 'member', 'volunteer'])(
    AUTHORIZED_FIELDS, MEMBER_FIELDS, VOLUNTEER_FIELDS
)


def validate_obj_against_fields(obj, fields):
    """Validates the member data in member. Returns a dict with the proper
    fields on success, or False on failure.
    """

    result = {}

    for field in fields._asdict().values():
        result[field.name] = obj.get(field.name, '')

        if not field.validator(result[field.name], field.required):
            logging.warn('Bad input: %s : %s' % (field.name, result[field.name]))
            return False

    return result


def validate_member(member):
    return validate_obj_against_fields(member, MEMBER_FIELDS)


def fields_to_dict(fields):
    """Returns partial fields information (suitable for JSON encoding).
    """

    res = {}
    for name, field in fields._asdict().items():
        res[name] = field.as_dict(True)

    return res
