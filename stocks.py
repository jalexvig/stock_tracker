import json

import httplib2

PRICE_DIGITS = 2


def get_stock_prices(symbols):
    """
    Query outside api for stock prices.
    :param symbols: Iterable of symbols to retrieve stock prices for.
    :return: dict mapping symbol to current price.
    """

    if isinstance(symbols, (str, unicode)):
        symbols = [symbols]

    url = 'http://finance.yahoo.com/webservice/v1/symbols/%s/quote?format=json' % ','.join(symbols)

    http = httplib2.Http()
    resp = http.request(url)
    content = json.loads(resp[1])

    symbol_dicts = content['list']['resources']
    symbol_dicts = [d['resource']['fields'] for d in symbol_dicts]

    symbol_price_dict = {d['symbol'].lower(): round(float(d['price']), PRICE_DIGITS) for d in symbol_dicts}

    return symbol_price_dict
