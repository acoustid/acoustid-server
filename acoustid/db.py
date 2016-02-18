from sqlalchemy.orm import sessionmaker


Session = sessionmaker()


class DatabaseContext(object):

    def __init__(self, bind):
        self.session = Session(bind=bind)
