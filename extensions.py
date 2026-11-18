"""
Flask extension singletons.

Kept in their own module so models.py / forms.py / app.py can import `db`
without circular imports back through app.py.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()
