#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : https://adampritchard.mit-license.org/
#

"""
Get the sheet keys for our spreadsheets.
These are otherwise kind of a hassle to figure out.
"""

import config
import sheetdata

if __name__ == "__main__":
    member_props = sheetdata.get_first_sheet_properties(config.SHEETS.member.id)
    print(f"MEMBERS_WORKSHEET_TITLE = '{member_props['title']}'")
    print(f"MEMBERS_WORKSHEET_ID = {member_props['id']}")
    print('')

    authorized_props = sheetdata.get_first_sheet_properties(config.SHEETS.authorized.id)
    print(f"AUTHORIZED_WORKSHEET_TITLE = '{authorized_props['title']}'")
    print(f"AUTHORIZED_WORKSHEET_ID = {authorized_props['id']}")
    print('')

    volunteer_interest_props = sheetdata.get_first_sheet_properties(config.SHEETS.volunteer_interest.id)
    print(f"VOLUNTEER_INTERESTS_WORKSHEET_TITLE = '{volunteer_interest_props['title']}'")
    print(f"VOLUNTEER_INTERESTS_WORKSHEET_ID = {volunteer_interest_props['id']}")
    print('')

    volunteer_props = sheetdata.get_first_sheet_properties(config.SHEETS.volunteer.id)
    print(f"VOLUNTEERS_WORKSHEET_TITLE = '{volunteer_props['title']}'")
    print(f"VOLUNTEERS_WORKSHEET_ID = {volunteer_props['id']}")
    print('')

    skills_category_props = sheetdata.get_first_sheet_properties(config.SHEETS.skills_category.id)
    print(f"SKILLS_CATEGORIES_WORKSHEET_TITLE = '{skills_category_props['title']}'")
    print(f"SKILLS_CATEGORIES_WORKSHEET_ID = {skills_category_props['id']}")
