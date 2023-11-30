from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

DATABASE_URL = "sqlite:///./test.db"  # Change this to your database connection string
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Chatroom(Base):
    __tablename__ = "chatrooms"
    id = Column(String, primary_key=True, index=True)
    messages = relationship("Message", back_populates="chatroom")


class Users(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String, unique=True, index=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, index=True)
    type = Column(String, index=True)
    user = Column(String, ForeignKey("users.id"))
    chatroom_id = Column(String, ForeignKey("chatrooms.id"))
    chatroom = relationship("Chatroom", back_populates="messages")

Base.metadata.create_all(bind=engine)
