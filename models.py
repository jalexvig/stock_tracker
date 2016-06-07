from google.appengine.ext import ndb


class MyModel(ndb.Model):

    @classmethod
    def get_create_by_id(cls, *args, **kwargs):
        """
        Get an entity or create one if it doesn't exist.
        :param args: Arbitrary number of args. These will be used to create a key if 'id' is not in kwargs.
        :param kwargs: Arbitrary kwargs. If 'id' is in kwargs, it will be used to look up the entity.
        :return: tuple. First element is entity. Second element indicates whether the entity was created.
        """

        created = False

        if 'id' not in kwargs:
            kwargs['id'] = '_'.join(args)
        entity = cls.get_by_id(kwargs['id'])
        if entity is None:
            entity = cls(**kwargs)
            created = True

        return entity, created

    @classmethod
    def get_by_id(cls, *args):
        return super(MyModel, cls).get_by_id('_'.join(args))


class SheetStock(MyModel):

    bound_lower = ndb.FloatProperty('lb')
    bound_upper = ndb.FloatProperty('ub')


class User(MyModel):

    notify = ndb.BooleanProperty('n', default=False)
    email = ndb.StringProperty('e')
    sheet_keys = ndb.KeyProperty(kind='Sheet', repeated=True)
    credentials = ndb.BlobProperty('c')


class Sheet(MyModel):

    title = ndb.StringProperty('t')
    last_updated = ndb.DateTimeProperty(auto_now=True)
    stock_keys = ndb.KeyProperty(kind='Stock', repeated=True)
    user_keys = ndb.KeyProperty(kind='User', repeated=True)


class Stock(MyModel):

    price = ndb.FloatProperty('p')
    sheet_keys = ndb.KeyProperty(kind='Sheet', repeated=True)
