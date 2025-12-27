import os
import traceback
from datetime import datetime
from pathlib import Path

# Log file location
LOG_DIR = Path(__file__).parent
LOG_FILE = LOG_DIR / "local_errors.log"

def log_error(error, context=None):
    """
    Logs errors to a local file for development testing.
    Only logs when ENVIRONMENT is development or not set.
    """
    env = os.getenv("ENVIRONMENT", "development")
    
    # Only log in development/local
    if env not in ["development", "dev", None]:
        return
    
    try:
        # Create log entry
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = f"""
{'='*80}
ERROR LOGGED: {timestamp}
{'='*80}

Error Type: {type(error).__name__}
Error Message: {str(error)}

"""
        
        # Add context if provided
        if context:
            log_entry += f"Context: {context}\n\n"
        
        # Add full traceback
        log_entry += "Full Traceback:\n"
        log_entry += "".join(traceback.format_exception(type(error), error, error.__traceback__))
        
        log_entry += f"\n{'='*80}\n\n"
        
        # Write to file (append mode)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        
        # Also print to console for immediate visibility
        print(f"❌ Error logged to {LOG_FILE}")
        print(f"   Error: {type(error).__name__}: {str(error)}")
        
    except Exception as log_error:
        # Fallback if logging itself fails
        print(f"⚠️  Failed to write error log: {log_error}")

# Initialize: Create log file if it doesn't exist
if not LOG_FILE.exists():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Local Error Log - Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")

