import logging
import threading

import db
import emails
import httplib2
import sheets

logger = logging.getLogger(__name__)

# Update this if your execution environment supports multithreading
USE_THREADS = False


def update_all_stocks_sheets(unsubscribe_url='Bad Developer... Always supply this.'):
    """
    Get new stock prices, alert users, and update spreadsheets.
    :param unsubscribe_url: Url that will be put in alert emails allowing users to unsubscribe.
    """

    sheet_prices_dict, sheet_alerts_dict = db.update_stock_prices(alerts=True)

    user_alerts_dict = db.get_user_alerts(sheet_alerts_dict)

    l = emails.get_emails(user_alerts_dict, unsubscribe_url)
    emails.send_emails(l)

    for ssheet_id, prices in sheet_prices_dict.items():
        credentials = db.get_credentials(ssheet_id=ssheet_id)
        h = credentials.authorize(httplib2.Http())
        # TODO(jalex): Implement using GAE's task queues (https://cloud.google.com/appengine/docs/python/taskqueue/)
        if USE_THREADS:
            t = threading.Thread(target=sheets.set_prices, args=(ssheet_id, prices, h))
            t.daemon = True
            t.start()
        else:
            sheets.set_prices(ssheet_id, prices, h)
