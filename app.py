import functools
import logging
import os
import uuid

import db
import flask
import httplib2
import sheets
from googleapiclient.discovery import build
from oauth2client import client
from refresh_data import update_all_stocks_sheets

logger = logging.getLogger(__name__)

app = flask.Flask(__name__)

app.secret_key = str(uuid.uuid4())

FILEPATH_CREDENTIALS = os.path.join(os.path.dirname(__file__), 'client_secret.json')
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile']
DT_FORMAT = '%m-%d-%Y %H:%M'

# TODO(jalex): Write unittests


def auth_required(func):
    """
    Decorator to check for credentials and start oauth dance if they don't exist in session.
    :param func: Function to wrap.
    :return: Wrapper function.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """
        Internal wrapper function.. All args/kwargs passed to wrapped function.
        :return: Either redirect to oauth endpoint or wrapped function results.
        """
        if 'credentials' not in flask.session:
            flask.session['original_func_name'] = func.__name__
            return flask.redirect(flask.url_for('oauth2callback'))
        return func(*args, **kwargs)

    return wrapper


def auth_required_resp(func):
    """
    Decorator to check for credentials and return unauthorized response if they don't exist in session.
    :param func: Function to wrap.
    :return: Wrapper function.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """
        Internal wrapper function.. All args/kwargs passed to wrapped function.
        :return: Either unauthorized response or wrapped function results.
        """
        if 'credentials' not in flask.session:
            message, resp_code = 'Unauthorized', 401
            resp = flask.jsonify({'message': message})
            resp.status_code = resp_code
            return resp
        else:
            return func(*args, **kwargs)

    return wrapper


@app.route('/')
@auth_required
def index():
    """
    Endpoint for homepage with user's sheets.
    :return: Response for homepage.
    """

    user_id = flask.session['user_id']
    user = db.get_create_user(user_id)

    sheets = [k.get() for k in user.sheet_keys]

    return flask.render_template('index.html', sheets=sheets, dt_format=DT_FORMAT)


@app.route('/oauth2callback')
def oauth2callback():
    """
    Endpoint for both oauth steps.
    :return: Response to authorize or response to exchange auth code for access token.
    """
    flow = client.flow_from_clientsecrets(FILEPATH_CREDENTIALS,
                                          scope=SCOPE,
                                          redirect_uri=flask.url_for('oauth2callback', _external=True))
    if 'code' not in flask.request.args:
        flow.params['access_type'] = 'offline'
        flow.params['approval_prompt'] = 'force'
        auth_uri = flow.step1_get_authorize_url()
        return flask.redirect(auth_uri)
    else:
        auth_code = flask.request.args.get('code')
        credentials = flow.step2_exchange(auth_code)
        user_info = _get_user_info(credentials)
        user_id, user_email = user_info['id'], user_info['email']
        if credentials.refresh_token is not None:
            db.store_user_credentials(user_id, credentials, email=user_email)
        else:
            credentials = db.get_credentials(user_id=user_id)
            assert credentials.refresh_token is not None
        flask.session['credentials'] = credentials.to_json()
        flask.session['user_id'] = user_id
        func_name = flask.session.get('original_func_name', 'index')
        return flask.redirect(flask.url_for(func_name))


def _get_user_info(credentials):
    """
    Get user's information from google api.
    :param credentials: OAuth2Credentials used to retrieve user info.
    :return: dict of user info.
    """

    service_user_info = build('oauth2', 'v2', http=credentials.authorize(httplib2.Http()))
    user_info = service_user_info.userinfo().get().execute()

    return user_info


@app.route('/delete', methods=['POST'])
@auth_required_resp
def delete():
    """
    Endpoint to delete sheet from server database.
    :return: Success response.
    """

    ssheet_id = flask.request.get_json().get('ssheet_id')
    db.delete_sheet(ssheet_id)
    resp = flask.jsonify({'ssheet_id': ssheet_id})
    resp.status_code = 200

    return resp


@app.route('/create')
@auth_required_resp
def create():
    """
    Endpoint to create sheet in google sheets and server database.
    :return: Success response.
    """

    user_id = flask.session['user_id']

    credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    h = credentials.authorize(httplib2.Http())
    ssheet_id, title = sheets.create_sheet(h)

    sheet = db.create_sheet(ssheet_id, user_id, title)

    row_html = flask.render_template('sheet_row.html', s=sheet, dt_format=DT_FORMAT)
    resp = flask.jsonify(row_to_insert=row_html)
    resp.status_code = 200

    return resp


@app.route('/sync', methods=['POST'])
@auth_required_resp
def sync():
    """
    Endpoint to sync data on google sheet with server database. Requires that ssheet_id be in posted json.
    :return: Response indicating success.
    """

    ssheet_id = flask.request.get_json().get('ssheet_id')

    credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    h = credentials.authorize(httplib2.Http())

    resp_dict = {}

    try:
        symbols, lbs, ubs = sheets.get_user_supplied_data(ssheet_id, http=h)
        title = sheets.get_title(ssheet_id, http=h)
        prices, dt = db.process_sheet_inputs(ssheet_id, symbols, lbs, ubs, title)
        sheets.set_prices(ssheet_id, prices, http=h)
        resp_dict['datetime'] = dt.strftime(DT_FORMAT)
        if title:
            resp_dict['title'] = title
        message, resp_code = 'Success', 200
    except sheets.UnauthorizedSheetError:
        message, resp_code = 'Forbidden', 403
    except sheets.SheetNotFoundError:
        message, resp_code = 'Not found', 404
    except sheets.UnknownSheetError:
        message, resp_code = 'Unknown', 500
    except sheets.UserDataUnreadableError:
        message, resp_code = 'Could not read sheet. Please make sure stocks are not formatted and no blank lines.', 400

    resp_dict.update({'ssheet_id': ssheet_id, 'message': message})
    resp = flask.jsonify(resp_dict)
    resp.status_code = resp_code

    return resp


@app.route('/update_stocks')
def update_all():
    """
    Endpoint for cron job to update all stocks and sheets.
    :return: Success response.
    """
    update_all_stocks_sheets(unsubscribe_url=flask.url_for('settings_get', _external=True))

    return '', 204


@app.route('/settings')
@auth_required
def settings_get():
    """
    Endpoint for retrieving user settings.
    :return: Response for settings page.
    """

    user_id = flask.session['user_id']
    user = db.get_create_user(user_id)

    return flask.render_template('settings.html', notify_user=user.notify)


@app.route('/settings', methods=['POST'])
@auth_required_resp
def settings_post():
    """
    Endpoint for changing user settings.
    :return: Success response.
    """

    user_id = flask.session['user_id']

    notify = flask.request.json.get('notify')
    if notify is not None:
        db.set_user_notify(user_id, notify)

    resp = flask.jsonify(user_id=user_id, notify=notify)
    resp.status_code = 200

    return resp


if __name__ == '__main__':

    app.run(host='127.0.0.1', port=8080, debug=True)
