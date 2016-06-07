import copy
import logging
from collections import defaultdict

from google.appengine.ext import ndb

import stocks
from models import SheetStock, Sheet, Stock, User
from oauth2client import client

logger = logging.getLogger(__name__)


def process_sheet_inputs(ssheet_id, symbols, lbs, ubs, title=None):
    """
    Make necessary changes to database given user inputs.
    :param ssheet_id: Spreadsheet id.
    :param symbols: Iterable of symbols.
    :param lbs: Iterable of lower bounds for the stock price.
    :param ubs: Iterable of upper bounds for the stock price.
    :param title: New str title of spreadsheet. None if not to be updated.
    :return: list of stock prices corresponding to symbols, datetime sheet was updated (UTC).
    """

    symbols = [s.lower() for s in symbols]

    sheet = Sheet.get_by_id(ssheet_id)

    to_put, to_delete = _process_removed_stocks(sheet, ssheet_id, symbols)

    stock_keys, prices, list_put = _process_new_or_changed_stocks(lbs, ubs, sheet, ssheet_id, symbols)
    to_put.extend(list_put)

    sheet.stock_keys = stock_keys
    if title is not None:
        sheet.title = title

    to_put.append(sheet)

    ndb.put_multi(to_put)
    ndb.delete_multi(to_delete)

    return prices, sheet.last_updated


def _process_new_or_changed_stocks(lbs, ubs, sheet, ssheet_id, symbols):
    """
    Update database to reflect sheet's new stocks, changed bounds, or changed order.
    :param lbs: Iterable of lower bounds for the stock price.
    :param ubs: Iterable of upper bounds for the stock price.
    :param sheet: Instance of models.Sheet to modify.
    :param ssheet_id: Spreadsheet id.
    :param symbols: Iterable of symbols.
    :return: list of stock keys, list of new prices, list of ndb Entities to put.
    """

    to_put = []
    stock_keys, prices = [], []

    for symbol, lb, ub in zip(symbols, lbs, ubs):

        stock, put_stock = Stock.get_create_by_id(symbol)

        if stock.price is None:
            price = stocks.get_stock_prices(symbol).get(symbol)
            stock.price = price
            put_stock = True

        if sheet.key not in stock.sheet_keys:
            stock.sheet_keys.append(sheet.key)
            put_stock = True

        if put_stock:
            to_put.append(stock)

        stock_keys.append(stock.key)
        prices.append(stock.price)

        sheetstock, put_sheetstock = SheetStock.get_create_by_id(ssheet_id, symbol, bound_lower=lb, bound_upper=ub)
        put_sheetstock = _update_sheet_stock_bounds(sheetstock, lb, ub, changed=put_sheetstock)

        if put_sheetstock:
            to_put.append(sheetstock)

    return stock_keys, prices, to_put


def _process_removed_stocks(sheet, ssheet_id, symbols):
    """
    Update database to reflect sheet's new stocks, changed bounds, or changed order.
    :param sheet: Instance of models.Sheet to modify.
    :param ssheet_id: Spreadsheet id.
    :param symbols: Iterable of symbols.
    :return: list of ndb Entities to put, list of ndb Entities to delete.
    """

    to_put, to_delete = [], []

    symbols_old = {k.id() for k in sheet.stock_keys}

    for symbol in symbols_old - set(symbols):
        stock = Stock.get_by_id(symbol)
        sheetstock_key = ndb.Key('SheetStock', '_'.join([ssheet_id, symbol]))

        to_delete.append(sheetstock_key)

        if stock and sheet.key in stock.sheet_keys:
            stock.sheet_keys.remove(sheet.key)
            if stock.sheet_keys:
                to_put.append(stock)
            else:
                to_delete.append(stock.key)

    return to_put, to_delete


