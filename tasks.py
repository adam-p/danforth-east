# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

import os
import logging

import webapp2
import jinja2

from google.appengine.ext import ndb

import config
import helpers
import utils
import gapps


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__),
                                                'templates')),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class NewMemberMailWorker(helpers.BaseHandler):

    def post(self):
        logging.info('NewMemberMailWorker hit')
        logging.info(self.request.params.items())

        #
        # Send welcome email
        #

        member_name = '%s %s' % (self.request.POST[config.MEMBER_FIELDS.first_name.name],
                                 self.request.POST[config.MEMBER_FIELDS.last_name.name])
        member_email = self.request.POST[config.MEMBER_FIELDS.email.name]

        with open('templates/tasks/email-new-member-subject.txt', 'r') as subject_file:
            subject = subject_file.read().strip()

        template_values = {
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('tasks/email-new-member.jinja')
        body_html = template.render(template_values)

        gapps.send_email(member_email,
                         member_name,
                         subject,
                         body_html)

        #
        # Send email to volunteer-interest-area reps
        #

        interest_reps = gapps.get_volunteer_interest_reps_for_member(self.request.POST)

        if interest_reps:
            template = JINJA_ENVIRONMENT.get_template('tasks/email-volunteer-interest-rep-subject.jinja')
            subject = template.render({'join_type': 'member'})
            subject = subject.strip()

            for interest, reps in interest_reps.items():
                template_values = {
                    'interest': interest,
                    'member_name': member_name,
                    'member_email': member_email,
                    'join_type': 'member',
                    'config': config,
                }
                template = JINJA_ENVIRONMENT.get_template('tasks/email-volunteer-interest-rep.jinja')
                body_html = template.render(template_values)

                for rep in reps:
                    gapps.send_email(rep.get(config.VOLUNTEER_INTEREST_FIELDS.email.name),
                                     rep.get(config.VOLUNTEER_INTEREST_FIELDS.name.name),
                                     subject,
                                     body_html)


class RenewMemberMailWorker(helpers.BaseHandler):

    def post(self):
        logging.info('RenewMemberMailWorker hit')
        logging.info(self.request.params.items())

        #
        # Send welcome email
        #

        member_name = '%s %s' % (self.request.POST[config.MEMBER_FIELDS.first_name.name],
                                 self.request.POST[config.MEMBER_FIELDS.last_name.name])
        member_email = self.request.POST[config.MEMBER_FIELDS.email.name]

        with open('templates/tasks/email-renew-member-subject.txt', 'r') as subject_file:
            subject = subject_file.read().strip()

        template_values = {
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('tasks/email-renew-member.jinja')
        body_html = template.render(template_values)

        gapps.send_email(member_email,
                         member_name,
                         subject,
                         body_html)


class NewVolunteerMailWorker(helpers.BaseHandler):

    def post(self):
        logging.info('NewVolunteerMailWorker hit')
        logging.info(self.request.params.items())

        #
        # Send welcome email
        #

        member_name = '%s %s' % (self.request.POST[config.VOLUNTEER_FIELDS.first_name.name],
                                 self.request.POST[config.VOLUNTEER_FIELDS.last_name.name])
        member_email = self.request.POST[config.VOLUNTEER_FIELDS.email.name]

        with open('templates/tasks/email-new-volunteer-subject.txt', 'r') as subject_file:
            subject = subject_file.read().strip()

        template_values = {
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('tasks/email-new-volunteer.jinja')
        body_html = template.render(template_values)

        gapps.send_email(member_email,
                         member_name,
                         subject,
                         body_html)

        #
        # Send email to volunteer-interest-area reps
        #

        interest_reps = gapps.get_volunteer_interest_reps_for_member(self.request.POST)

        if interest_reps:
            template = JINJA_ENVIRONMENT.get_template('tasks/email-volunteer-interest-rep-subject.jinja')
            subject = template.render({'join_type': 'volunteer'})
            subject = subject.strip()

            for interest, reps in interest_reps.items():
                template_values = {
                    'interest': interest,
                    'member_name': member_name,
                    'member_email': member_email,
                    'join_type': 'volunteer',
                    'config': config,
                }
                template = JINJA_ENVIRONMENT.get_template('tasks/email-volunteer-interest-rep.jinja')
                body_html = template.render(template_values)

                for rep in reps:
                    gapps.send_email(rep.get(config.VOLUNTEER_INTEREST_FIELDS.email.name),
                                     rep.get(config.VOLUNTEER_INTEREST_FIELDS.name.name),
                                     subject,
                                     body_html)


class Settings(ndb.Model):
    """Used to store app state and settings.
    """

    SINGLETON_DATASTORE_KEY = 'SINGLETON'

    @classmethod
    def singleton(cls):
        return cls.get_or_insert(cls.SINGLETON_DATASTORE_KEY)

    member_sheet_year = ndb.IntegerProperty(
        default=2014,
        verbose_name='The current year of operation. When the calendar year changes, work needs to be done and this gets updated.',
        indexed=False)


class MemberSheetCullWorker(helpers.BaseHandler):
    """Remove defunct members from the members sheet.
    """

    def get(self):
        """This will get hit by cron triggers.
        """
        logging.debug('MemberSheetCullWorker.get hit')
        gapps.cull_members_sheet()

    def post(self):
        """This will get hit by taskqueue calls.
        """
        logging.debug('MemberSheetCullWorker.post hit')
        gapps.cull_members_sheet()


class MemberSheetArchiveWorker(helpers.BaseHandler):
    """Every year we make an archival copy of the current members spreadsheet.
    """

    def get(self):
        logging.debug('MemberSheetArchiveWorker hit')

        settings = Settings.singleton()
        logging.info(settings)

        new_year = gapps.archive_members_sheet(settings.member_sheet_year)
        if new_year:
            settings.member_sheet_year = new_year
            settings.put()


app = webapp2.WSGIApplication([  # pylint: disable=C0103
    ('/tasks/new-member-mail', NewMemberMailWorker),
    ('/tasks/renew-member-mail', RenewMemberMailWorker),
    ('/tasks/new-volunteer-mail', NewVolunteerMailWorker),
    ('/tasks/member-sheet-cull', MemberSheetCullWorker),
    ('/tasks/member-sheet-archive', MemberSheetArchiveWorker),
], debug=config.DEBUG)

