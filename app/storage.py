import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from contextlib import contextmanager
from app.config import settings

class Database:
    def __init__(self, db_url: str):
        # Extract path from sqlite URL
        if db_url.startswith('sqlite:///'):
            # Remove sqlite:/// prefix
            path = db_url.replace('sqlite:///', '', 1)
            
            # Handle relative paths (./app.db)
            if path.startswith('./'):
                path = path[2:]  # Remove ./
            
            # Make it absolute path
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            
            self.db_path = path
        else:
            raise ValueError(f"Invalid database URL: {db_url}")
        
        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        print(f"Database path: {self.db_path}")  # Debug print
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    from_msisdn TEXT NOT NULL,
                    to_msisdn TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    text TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            # Create index for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_from 
                ON messages(from_msisdn)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_ts 
                ON messages(ts)
            """)
    
    def is_ready(self) -> bool:
        """Check if database is ready"""
        try:
            with self.get_connection() as conn:
                conn.execute("SELECT 1 FROM messages LIMIT 1")
            return True
        except Exception:
            return False
    
    def insert_message(self, message_id: str, from_msisdn: str, to_msisdn: str, 
                      ts: str, text: Optional[str]) -> Tuple[bool, bool]:
        """
        Insert a message into the database.
        Returns: (success, is_duplicate)
        """
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO messages (message_id, from_msisdn, to_msisdn, ts, text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (message_id, from_msisdn, to_msisdn, ts, text, created_at))
            return True, False  # Success, not a duplicate
        except sqlite3.IntegrityError:
            # Duplicate message_id
            return True, True  # Success (idempotent), is a duplicate
    
    def get_messages(self, limit: int = 10, offset: int = 0, 
                    from_msisdn: Optional[str] = None,
                    since: Optional[str] = None,
                    q: Optional[str] = None) -> Tuple[List[dict], int]:
        """
        Get messages with pagination and filters.
        Returns: (messages, total_count)
        """
        with self.get_connection() as conn:
            # Build WHERE clause
            where_clauses = []
            params = []
            
            if from_msisdn:
                where_clauses.append("from_msisdn = ?")
                params.append(from_msisdn)
            
            if since:
                where_clauses.append("ts >= ?")
                params.append(since)
            
            if q:
                where_clauses.append("text LIKE ?")
                params.append(f"%{q}%")
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            count_query = f"SELECT COUNT(*) as count FROM messages WHERE {where_sql}"
            total = conn.execute(count_query, params).fetchone()['count']
            
            # Get paginated results
            query = f"""
                SELECT message_id, from_msisdn, to_msisdn, ts, text
                FROM messages
                WHERE {where_sql}
                ORDER BY ts ASC, message_id ASC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            
            cursor = conn.execute(query, params)
            messages = [dict(row) for row in cursor.fetchall()]
            
            return messages, total
    
    def get_stats(self) -> dict:
        """Get message statistics"""
        with self.get_connection() as conn:
            # Total messages
            total = conn.execute("SELECT COUNT(*) as count FROM messages").fetchone()['count']
            
            # Unique senders
            senders = conn.execute(
                "SELECT COUNT(DISTINCT from_msisdn) as count FROM messages"
            ).fetchone()['count']
            
            # Messages per sender (top 10)
            per_sender = conn.execute("""
                SELECT from_msisdn, COUNT(*) as count
                FROM messages
                GROUP BY from_msisdn
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()
            
            # First and last message timestamps
            timestamps = conn.execute("""
                SELECT MIN(ts) as first_ts, MAX(ts) as last_ts
                FROM messages
            """).fetchone()
            
            return {
                'total_messages': total,
                'senders_count': senders,
                'messages_per_sender': [
                    {'from': row['from_msisdn'], 'count': row['count']}
                    for row in per_sender
                ],
                'first_message_ts': timestamps['first_ts'],
                'last_message_ts': timestamps['last_ts']
            }

# Global database instance
db = None

def get_db() -> Database:
    """Get database instance"""
    global db
    if db is None:
        db = Database(settings.database_url)
    return db