def _update_sheet_stock_bounds(sheetstock, lb, ub, changed=False):
    """
    Update sheetstock to reflect new bounds.
    :param sheetstock: Instance of models.SheetStock.
    :param lb: Lower bound.
    :param ub: Upper bound.
    :param changed: bool indicating whether sheetstock has been changed without being stored.
    :return: bool indicating whether sheet_stock has been changed without being stored.
    """

    if sheetstock.bound_lower != lb:
        sheetstock.bound_lower = lb
        changed = True
    if sheetstock.bound_upper != ub:
        sheetstock.bound_upper = ub
        changed = True

    return changed


def update_stock_prices(symbols=None, ssheet_ids=None, alerts=False):
    """
    Update the stock prices by querying outside api.
    :param symbols: Symbols to update.
    :param ssheet_ids: Spreadsheet ids to update. If None, update all spreadsheets.
    :param alerts: Also return a nested dict mapping sheets to symbols to tuples for stock prices that crossed bounds.
    :return: dict mapping sheets to prices (for sheets that changed), dict with alerts (if alerts kwarg is True).
    """

    symbol_price_dict, symbol_price_updated_dict = _update_stocks(symbols)

    sheet_prices_dict = {}

    if ssheet_ids is None:
        sheets = list(Sheet.query())
    else:
        sheets = [Sheet.get_by_id(sid) for sid in ssheet_ids]

    sheet_alerts_dict = {}

    for sheet in sheets:
        if sheet is None:
            continue

        ssheet_id = sheet.key.id()

        sheet_symbols = [stock_key.id() for stock_key in sheet.stock_keys]
        sheet_symbols_updated = [s for s in sheet_symbols if s in symbol_price_updated_dict]

        if any(sheet_symbols_updated):
            sheet_prices = [symbol_price_dict.get(s, '') for s in sheet_symbols]
            sheet_prices_dict[ssheet_id] = sheet_prices

            if alerts:
                d = _get_sheet_alerts(ssheet_id, sheet_symbols_updated, symbol_price_updated_dict)
                if d:
                    sheet_alerts_dict.update({ssheet_id: d})

    if alerts:
        return sheet_prices_dict, sheet_alerts_dict

    return sheet_prices_dict


def _get_sheet_alerts(ssheet_id, sheet_symbols_updated, symbol_price_updated_dict):
    """
    Get alert data for spreadsheets with crossed bounds.
    :param ssheet_id: Spreadsheet id.
    :param sheet_symbols_updated: Iterable of symbols that were updated for this sheet.
    :param symbol_price_updated_dict: dict mapping symbols to (old price, new price).
    :return: A nested dict mapping sheets to symbols to tuples for stock prices that crossed bounds.
    """

    d = {}

    for symbol in sheet_symbols_updated:
        sheetstock = SheetStock.get_by_id(ssheet_id, symbol)
        alert = _get_alert(sheetstock.bound_lower, sheetstock.bound_upper, *symbol_price_updated_dict[symbol])
        if alert is not None:
            d[symbol] = alert

    return d


def _get_alert(lb, ub, price_old, price_new):
    """
    Filter function to determine whether bounds were crossed.
    :param lb: Lower bound for alert.
    :param ub: Upper bound for alert.
    :param price_old: Old stock price.
    :param price_new: New stock price.
    :return: tuple of data if bounds were crossed. Otherwise None.
    """

    if (price_old <= ub < price_new) or (price_new < lb <= price_old):
        return lb, ub, price_old, price_new


def _update_stocks(symbols):
    """
    Update models.Stock entities.
    :param symbols: Iterable of stock symbols to update.
    :return: dict mapping symbols to new prices, dict mapping symbols to (old price, new price) for changed symbols.
    """

    to_put = []
    symbol_price_updated_dict = {}

    if symbols is None:
        stocks_ = list(Stock.query())
        symbols = [s.key.id() for s in stocks_]
    else:
        stocks_ = [Stock.get_by_id(s) for s in symbols]

    symbol_price_dict = stocks.get_stock_prices(symbols)

    for stock in stocks_:
        if stock is None:
            continue

        symbol = stock.key.id()
        price = symbol_price_dict.get(symbol, None)

        if stock.price != price:
            symbol_price_updated_dict[symbol] = (stock.price, price)
            stock.price = price
            to_put.append(stock)

    ndb.put_multi(to_put)

    return symbol_price_dict, symbol_price_updated_dict


