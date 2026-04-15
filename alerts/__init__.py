"""
Alert System
Sends notifications via Telegram, Discord, Email, and generates TradingView alerts.
"""

import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from loguru import logger

from models import TradingSignal, SignalDirection, StrategyType
from config import get_config
from alerts.telegram_bot import SignalDuplicateChecker
from alerts.alert_manager import AlertManager
from alerts.signal_publisher import SignalPublisher, get_signal_publisher
