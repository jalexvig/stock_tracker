import logging
import re
from functools import wraps

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

sheets_service = build('sheets', 'v4')

FORMAT_LT = {
    "backgroundColor": {
        "red": 1,
    }
}

FORMAT_GT = {
    "backgroundColor": {
        "blue": 1,
    }
}


def handle_google_api_errors(func):
    """
    Decorator to process errors when calling google apis.
    :param func: Function to wrap.
    :return: Wrapper function.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        """
        Internal wrapper function.. All args/kwargs passed to wrapped function.
        :return: Either return result of wrapped function or log and raise custom exceptions.
        """
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            resp_code = int(e.resp['status'])
            if resp_code == 403 or resp_code == 401:
                logger.exception('Unauthorized access.')
                raise UnauthorizedSheetError(e.uri)
            elif resp_code == 404:
                logger.exception('Sheet not found.')
                raise SheetNotFoundError(e.uri)
            else:
                logger.exception('Unhandled response code.')
                raise UnknownSheetError('Response code %i not handled. Resp content = %s' % (resp_code, e.content))

    return wrapper


@handle_google_api_errors
def get(ssheet_id, range_, http=None, major_dimension='COLUMNS'):
    """
    Get range(s) from single spreadsheet.
    :param ssheet_id: Spreadsheet id.
    :param range_: Range(s) to extract in A1 notation. If multiple ranges specified must be in a list.
    :param http: httplib2.Http instance.
    :param major_dimension: Major dimension to use when returning data.
    :return: Retrieved values.
    """

    if isinstance(range_, str):
        return _get(ssheet_id, range_, major_dimension, http=http)
    elif isinstance(range_, list):
        return _get_batch(ssheet_id, range_, major_dimension, http=http)
    else:
        pass
    raise TypeError('range must be either type list or str')


def _get_batch(ssheet_id, ranges, major_dimension, http=None):
    """
    Get ranges from single spreadsheet.
    :param ssheet_id: Spreadsheet id.
    :param ranges: list of ranges to extract in A1 notation.
    :param major_dimension: Major dimension to use when returning data.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: Retrieved values.
    """

    res = sheets_service.spreadsheets().values().batchGet(
        spreadsheetId=ssheet_id, ranges=ranges, majorDimension=major_dimension
    ).execute(http=http)

    res = [d['values'] for d in res['valueRanges']]

    return res


def _get(ssheet_id, range_, major_dimension, http=None):
    """
    Get range from single spreadsheet.
    :param ssheet_id: Spreadsheet id.
    :param range_: str range to extract in A1 notation.
    :param major_dimension: Major dimension to use when returning data.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: Retrieved values.
    """

    resp = sheets_service.spreadsheets().values().get(
        spreadsheetId=ssheet_id, range=range_, majorDimension=major_dimension
    ).execute(http=http)

    res = resp.get('values')

    return res


@handle_google_api_errors
def _update(ssheet_id, range_, values, major_dimension, http=None):
    """
    Write values to spreadsheet.
    :param ssheet_id: Spreadsheet id.
    :param range_: str range to extract in A1 notation.
    :param values: list of values to write.
    :param major_dimension: Major dimension to use when returning data.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: Response from api.
    """

    body = {
        'range': range_,
        'values': values,
        'majorDimension': major_dimension
    }

    resp = sheets_service.spreadsheets().values().update(
        spreadsheetId=ssheet_id, range=range_, body=body, valueInputOption='USER_ENTERED'
    ).execute(http=http)

    return resp


@handle_google_api_errors
def batch_update(ssheet_id, requests, http=None):
    """
    Update spreadsheet.
    :param ssheet_id: Spreadsheet id.
    :param requests: list of requests. See https://developers.google.com/sheets/reference/rest/v4/spreadsheets/request
        for more info.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: Response from api.
    """

    body = {
        'requests': requests
    }

    resp = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=ssheet_id, body=body
    ).execute(http=http)

    return resp


@handle_google_api_errors
def get_spreadsheet(ssheet_id, http=None):
    """
    Get spreadsheet metadata.
    :param ssheet_id: Spreadsheet id.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: Response from api.
    """

    resp = sheets_service.spreadsheets().get(
        spreadsheetId=ssheet_id
    ).execute(http=http)

    return resp


def _get_request_add_conditional_format(rule):
    """
    Get request to conditionally format cells.
    :param rule: dict form of rule to format cells.
    :return: dict form of request.
    """

    request = {
        "addConditionalFormatRule": {
            "rule": rule,
            'index': 0
        }
    }

    return request


def _get_requests_highlight_outside_bounds(sheet_id=0):
    """
    Get requests to highlight user specified values that fall outside of bounds.
    :param sheet_id: Sheet id (inside spreadsheet).
    :return: list of requests.
    """

    rules = _get_rules_highlight_outside_bounds(sheet_id)

    requests = list(map(_get_request_add_conditional_format, rules))

    return requests


def _get_rule_conditional_format(type_, values, format_, ranges):
    """
    Get rule to conditionally highlight cells.
    :param type_: Type of conditional comparison to make.
    :param values: User entered values (using '=A1' notation).
    :param format_: Format of cells matching condition.
    :param ranges: Ranges to apply conditional formatting.
    :return: dict form of rule.
    """

    d = {
        "booleanRule": {
            "condition": {
                "type": type_,
                "values": values
            },
            "format": format_
        },
        "ranges": ranges
    }

    return d


def _get_rules_highlight_outside_bounds(sheet_id=0):
    """
    Get rules for highlighting values that fall outside of user specified bounds.
    :param sheet_id: Sheet id.
    :return: list of rules.
    """

    type_lt = "NUMBER_LESS"
    type_gt = "NUMBER_GREATER"

    values_lt = [{'userEnteredValue': '=B2'}]
    values_gt = [{'userEnteredValue': '=C2'}]

    ranges = [{
        "sheetId": sheet_id,
        "startColumnIndex": 3,
        "endColumnIndex": 4,
        "startRowIndex": 1
    }]

    rule_lt = _get_rule_conditional_format(type_lt, values_lt, FORMAT_LT, ranges)
    rule_gt = _get_rule_conditional_format(type_gt, values_gt, FORMAT_GT, ranges)

    return [rule_lt, rule_gt]


def setup_formatting(ssheet_id, sheet_id=0, http=None):
    """
    Set up highlighting for values outside of bounds for new sheet.
    :param ssheet_id: Spreadsheet id.
    :param sheet_id: Sheet id.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: Response from api.
    """

    requests = _get_requests_highlight_outside_bounds(sheet_id)
    resp = batch_update(ssheet_id, requests, http)

    return resp


def create_sheet(http, title='My Stock Tracker'):
    """
    Create spreadsheet.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :param title: str title of spreadsheet.
    :return: tuple of (spreadsheet id, spreadsheet title).
    """

    header_row = ['Symbol', 'Lower Bound', 'Upper Bound', 'Price']
    body = {
        'sheets': [
            {
                'data': [
                    {
                        'rowData': {
                            'values': [{'userEnteredValue': {'stringValue': val}} for val in header_row]
                        }
                    }
                ],
                'conditionalFormats': _get_rules_highlight_outside_bounds(),
                'properties': {
                    'sheetId': 0,
                }
            }
        ],
        'properties': {
            'title': title,
        }
    }

    d = sheets_service.spreadsheets().create(body=body).execute(http=http)
    ssheet_id = d['spreadsheetId']
    title = d['properties']['title']

    return ssheet_id, title


def _convert_price_string(s):
    """
    Convert price string to float.
    :param s: Price str.
    :return: float value of s.
    """

    try:
        res = float(s)
    except ValueError:
        m = re.search('\d+\.?\d*', s)
        if m is None:
            raise PriceConversionError('Error converting price %s' % s)

        res = m.group(0)

    return res


def get_user_supplied_data(ssheet_id, http):
    """
    Get all data in user supplied fields on sheet.
    :param ssheet_id: Spreadsheet id.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: tuple of (symbols, lower bounds, upper bounds)
    """

    symbols, lbs, ubs = [], [], []

    res = get(ssheet_id, 'A2:C', http=http)
    if res is not None:
        symbols, lbs, ubs = res
        for symbol in symbols:
            if not symbol:
                raise UserDataUnreadableError('Found empty stock symbol')
        try:
            lbs = [_convert_price_string(lb) for lb in lbs]
            ubs = [_convert_price_string(ub) for ub in ubs]
        except PriceConversionError:
            logger.exception('Error converting bounds')
            raise UserDataUnreadableError

    return symbols, lbs, ubs


def get_title(ssheet_id, http):
    """
    Get spreadsheet title.
    :param ssheet_id: Spreadsheet id.
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: str title of spreadsheet.
    """

    ssheet = get_spreadsheet(ssheet_id, http=http)

    try:
        title = ssheet['properties']['title'] or None
    except KeyError:
        title = None

    return title


def set_prices(ssheet_id, prices, http):
    """
    Set prices on sheet.
    :param ssheet_id: Spreadsheet id.
    :param prices: list of prices (floats).
    :param http: httplib2.Http instance. If None, will use service's instance if set.
    :return: Response from api.
    """

    resp = _update(ssheet_id, 'D2:D', [prices], 'COLUMNS', http=http)

    return resp


class SheetNotFoundError(Exception):
    pass


class UnauthorizedSheetError(Exception):
    pass


class UnknownSheetError(Exception):
    pass


class PriceConversionError(Exception):
    pass


class UserDataUnreadableError(Exception):
    pass
