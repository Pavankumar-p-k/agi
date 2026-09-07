"""Database models."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from core.database import Base, SessionLocal, engine
from datetime import datetime


class McpServer(Base):
    __tablename__ = "mcp_servers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    command = Column(String(1024), nullable=True)
    is_active = Column(Boolean, default=True)


class ModelEndpoint(Base):
    __tablename__ = "model_endpoints"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(1024), nullable=False)
    is_active = Column(Boolean, default=True)
