import requests
import datetime
import time
import pytz
import os

# CONFIG
ZIP_CODE = "97005"
LAT = 45.4871   # Approx for Beaverton
LON = -122.8037
OUTPUT_FILE = "/tmp/weather_receipt.txt"
PRINTER_NAME = "POS58"  # Change to your CUPS printer name

def get_weather():
    # Step 1: Get grid data from NWS
    points_url = f"https://api.weather.gov/points/{LAT},{LON}"
    headers = {"User-Agent": "weather-script (your@email.com)"}
    
    points_resp = requests.get(points_url, headers=headers)
    points_data = points_resp.json()
    
    forecast_url = points_data["properties"]["forecast"]
    
    # Step 2: Get forecast
    forecast_resp = requests.get(forecast_url, headers=headers)
    forecast_data = forecast_resp.json()
    
    today = forecast_data["properties"]["periods"][0]
    
    return {
        "name": today["name"],
        "temp": today["temperature"],
        "unit": today["temperatureUnit"],
        "forecast": today["detailedForecast"]
    }

def format_receipt(weather):
    now = datetime.datetime.now()
    
    receipt = []
    receipt.append("\n***** DAILY WEATHER *****")
    receipt.append(now.strftime("%Y-%m-%d %H:%M"))
    receipt.append("------------------------")
    receipt.append(f"Location: {ZIP_CODE}")
    receipt.append(f"{weather['name']}")
    receipt.append(f"Temp: {weather['temp']}*{weather['unit']}")
    receipt.append("------------------------")
    
    # Wrap forecast text for receipt width (~32 chars)
    words = weather["forecast"].split()
    line = ""
    for word in words:
        if len(line) + len(word) + 1 <= 32:
            line += " " + word if line else word
        else:
            receipt.append(line)
            line = word
    if line:
        receipt.append(line)
    
    receipt.append("------------------------")
    receipt.append("Printed via NWS API \n\n\n")
    
    return "\n".join(receipt)

def save_to_file(text):
    with open(OUTPUT_FILE, "w") as f:
        f.write(text)

def print_file():
    # Send to CUPS printer
    os.system(f"lp -d {PRINTER_NAME} {OUTPUT_FILE}")

def run_job():
    try:
        weather = get_weather()
        receipt_text = format_receipt(weather)
        save_to_file(receipt_text)
        print_file()
        print("Weather printed successfully.")
    except Exception as e:
        print("Error:", e)

def wait_until_6am():
    tz = pytz.timezone("America/Los_Angeles")
    
    while True:
        now = datetime.datetime.now(tz)
        target = now.replace(hour=6, minute=5, second=0, microsecond=0)
        
        if now >= target:
            target += datetime.timedelta(days=1)
        
        sleep_seconds = (target - now).total_seconds()
        print(f"Sleeping for {sleep_seconds/3600:.2f} hours until 6:05AM...")
        time.sleep(sleep_seconds)
        
        run_job()

if __name__ == "__main__":
    wait_until_6am()
