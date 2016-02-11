import random
import datetime
from .models import Account, Application, StatsLookups


def create_sample_data(session):
    rnd = random.WichmannHill(1)

    account_1234 = Account(id=1234, name='user1234', apikey='26ec5efff4a6')
    session.add(account_1234)
    account_1235 = Account(id=1235, name='lukz', mbuser='lukz', apikey='2112c535e9e6', is_admin=True)
    session.add(account_1235)

    application_1234 = Application(account=account_1234, name='Test App', version='1.0', apikey='617f98b2d7cc')
    session.add(application_1234)

    unflushed = 0
    dt = datetime.datetime(2014, 1, 2)
    while dt < datetime.datetime.now():
        obj = StatsLookups(date=dt.date(), hour=dt.hour, application=application_1234)
        obj.count_nohits = rnd.randint(0, 1000)
        obj.count_hits = rnd.randint(0, 10000)
        session.add(obj)
        dt += datetime.timedelta(hours=1)
        unflushed += 1
        if unflushed > 100:
            session.flush()
            unflushed = 0

    application_1235 = Application(account=account_1235, name='Test App 2', version='0.2', apikey='c24d2e31d8db')
    session.add(application_1235)

    unflushed = 0
    dt = datetime.datetime(2015, 2, 3)
    while dt < datetime.datetime.now():
        obj = StatsLookups(date=dt.date(), hour=dt.hour, application=application_1235)
        obj.count_nohits = rnd.randint(0, 200)
        obj.count_hits = rnd.randint(0, 1000)
        session.add(obj)
        dt += datetime.timedelta(hours=1)
        unflushed += 1
        if unflushed > 100:
            session.flush()
            unflushed = 0

    session.commit()
