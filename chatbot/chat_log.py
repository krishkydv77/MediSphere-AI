"""
Saves every chatbot message (text / image / voice) into the `chat_messages` table of the SAME
database the chatbot already uses (users, doctors, bookings ...).

Logging must never break a chat reply, so every function swallows its own errors.
"""
import html
import re

from src.logger import get_logger

logger = get_logger(__name__)


def html_to_text(reply_html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", reply_html or "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


def save_chat_message(db, user_id, channel: str, user_text: str, bot_reply_html: str, **meta):
    """Returns message_id (or None if saving failed). meta: language, audio_path, stt_ms, chat_ms, tts_ms, total_ms"""
    try:
        from chatbot.database.models import ChatMessage

        row = ChatMessage(
            user_id=user_id,
            channel=channel,
            user_text=user_text,
            bot_reply=html_to_text(bot_reply_html),
            **{k: v for k, v in meta.items() if v is not None},
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.message_id
    except Exception as e:
        logger.error(f"save_chat_message failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def update_chat_timing(message_id, **fields):
    """Voice: tts_ms / total_ms are known only after audio is streamed, so update the row afterwards."""
    if not message_id:
        return
    try:
        from chatbot.database.db_config import SessionLocal
        from chatbot.database.models import ChatMessage

        db = SessionLocal()
        try:
            db.query(ChatMessage).filter(ChatMessage.message_id == message_id).update(fields)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"update_chat_timing failed: {e}")
