import sqlite3
import pandas as pd
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = "trading_signals.db"

def cleanup_duplicates():
    if not os.path.exists(DB_PATH):
        logger.error(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Get all OPEN trades
        query = "SELECT id, code, buy_date FROM trade_records WHERE status='OPEN' ORDER BY code, buy_date ASC"
        df = pd.read_sql_query(query, conn)

        if df.empty:
            logger.info("No OPEN trades found.")
            return

        logger.info(f"Found {len(df)} OPEN records.")

        # 2. Identify duplicates
        # Keep the FIRST record (earliest buy_date) for each code
        ids_to_keep = df.groupby('code')['id'].first().tolist()
        
        # All other IDs for these codes in OPEN status should be deleted (or marked as CLOSED/INVALID)
        # Here we will DELETE them as per user instruction "清理重复开仓记录"
        
        all_ids = df['id'].tolist()
        ids_to_delete = list(set(all_ids) - set(ids_to_keep))

        if not ids_to_delete:
            logger.info("No duplicates found to delete.")
            return

        logger.info(f"Found {len(ids_to_delete)} duplicate records to delete.")
        
        # 3. Delete duplicates
        # Convert list to string for SQL IN clause
        ids_str = ','.join(map(str, ids_to_delete))
        delete_query = f"DELETE FROM trade_records WHERE id IN ({ids_str})"
        
        cursor.execute(delete_query)
        deleted_count = cursor.rowcount
        
        conn.commit()
        logger.info(f"Successfully deleted {deleted_count} duplicate records.")

        # 4. Verify results
        verify_query = "SELECT code, COUNT(*) as cnt FROM trade_records WHERE status='OPEN' GROUP BY code HAVING cnt > 1"
        cursor.execute(verify_query)
        remaining_duplicates = cursor.fetchall()
        
        if remaining_duplicates:
            logger.warning(f"Verification Failed: Still found duplicates: {remaining_duplicates}")
        else:
            logger.info("Verification Passed: No duplicate OPEN positions remain.")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup_duplicates()
