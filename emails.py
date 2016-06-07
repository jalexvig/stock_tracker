import copy
import logging

from google.appengine.api import app_identity
from google.appengine.api import mail

SENDER = 'notifications@{}.appspotmail.com'.format(app_identity.get_application_id())
SUBJECT = 'Stock alerts!'

logger = logging.getLogger(__name__)


def send_emails(emails):
    """
    Send emails.
    :param emails: Iterable of tuples of form (recipient, message).
    """

    for recipient, message in emails:
        try:
            mail.send_mail(SENDER, recipient, SUBJECT, message)
        except mail.InvalidSenderError:
            logger.exception('Sender: %s, recipient: %s, subject: %s', SENDER, recipient, SUBJECT)


def get_emails(user_alerts_dict, unsubscribe_url):
    """
    Get list of emails.
    :param user_alerts_dict: Nested dict mapping user id to spreadsheet id to symbol to alert data.
    :param unsubscribe_url: Url that will be put in alert emails allowing users to unsubscribe.
    :return: Iterable of tuples of form (recipient, message).
    """

    user_alerts_dict = copy.copy(user_alerts_dict)

    email_tups = []

    for user_id, sheet_alerts_dict in user_alerts_dict.items():
        email = sheet_alerts_dict.pop('email')
        message = _get_email_message(sheet_alerts_dict, unsubscribe_url)
        email_tups.append((email, message))

    return email_tups


def _get_email_message(sheet_alerts_dict, unsubscribe_url):
    """
    Get a single email message.
    :param sheet_alerts_dict: Nested dict mapping spreadsheet id to symbol to alert data.
    :param unsubscribe_url: Url that will be put in alert emails allowing users to unsubscribe.
    :return: Message (str) to send.
    """

    sheet_messages = []

    for sheet_id, symbol_alerts_dict in sheet_alerts_dict.items():
        sheet_title = symbol_alerts_dict.pop('sheet_title', '')

        sheet_message = '{} (https://docs.google.com/spreadsheets/d/{})\n\t'.format(sheet_title, sheet_id)

        sheet_message += '\n\t'.join(map(_format_symbol_alert, symbol_alerts_dict.items()))

        sheet_messages.append(sheet_message)

    message = '\n\n'.join(sheet_messages)

    message += '\n\nTo unsubscribe, visit the following link: {}'.format(unsubscribe_url)

    return message


def _format_symbol_alert(tup):
    """
    Format alert data.
    :param tup: tuple of form (symbol, alert data). The alert data is a tuple of form
        (lower bound, upper bound, old price, new price).
    :return: Formatted alert (str).
    """

    symbol, alert = tup

    lb, ub, price_old, price_new = alert

    m = '{}    Bounds: ({}, {})    Old price: {}    New price: {}'.format(symbol, lb, ub, price_old, price_new)

    return m
