#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Get the sheet keys for our spreadsheets.
"""

import appengine_config

import config
import gapps

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

if __name__ == '__main__':
    print('MEMBERS_WORKSHEET_KEY = %s' % (gapps._get_first_worksheet_id(config.MEMBERS_SPREADSHEET_KEY),))
    print('AUTHORIZED_WORKSHEET_KEY = %s' % (gapps._get_first_worksheet_id(config.AUTHORIZED_SPREADSHEET_KEY),))
    print('VOLUNTEER_WORKSHEET_KEY = %s' % (gapps._get_first_worksheet_id(config.VOLUNTEER_SPREADSHEET_KEY),))
