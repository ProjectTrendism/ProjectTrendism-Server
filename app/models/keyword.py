from sqlalchemy import Column, Integer, String, Float, Boolean
from app.database import Base

class Keyword(Base):
    __tablename__ = "keywords"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    category    = Column(String, nullable=False)
    r_value     = Column(Float, default=50.0)
    g_value     = Column(Float, default=50.0)
    b_value     = Column(Float, default=50.0)
    rarity      = Column(String, default="COMMON")
    description = Column(String, default="")
    is_active   = Column(Boolean, default=True)