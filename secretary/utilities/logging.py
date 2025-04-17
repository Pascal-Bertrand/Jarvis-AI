"""This will log every message that is incoming or outgoing"""

import logging
import os
from datetime import datetime
import traceback

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# Generate a filename based on current date and time
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join(logs_dir, f"log_{current_time}.txt")

# Configure logger
logger = logging.getLogger("AgentAI")
logger.setLevel(logging.DEBUG)

# Create file handler
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def log_user_message(user_id, message):
    """Log a message from a user"""
    logger.info(f"USER ({user_id}): {message}")

def log_agent_message(agent_id, message):
    """Log a message from an agent"""
    logger.info(f"AGENT ({agent_id}): {message}")

def log_system_message(message):
    """Log a system message"""
    logger.info(f"SYSTEM: {message}")

def log_api_request(api_name, request_data):
    """Log an API request"""
    logger.debug(f"API REQUEST ({api_name}): {request_data}")

def log_api_response(api_name, response_data):
    """Log an API response"""
    logger.debug(f"API RESPONSE ({api_name}): {response_data}")

def log_network_message(sender_id, recipient_id, content):
    """Log a message sent through the network"""
    logger.info(f"NETWORK: From {sender_id} to {recipient_id}: {content}")

def log_error(error_message, include_traceback=True):
    """Log an error message with optional traceback"""
    if include_traceback:
        error_message = f"{error_message}\n{traceback.format_exc()}"
    logger.error(f"ERROR: {error_message}")

def log_warning(warning_message):
    """Log a warning message"""
    logger.warning(f"WARNING: {warning_message}")

# Initialize with startup message
logger.info(f"======= AgentAI Logging Started at {current_time} =======")
print(f"Logging to file: {log_file}")
