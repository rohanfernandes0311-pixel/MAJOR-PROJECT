"""
==============================================================
 Landslide Early Warning Alert System
==============================================================
Implements:
  1. Threshold-based alert classification
  2. Telegram Bot notification
  3. Twilio WhatsApp notification
  4. Alert log + history

Risk Thresholds (configurable):
  HIGH   → deformation > 25 mm OR rainfall > 150 mm OR IVM failure < 14 days
  MEDIUM → deformation > 10 mm OR rainfall > 80 mm  OR IVM failure < 60 days
  LOW    → otherwise

Setup instructions printed when credentials are missing.
"""

import os
import json
import logging
import requests
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict

# ─────────────────────────────────────────────────────────────
# Config / Credentials  (set via environment variables)
# ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")
TWILIO_SID         = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH        = os.getenv("TWILIO_AUTH_TOKEN",  "")
TWILIO_FROM        = os.getenv("TWILIO_WHATSAPP_FROM","whatsapp:+14155238886")
TWILIO_TO          = os.getenv("TWILIO_WHATSAPP_TO",  "")

LOG_DIR  = Path(__file__).parent / "alerts"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "alert_log.jsonl"

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("AlertSystem")


# ─────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────

@dataclass
class SensorReading:
    """Real-time environmental + InSAR observation."""
    timestamp        : str   = field(default_factory=lambda: datetime.utcnow().isoformat())
    latitude         : float = 0.0
    longitude        : float = 0.0
    location_name    : str   = "Unknown"
    deformation_mm   : float = 0.0
    velocity_mm_yr   : float = 0.0
    rainfall_mm      : float = 0.0
    slope_deg        : float = 0.0
    soil_moisture_pct: float = 0.0
    coherence        : float = 0.9
    ivm_failure_days : float = 9999.0   # IVM estimated days to failure
    ml_risk_label    : str   = "Low"    # RF/XGB prediction
    ml_confidence    : float = 0.0


@dataclass
class Alert:
    """An alert event."""
    alert_id     : str
    timestamp    : str
    risk_level   : str          # LOW / MEDIUM / HIGH / CRITICAL
    location_name: str
    latitude     : float
    longitude    : float
    trigger      : str          # What triggered the alert
    message      : str
    sent_telegram: bool = False
    sent_whatsapp: bool = False


# ─────────────────────────────────────────────────────────────
# 1.  Threshold-based classifier
# ─────────────────────────────────────────────────────────────

THRESHOLDS = {
    "deformation_mm"   : {"HIGH": 25.0, "MEDIUM": 10.0},
    "rainfall_mm"      : {"HIGH": 150.0,"MEDIUM": 80.0},
    "ivm_failure_days" : {"HIGH": 14.0, "MEDIUM": 60.0},   # lower = more urgent
    "velocity_mm_yr"   : {"HIGH": 60.0, "MEDIUM": 25.0},
    "soil_moisture_pct": {"HIGH": 80.0, "MEDIUM": 60.0},
}


