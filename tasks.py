# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
Flask routes used by tasks queues and cron jobs
"""

import logging
import flask
from google.cloud import ndb

import config
import gapps
import emailer
import main


tasks = flask.Blueprint('tasks', __name__)

# These aren't routes submitted to by users, and there are checks to ensure that.
main.csrf.exempt(tasks)



@tasks.route('/tasks/new-member-mail', methods=['POST'])
def new_member_mail():
    """Queue task invoked when a member has been newly registered.
    Sends appropriate welcome emails.
    """
    logging.info('tasks.new_member_mail hit')

    member_dict = gapps.validate_queue_task(flask.request)
    logging.info(member_dict)

    #
    # Send welcome email
    #

    member_name = '%s %s' % (member_dict[config.SHEETS.member.fields.first_name.name],
                                member_dict[config.SHEETS.member.fields.last_name.name])
    member_email = member_dict[config.SHEETS.member.fields.email.name]

    with open('templates/tasks/email-new-member-subject.txt', 'r') as subject_file:
        subject = subject_file.read().strip()

    body_html = flask.render_template(
        'tasks/email-new-member.jinja',
        app_config=config)

    if not emailer.send((member_email, member_name), subject, body_html, None):
        # Log and carry on
        logging.error(f'failed to send new-member email to {member_email}')
    else:
        logging.info(f'sent new-member email to {member_email}')

    #
    # Send email to volunteer-interest-area reps
    #

    interest_reps = gapps.get_volunteer_interest_reps_for_member(member_dict)

    if interest_reps:
        subject = flask.render_template(
            'tasks/email-volunteer-interest-rep-subject.jinja',
            app_config=config,
            join_type='member').strip()

        for interest, reps in interest_reps.items():
            body_html = flask.render_template(
                'tasks/email-volunteer-interest-rep.jinja',
                app_config=config,
                join_type='member',
                interest=interest,
                member_name=member_name,
                member_email=member_email)

            for rep in reps:
                rep_email = rep.get(config.SHEETS.volunteer_interest.fields.email.name)
                rep_name = rep.get(config.SHEETS.volunteer_interest.fields.name.name)
                ok = emailer.send(
                        (rep_email, rep_name),
                        subject,
                        body_html, None)
                if not ok:
                    logging.error(f'failed to send new-member-volunteer-interest email to {rep_email}')
                else:
                    logging.info(f'sent new-member-volunteer-interest email to {rep_email}')

    return flask.make_response('', 200)


@tasks.route('/tasks/renew-member-mail', methods=['POST'])
def renew_member_mail():
    """Queue task invoked when a member has been renewed.
    Sends appropriate welcome emails.
    """
    logging.info('tasks.renew_member_mail hit')

    member_dict = gapps.validate_queue_task(flask.request)
    logging.info(member_dict)

    #
    # Send welcome email
    #

    member_name = '%s %s' % (member_dict[config.SHEETS.member.fields.first_name.name],
                                member_dict[config.SHEETS.member.fields.last_name.name])
    member_email = member_dict[config.SHEETS.member.fields.email.name]

    with open('templates/tasks/email-renew-member-subject.txt', 'r') as subject_file:
        subject = subject_file.read().strip()

    body_html = flask.render_template(
        'tasks/email-renew-member.jinja',
        app_config=config)

    if not emailer.send((member_email, member_name), subject, body_html, None):
        # Log and carry on
        # TODO: Should we instead return non-200 and let the task retry?
        logging.error(f'failed to send renew-member email to {member_email}')
    else:
        logging.info(f'sent renew-member email to {member_email}')

    return flask.make_response('', 200)


@tasks.route('/tasks/new-volunteer-mail', methods=['POST'])
def new_volunteer_mail():
    """Queue task invoked when a new volunteer has been added.
    Sends appropriate welcome emails.
    """

    logging.info('tasks.new_volunteer_mail hit')

    volunteer_dict = gapps.validate_queue_task(flask.request)
    logging.info(volunteer_dict)

    #
    # Send welcome email
    #

    volunteer_name = '%s %s' % (volunteer_dict[config.SHEETS.volunteer.fields.first_name.name],
                                volunteer_dict[config.SHEETS.volunteer.fields.last_name.name])
    volunteer_email = volunteer_dict[config.SHEETS.volunteer.fields.email.name]

    with open('templates/tasks/email-new-volunteer-subject.txt', 'r') as subject_file:
        subject = subject_file.read().strip()

    body_html = flask.render_template(
        'tasks/email-new-volunteer.jinja',
        app_config=config)

    if not emailer.send((volunteer_email, volunteer_name), subject, body_html, None):
        # Log and carry on
        # TODO: Should we instead return non-200 and let the task retry?
        logging.error(f'failed to send new-volunteer email to {volunteer_email}')
    else:
        logging.info(f'sent new-volunteer email to {volunteer_email}')

    #
    # Send email to volunteer-interest-area reps
    #

    interest_reps = gapps.get_volunteer_interest_reps_for_member(volunteer_dict)

    if interest_reps:
        subject = flask.render_template(
            'tasks/email-volunteer-interest-rep-subject.jinja',
            app_config=config,
            join_type='volunteer').strip()

        for interest, reps in interest_reps.items():
            body_html = flask.render_template(
                'tasks/email-volunteer-interest-rep.jinja',
                app_config=config,
                join_type='volunteer',
                interest=interest,
                member_name=volunteer_name,
                member_email=volunteer_email)

            for rep in reps:
                rep_email = rep.get(config.SHEETS.volunteer_interest.fields.email.name)
                rep_name = rep.get(config.SHEETS.volunteer_interest.fields.name.name)
                ok = emailer.send(
                        (rep_email, rep_name),
                        subject, body_html, None)
                if not ok:
                    logging.error(f'failed to send new-volunteer-volunteer-interest email to {rep_email}')
                else:
                    logging.info(f'sent new-volunteer-volunteer-interest email to {rep_email}')

    return flask.make_response('', 200)


@tasks.route('/tasks/member-sheet-cull', methods=['GET', 'POST'])
def member_sheet_cull():
    """Remove members from the members sheet who have not renewed in a long time.
    This gets called both as a cron job and a task queue job.
    """
    if flask.request.method == 'GET':
        # cron job
        logging.debug('tasks.member_sheet_cull hit from cron')
        gapps.validate_cron_task(flask.request)
    else:
        # task queue job
        logging.debug('tasks.member_sheet_cull hit from task queue')
        gapps.validate_queue_task(flask.request)

    gapps.cull_members_sheet()

    return flask.make_response('', 200)


class Settings(ndb.Model):
    """Used to store app state and settings.
    """
    SINGLETON_DATASTORE_KEY = 'SINGLETON'

    _ndb_client = ndb.Client()

    member_sheet_year = ndb.IntegerProperty(
        default=2019,
        verbose_name='The current year of operation. When the calendar year changes, work needs to be done and this gets updated.',
        indexed=False)

    @classmethod
    def singleton(cls):
        with cls._ndb_client.context():
            return cls.get_or_insert(cls.SINGLETON_DATASTORE_KEY)

    def update(self):
        with self._ndb_client.context():
            self.put()


@tasks.route('/tasks/member-sheet-archive', methods=['GET'])
def member_sheet_archive():
    """Cron task that creates an archive of the members sheet once per year.
    """
    logging.warning('tasks.member_sheet_archive: hit')
    gapps.validate_cron_task(flask.request)

    settings = Settings.singleton()
    logging.debug('tasks.member_sheet_archive: settings.member_sheet_year: %d', settings.member_sheet_year)

    new_year = gapps.archive_members_sheet(settings.member_sheet_year)
    if new_year:
        logging.debug('tasks.member_sheet_archive: archived; setting new year: %d', new_year)
        settings.member_sheet_year = new_year
        settings.update()

    return flask.make_response('', 200)


@tasks.route('/tasks/renewal-reminder-emails', methods=['GET'])
def renewal_reminder_emails():
    """Sends renewal reminder emails to members who are nearing their renewal
    date.
    """
    logging.debug('tasks.renewal_reminder_emails: hit')
    gapps.validate_cron_task(flask.request)

    expiring_rows = gapps.get_members_expiring_soon()
    if not expiring_rows:
        logging.debug('tasks.renewal_reminder_emails: no expiring members')
        return flask.make_response('', 200)

    logging.debug('tasks.renewal_reminder_emails: found %d expiring members', len(expiring_rows))

    with open('templates/tasks/email-renewal-reminder-subject.txt', 'r') as subject_file:
        subject_noauto = subject_file.read().strip()

    with open('templates/tasks/email-renewal-reminder-auto-subject.txt', 'r') as subject_file:
        subject_auto = subject_file.read().strip()

    for row in expiring_rows:
        member_first_name = row.dict.get(config.SHEETS.member.fields.first_name.name)
        member_name = '%s %s' % (member_first_name,
                                 row.dict.get(config.SHEETS.member.fields.last_name.name))
        member_email = row.dict.get(config.SHEETS.member.fields.email.name)

        # Right now we use a Paypal button that does one-time purchases;
        # that is, members pay for a year and then need to manually pay
        # again the next year. But previously we used a "subscription"
        # Paypal button, so there are still some members who automatically
        # pay each year. These two groups will get different reminder
        # emails.
        auto_renewing = str(row.dict.get(config.SHEETS.member.fields.paypal_auto_renewing.name))
        if auto_renewing.lower().startswith('y'):
            # Member is auto-renewing (i.e., is a Paypal "subscriber")
            subject = subject_auto
            body_html = flask.render_template(
                'tasks/email-renewal-reminder-auto.jinja',
                app_config=config,
                member_first_name=row.dict.get(config.SHEETS.member.fields.first_name.name))
            logging.info('tasks.renewal_reminder_emails: sending auto-renewing reminder to %s', member_email)

        else:
            # Member is year-to-year
            subject = subject_noauto
            body_html = flask.render_template(
                'tasks/email-renewal-reminder.jinja',
                app_config=config,
                member_first_name=row.dict.get(config.SHEETS.member.fields.first_name.name))
            logging.info('tasks.renewal_reminder_emails: sending non-auto-renewing reminder to %s', member_email)

        emailer.send((member_email, member_name),
                     subject, body_html, None)

    return flask.make_response('', 200)


@tasks.route('/tasks/process-mailchimp-updates', methods=['GET', 'POST'])
def process_mailchimp_updates():
    """Updates MailChimp with changed members and volunteers.
    This gets called both as a cron job and a task queue job.
    """
    if flask.request.method == 'GET':
        # cron job
        logging.debug('tasks.process_mailchimp_updates: hit from cron')
        gapps.validate_cron_task(flask.request)
    else:
        # task queue job
        logging.debug('tasks.process_mailchimp_updates: hit from task queue')
        gapps.validate_queue_task(flask.request)

    if not config.MAILCHIMP_ENABLED:
        return flask.make_response('', 200)

    gapps.process_mailchimp_updates()
    return flask.make_response('', 200)
