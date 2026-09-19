import requests
import datetime
import threading
import time
import pytz
import os
import textwrap

# ==========================================================
# CONFIGURATION
# ==========================================================

ZIP_CODE = "97005"

# Beaverton, OR
LAT = 45.4871
LON = -122.8037

# Output receipt dir
OUTPUT_DIR = "/tmp"

# CUPS printer name
PRINTER_NAME = "POS58"

# NWS User-Agent (replace with your own email)
HEADERS = {
    "User-Agent": "weather-printer (your@email.com)"
}

# Check every 5 minutes after 6:00 AM until the daytime
# forecast becomes available.
FORECAST_CHECK_INTERVAL = 300  # seconds

# Check for emergency alerts every minute.
ALERT_CHECK_INTERVAL = 60  # seconds

# Time to begin looking for the daytime forecast
DAILY_PRINT_HOUR = 6
DAILY_PRINT_MINUTE = 0

# ==========================================================
# API ENDPOINTS
# ==========================================================

POINTS_URL = f"https://api.weather.gov/points/{LAT},{LON}"

ALERT_URL = (
    f"https://api.weather.gov/alerts/active?point={LAT},{LON}"
)

# ==========================================================
# GLOBAL STATE
# ==========================================================

# Keeps track of alert IDs we've already printed so
# duplicate alerts are not reprinted.
printed_alerts = set()

# Keeps track of the last date we printed the daily forecast.
last_forecast_date = None

# Thread lock to prevent two threads from trying to print
# at exactly the same time.
printer_lock = threading.Lock()

# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================

def wrap_text(text, width=32):
    """
    Wrap text to fit a typical 58mm receipt printer.
    """
    return textwrap.wrap(text, width=width)


def save_to_file(text):
    filename = (
        f"{OUTPUT_DIR}/weather_receipt_"
        f"{int(time.time())}.txt"
    )

    with open(filename, "w") as f:
        f.write(text)

    return filename

def print_file():
    """
    Send the receipt file to the configured CUPS printer.
    """
    os.system(f'lp -d "{PRINTER_NAME}" "{OUTPUT_FILE}"')

def print_receipt(text):
    with printer_lock:

        filename = save_to_file(text)

        time.sleep(0.25)

        os.system(
            f'lp -d "{PRINTER_NAME}" "{filename}"'
        )

        time.sleep(1)

def current_time():
    """
    Return the current Pacific Time.
    """
    tz = pytz.timezone("America/Los_Angeles")
    return datetime.datetime.now(tz)


def log(message):
    """
    Print timestamped messages to the console.
    """
    timestamp = current_time().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    
# ==========================================================
# API FUNCTIONS
# ==========================================================

forecast_url = None