def classify_alert_level(reading: SensorReading) -> tuple[str, list[str]]:
    """
    Determine alert level from sensor reading.
    
    Returns:
        (level, triggers) where triggers is a list of violated thresholds
    """
    triggers_high   = []
    triggers_medium = []

    # Deformation
    if reading.deformation_mm >= THRESHOLDS["deformation_mm"]["HIGH"]:
        triggers_high.append(f"Deformation {reading.deformation_mm:.1f} mm ≥ {THRESHOLDS['deformation_mm']['HIGH']} mm")
    elif reading.deformation_mm >= THRESHOLDS["deformation_mm"]["MEDIUM"]:
        triggers_medium.append(f"Deformation {reading.deformation_mm:.1f} mm")

    # Rainfall
    if reading.rainfall_mm >= THRESHOLDS["rainfall_mm"]["HIGH"]:
        triggers_high.append(f"Rainfall {reading.rainfall_mm:.1f} mm ≥ {THRESHOLDS['rainfall_mm']['HIGH']} mm")
    elif reading.rainfall_mm >= THRESHOLDS["rainfall_mm"]["MEDIUM"]:
        triggers_medium.append(f"Rainfall {reading.rainfall_mm:.1f} mm")

    # IVM failure estimate
    if 0 < reading.ivm_failure_days <= THRESHOLDS["ivm_failure_days"]["HIGH"]:
        triggers_high.append(f"IVM failure estimate: {reading.ivm_failure_days:.1f} days")
    elif 0 < reading.ivm_failure_days <= THRESHOLDS["ivm_failure_days"]["MEDIUM"]:
        triggers_medium.append(f"IVM failure estimate: {reading.ivm_failure_days:.1f} days")

    # Velocity
    if reading.velocity_mm_yr >= THRESHOLDS["velocity_mm_yr"]["HIGH"]:
        triggers_high.append(f"Velocity {reading.velocity_mm_yr:.1f} mm/yr")
    elif reading.velocity_mm_yr >= THRESHOLDS["velocity_mm_yr"]["MEDIUM"]:
        triggers_medium.append(f"Velocity {reading.velocity_mm_yr:.1f} mm/yr")

    # ML model override
    if reading.ml_risk_label == "High" and reading.ml_confidence > 0.70:
        triggers_high.append(f"ML model: High risk ({reading.ml_confidence:.0%} confidence)")
    elif reading.ml_risk_label == "Medium":
        triggers_medium.append(f"ML model: Medium risk ({reading.ml_confidence:.0%} confidence)")

    if triggers_high:
        return "HIGH", triggers_high
    elif triggers_medium:
        return "MEDIUM", triggers_medium
    return "LOW", ["All parameters within safe limits"]


# ─────────────────────────────────────────────────────────────
# 2.  Alert message composer
# ─────────────────────────────────────────────────────────────

EMOJI = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢", "CRITICAL": "🚨"}

def compose_message(reading: SensorReading, level: str, triggers: list[str]) -> str:
    """Compose a human-readable alert message."""
    emoji = EMOJI.get(level, "⚠️")
    lines = [
        f"{emoji} LANDSLIDE {level} RISK ALERT {emoji}",
        f"📍 Location : {reading.location_name}",
        f"🕐 Time     : {reading.timestamp[:19]} UTC",
        f"🌐 Coords   : {reading.latitude:.4f}°N, {reading.longitude:.4f}°E",
        "",
        "📊 Sensor Readings:",
        f"   • InSAR Deformation : {reading.deformation_mm:.2f} mm",
        f"   • LOS Velocity      : {reading.velocity_mm_yr:.1f} mm/yr",
        f"   • InSAR Coherence   : {reading.coherence:.3f}",
        f"   • 7-day Rainfall    : {reading.rainfall_mm:.1f} mm",
        f"   • Slope             : {reading.slope_deg:.1f}°",
        f"   • Soil Moisture     : {reading.soil_moisture_pct:.1f}%",
        f"   • IVM Failure Est.  : {reading.ivm_failure_days:.0f} days",
        f"   • ML Risk Label     : {reading.ml_risk_label} ({reading.ml_confidence:.0%})",
        "",
        "⚠️ Triggered by:",
    ]
    for t in triggers:
        lines.append(f"   ✗ {t}")
    lines += [
        "",
        "🏥 Recommended Action:",
    ]
    if level == "HIGH":
        lines += [
            "   → EVACUATE affected communities immediately",
            "   → Notify NDMA / District Disaster Management Authority",
            "   → Deploy field assessment teams",
            "   → Close access roads in hazard zone",
        ]
    elif level == "MEDIUM":
        lines += [
            "   → Issue precautionary advisory to residents",
            "   → Increase monitoring frequency to 6-hourly",
            "   → Pre-position emergency response teams",
        ]
    else:
        lines += [
            "   → Continue routine monitoring",
            "   → No immediate action required",
        ]
    lines.append("")
    lines.append("— Landslide Early Warning System | Auto-generated Alert —")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# 3.  Telegram sender
# ─────────────────────────────────────────────────────────────

