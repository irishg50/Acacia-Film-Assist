import sys
import os

# Ensure the current directory is in the path so imports work
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
import logging

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

configure_logging()
app = create_app()

if __name__ == '__main__':
    print("Starting Flask app from run.py")
    app.run(debug=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

app.logger.info("Application started")