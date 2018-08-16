"""Provides database storage for the Dozer Discord bot"""

import sqlalchemy
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, ForeignKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker

__all__ = ['engine', 'DatabaseObject', 'Session', 'Column', 'Integer', 'String', 'ForeignKey', 'relationship',
           'Boolean', 'ForeignKeyConstraint']

engine = sqlalchemy.create_engine('sqlite:///dozer.db')
DatabaseObject = declarative_base(bind=engine, name='DatabaseObject')
DatabaseObject.__table_args__ = {'extend_existing': True}  # allow use of the reload command with db cogs


class CtxSession(Session):
    """Allows sessions to be used as context managers and asynchronous context managers."""
    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, err_type, err, tb):
        if err_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    async def __aexit__(self, err_type, err, tb):
        return self.__exit__(err_type, err, tb)


Session = sessionmaker(bind=engine, class_=CtxSession)