def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """
    Send alert via Telegram Bot API.
    
    Setup:
      1. Create bot: message @BotFather → /newbot
      2. Get token → set TELEGRAM_BOT_TOKEN env var
      3. Find your chat_id → set TELEGRAM_CHAT_ID env var
         (send any message to bot, then:
          curl https://api.telegram.org/bot<TOKEN>/getUpdates)
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning(
            "Telegram credentials not set. "
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables."
        )
        # Simulate for demo
        logger.info(f"[SIMULATED TELEGRAM]\n{message}")
        return False

    url     = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id"   : TELEGRAM_CHAT_ID,
        "text"      : message,
        "parse_mode": parse_mode,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"✅ Telegram alert sent to chat {TELEGRAM_CHAT_ID}")
            return True
        else:
            logger.error(f"Telegram error: {resp.status_code} {resp.text}")
            return False
    except requests.RequestException as e:
        logger.error(f"Telegram network error: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# 4.  WhatsApp sender (Twilio)
# ─────────────────────────────────────────────────────────────

def send_whatsapp(message: str) -> bool:
    """
    Send alert via Twilio WhatsApp API.
    
    Setup:
      1. Create Twilio account → https://twilio.com
      2. Enable WhatsApp sandbox or WhatsApp Business
      3. Set env vars: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                       TWILIO_WHATSAPP_FROM, TWILIO_WHATSAPP_TO
         TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886" (sandbox)
         TWILIO_WHATSAPP_TO   = "whatsapp:+91XXXXXXXXXX"
    """
    if not all([TWILIO_SID, TWILIO_AUTH, TWILIO_TO]):
        logger.warning("Twilio credentials not set — simulating WhatsApp alert.")
        logger.info(f"[SIMULATED WHATSAPP]\n{message[:500]}...")
        return False

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_AUTH)
        msg = client.messages.create(
            body = message[:1600],   # WhatsApp 1600-char limit
            from_= TWILIO_FROM,
            to   = TWILIO_TO
        )
        logger.info(f"✅ WhatsApp alert sent. SID: {msg.sid}")
        return True
    except ImportError:
        logger.warning("twilio package not installed: pip install twilio")
        return False
    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# 5.  Alert orchestrator
# ─────────────────────────────────────────────────────────────

def process_reading(
    reading   : SensorReading,
    send_only_above: str = "LOW"  # Only send notifications for MEDIUM / HIGH
) -> Alert:
    """
    Full alert pipeline:
      classify → compose → notify → log
    """
    level, triggers = classify_alert_level(reading)
    message  = compose_message(reading, level, triggers)
    alert_id = f"ALERT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    alert = Alert(
        alert_id      = alert_id,
        timestamp     = reading.timestamp,
        risk_level    = level,
        location_name = reading.location_name,
        latitude      = reading.latitude,
        longitude     = reading.longitude,
        trigger       = " | ".join(triggers),
        message       = message,
    )

    levels_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    if levels_order.get(level, 0) >= levels_order.get(send_only_above, 0):
        try:
            alert.sent_telegram = send_telegram(message)
            alert.sent_whatsapp = send_whatsapp(message)
            if not (alert.sent_telegram or alert.sent_whatsapp):
                raise RuntimeError("Primary notification channels unavailable")
        except Exception:
            try:
                from mesh_comm import send_mesh_alert
                alert_dict = {
                    "id": alert.alert_id,
                    "timestamp": alert.timestamp,
                    "location": (reading.latitude, reading.longitude),
                    "risk_level": alert.risk_level,
                    "message": alert.message,
                    "ttl": 6,
                }
                send_mesh_alert(alert_dict)
            except Exception:
                pass

    # Log to JSONL
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(asdict(alert)) + "\n")

    return alert


def load_alert_history(n: int = 50) -> list[dict]:
    """Load the last n alerts from the log."""
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE) as f:
        lines = f.readlines()
    return [json.loads(l) for l in lines[-n:]]


# ─────────────────────────────────────────────────────────────
# 6.  Demo / test
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Simulate a HIGH-risk reading
    r = SensorReading(
        location_name     = "Munnar Hills, Kerala",
        latitude          = 10.089,
        longitude         = 77.060,
        deformation_mm    = 31.4,
        velocity_mm_yr    = 72.0,
        rainfall_mm       = 178.5,
        slope_deg         = 38.2,
        soil_moisture_pct = 84.3,
        coherence         = 0.42,
        ivm_failure_days  = 8.0,
        ml_risk_label     = "High",
        ml_confidence     = 0.87,
    )
    alert = process_reading(r, send_only_above="LOW")
    print(f"\nAlert ID   : {alert.alert_id}")
    print(f"Risk Level : {alert.risk_level}")
    print(f"Logged to  : {LOG_FILE}")