def get_forecast_url():
    """
    Retrieve the forecast URL for the configured latitude
    and longitude. This normally only needs to be done once.
    """
    global forecast_url

    if forecast_url:
        return forecast_url

    response = requests.get(POINTS_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()

    data = response.json()

    forecast_url = data["properties"]["forecast"]

    return forecast_url


def get_weather():
    """
    Return the first available daytime forecast.

    Returns:
        dict or None

    None means the NWS has not yet published a daytime
    forecast (usually still showing 'Overnight').
    """

    url = get_forecast_url()

    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    periods = response.json()["properties"]["periods"]

    for period in periods:

        if not period["isDaytime"]:
            continue

        # Ignore "This Afternoon" after today's forecast
        # has already been printed.
        return {
            "name": period["name"],
            "temperature": period["temperature"],
            "unit": period["temperatureUnit"],
            "forecast": period["detailedForecast"]
        }

    return None


def get_active_alerts():
    """
    Return all active NWS alerts for this location.

    Returns an empty list if there are no alerts.
    """

    response = requests.get(
        ALERT_URL,
        headers=HEADERS,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    return data.get("features", [])


def get_new_alerts():
    """
    Return only alerts that have not already been printed.
    """

    global printed_alerts

    new_alerts = []

    for alert in get_active_alerts():

        alert_id = alert.get("id")

        if alert_id in printed_alerts:
            continue

        printed_alerts.add(alert_id)
        new_alerts.append(alert)

    return new_alerts

# ==========================================================
# RECEIPT FORMATTING FUNCTIONS
# ==========================================================

def format_weather_receipt(weather):
    """
    Format the daily forecast into a thermal receipt layout.
    """

    now = current_time()

    receipt = []

    receipt.append("")
    receipt.append("************************")
    receipt.append("     DAILY WEATHER")
    receipt.append("************************")
    receipt.append("")

    receipt.append(
        now.strftime("%Y-%m-%d %H:%M")
    )

    receipt.append("------------------------")

    receipt.append(
        f"Location: {ZIP_CODE}"
    )

    receipt.append("")

    receipt.append(
        weather["name"]
    )

    receipt.append(
        f"Temp: {weather['temperature']}{weather['unit']}"
    )

    receipt.append("------------------------")

    receipt.append("")

    forecast_lines = wrap_text(
        weather["forecast"],
        32
    )

    receipt.extend(forecast_lines)

    receipt.append("")
    receipt.append("------------------------")
    receipt.append("Printed via NWS API")
    receipt.append("")
    receipt.append("")
    receipt.append("")

    return "\n".join(receipt)


def format_alert_receipt(alert):
    """
    Format an emergency weather alert receipt.
    """

    props = alert["properties"]

    receipt = []

    receipt.append("")
    receipt.append("************************")
    receipt.append("     WEATHER ALERT")
    receipt.append("************************")
    receipt.append("")

    receipt.append(
        props.get(
            "event",
            "Weather Alert"
        )
    )

    receipt.append("------------------------")

    if props.get("headline"):
        receipt.extend(
            wrap_text(
                props["headline"],
                32
            )
        )

    receipt.append("")

    if props.get("description"):
        receipt.extend(
            wrap_text(
                props["description"],
                32
            )
        )

    if props.get("instruction"):

        receipt.append("")
        receipt.append("ACTION:")

        receipt.extend(
            wrap_text(
                props["instruction"],
                32
            )
        )

    receipt.append("")
    receipt.append("------------------------")
    receipt.append("")

    return "\n".join(receipt)
    
# ==========================================================
# WEATHER AND ALERT WORKER FUNCTIONS
# ==========================================================

def print_daily_forecast():
    """
    Get the daytime forecast and print it.
    """

    global last_forecast_date

    weather = get_weather()

    if weather is None:
        log("Daytime forecast not available yet.")
        return False

    today = current_time().date()

    if last_forecast_date == today:
        return True

    log(
        f"Daytime forecast found: {weather['name']}"
    )

    receipt = format_weather_receipt(weather)

    log("Printing daily forecast...")
    print("----- RECEIPT DEBUG -----")
    print(receipt)
    print("-------------------------")
    print_receipt(receipt)

    last_forecast_date = today

    log("Daily forecast printed successfully.")

    return True


def check_for_alerts():
    """
    Check for new NWS alerts and print them.
    """

    alerts = get_new_alerts()

    for alert in alerts:

        props = alert["properties"]

        event = props.get(
            "event",
            "Unknown Alert"
        )

        log(
            f"New alert detected: {event}"
        )

        receipt = format_alert_receipt(alert)

        print_receipt(receipt)

        log(
            "Alert printed successfully."
        )


def alert_loop():
    """
    Runs continuously and checks for emergency alerts.
    """

    log("Alert monitoring started.")

    while True:

        try:
            check_for_alerts()

        except Exception as e:
            log(
                f"Alert check error: {e}"
            )

        time.sleep(
            ALERT_CHECK_INTERVAL
        )


def wait_until_daily_check_time():
    """
    Wait until the configured daily forecast check time.
    """

    while True:

        now = current_time()

        target = now.replace(
            hour=DAILY_PRINT_HOUR,
            minute=DAILY_PRINT_MINUTE,
            second=0,
            microsecond=0
        )

        if now >= target:
            return

        seconds = (
            target - now
        ).total_seconds()

        log(
            f"Waiting {seconds/3600:.2f} hours until forecast check."
        )

        time.sleep(
            min(seconds, 3600)
        )


def daily_forecast_loop():
    """
    Runs once per day.

    After 6:00 AM it checks every 5 minutes until
    the daytime forecast is available.
    """

    log("Daily forecast scheduler started.")

    while True:

        try:

            wait_until_daily_check_time()

            log(
                "Beginning daytime forecast checks."
            )

            while True:

                if print_daily_forecast():
                    break

                time.sleep(
                    FORECAST_CHECK_INTERVAL
                )

        except Exception as e:

            log(
                f"Forecast scheduler error: {e}"
            )

        # Wait until the next day
        time.sleep(60)
        
# ==========================================================
# PROGRAM STARTUP
# ==========================================================

def main():
    """
    Start the weather printer service.
    """

    log("Weather Printer starting...")

    # Start 24/7 emergency alert monitoring
    alert_thread = threading.Thread(
        target=alert_loop,
        daemon=True
    )

    alert_thread.start()

    # Start daily forecast scheduler
    forecast_thread = threading.Thread(
        target=daily_forecast_loop,
        daemon=True
    )

    forecast_thread.start()

    log("Weather Printer is running.")

    try:
        # Keep the main program alive.
        # Worker threads run in the background.
        while True:
            time.sleep(60)

    except KeyboardInterrupt:

        log("Stopping Weather Printer...")
        log("Goodbye.")


if __name__ == "__main__":
    main()