def get_user_alerts(sheet_alerts_dict):
    """
    Get alert data corresponding to stocks for each user.
    :param sheet_alerts_dict: Nested dict mapping ssheet id to symbol to alert data.
    :return: Nested dict mapping user id to ssheet id to symbol to alert data.
    """

    d = defaultdict(dict)

    user_keys_to_notify = {u.key for u in User.query(User.notify == True)}

    for sheet_id, symbol_alert_dict in sheet_alerts_dict.items():

        sheet = Sheet.get_by_id(sheet_id)
        if sheet is None:
            continue

        symbol_alert_dict = copy.copy(symbol_alert_dict)
        symbol_alert_dict['sheet_title'] = sheet.title

        for user_key in sheet.user_keys:
            if user_key in user_keys_to_notify:
                d[user_key.id()][sheet_id] = symbol_alert_dict

    for user_id in d:
        d[user_id]['email'] = User.get_by_id(user_id).email

    return d


def delete_sheet(ssheet_id):
    """
    Delete a sheet.
    :param ssheet_id: Spreadsheet id.
    """

    sheet = Sheet.get_by_id(ssheet_id)
    to_put, to_delete = _process_removed_stocks(sheet, ssheet_id, [])

    for k in sheet.user_keys:
        user = k.get()
        user.sheet_keys.remove(sheet.key)
        to_put.append(user)

    to_delete.append(sheet.key)

    ndb.put_multi(to_put)
    ndb.delete_multi(to_delete)


def create_sheet(ssheet_id, user_id, title):
    """
    Create a sheet with given title and register it to given user.
    :param ssheet_id: Spreadsheet id.
    :param user_id: User id.
    :param title: Spreadsheet title.
    :return: models.Sheet instance.
    """

    sheet = Sheet(id=ssheet_id, title=title)
    user = User.get_by_id(user_id)

    sheet.user_keys.append(user.key)

    key_sheet = sheet.put()

    user.sheet_keys.append(key_sheet)

    user.put()

    return sheet


def get_create_user(user_id):
    """
    Retrieve a user with specified user id from the database if it exists. Otherwise create one and store it.
    :param user_id: User id.
    :return: models.User instance.
    """

    user, created = User.get_create_by_id(user_id)
    if created:
        user.put()

    return user


def store_user_credentials(user_id, credentials, email):
    """
    Store credentials with user. Create user if it does not exist.
    :param user_id: User id.
    :param credentials: OAuth2Credentials instance.
    :param email: User's email address.
    """

    credentials = credentials.to_json()

    user, put = User.get_create_by_id(user_id, email=email)
    user.credentials = credentials
    user.put()


def set_user_notify(user_id, notify):
    """
    Update a user's notification settings.
    :param user_id: User id.
    :param notify: bool indicating whether or not the user wishes to be notified when stock prices cross bounds.
    """

    user = User.get_by_id(user_id)

    if user.notify != notify:
        user.notify = notify
        user.put()


def get_credentials(user_id=None, ssheet_id=None):
    """
    Get credentials associated with user or credentials that can access given spreadsheet.
    :param user_id: User id.
    :param user_id: Spreadsheet id.
    :return: OAuth2Credentials instance.
    """

    if user_id is not None:
        user = User.get_by_id(user_id)
        credentials = client.OAuth2Credentials.from_json(user.credentials)
    elif ssheet_id is not None:
        user_keys = Sheet.get_by_id(ssheet_id).user_keys
        if user_keys is None:
            raise NoUsersForSheetError
        credentials = get_credentials(user_id=user_keys[0].id())
    else:
        raise TypeError('Must supply either user_id or ssheet_id kwarg.')

    return credentials


class NoUsersForSheetError(Exception):
    pass
