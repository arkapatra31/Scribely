"""Session lifecycle: live recording sessions (and, later, SQLite persistence)."""

from scribely.session.live import LiveSessionManager, SessionError

__all__ = ["LiveSessionManager", "SessionError"]
