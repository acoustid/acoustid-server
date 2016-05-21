from sqlalchemy.orm import sessionmaker


Session = sessionmaker()


class DatabaseContext(object):

    def __init__(self, bind):
        self.session = Session(bind=bind)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()
