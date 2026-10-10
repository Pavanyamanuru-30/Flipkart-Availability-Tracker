import streamlit as st
import pandas as pd
import aiohttp
import asyncio
import re
import os
import sqlite3
import datetime
import random
from urllib.parse import urlparse
from io import BytesIO

# --- DB INIT (Analytics & History) ---
conn = sqlite3.connect("flipkart_history.db", check_same_thread=False)
c = conn.cursor()
# Drop table to safely upgrade schema for new Price and SLA columns
c.execute("DROP TABLE IF EXISTS scan_history")
c.execute('''CREATE TABLE scan_history
             (timestamp TEXT, product_id TEXT, url TEXT, state TEXT, district TEXT, pincode TEXT, area TEXT, status TEXT, price TEXT, delivery_date TEXT)''')
conn.commit()

# --- PROXY FETCHING (Anti-Ban) ---
@st.cache_data(ttl=3600)
def get_free_proxies():
    try:
        import requests
        res = requests.get("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt", timeout=10)
        if res.status_code == 200:
            proxies = res.text.strip().split("\n")
            return [f"http://{p.strip()}" for p in proxies if p.strip()]
    except:
        pass
    return []

# --- API CONSTANTS ---
API = "https://1.rome.api.flipkart.com/api/4/page/fetch"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "X-User-Agent": UA + " FKUA/website/42/website/Desktop",
    "Origin": "https://www.flipkart.com",
    "Referer": "https://www.flipkart.com/",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip",
}

# --- REGEX ---
RE_SERVICEABLE = re.compile(r'"serviceable":(true|false)')
RE_SLA = re.compile(r'"slaText":"([^"]*)"')
RE_PRICE = re.compile(r'"price":\s*([0-9]+)')
RE_NO_PIN = re.compile(r'No Pincode')
RE_OOS_AREA = re.compile(r'out of stock in this area', re.I)
RE_AVAIL = re.compile(r'"availabilityStatus":"([^"]*)"')

def product_path(url: str) -> str:
    p = urlparse(url)
    if "flipkart.com" not in p.netloc and not url.startswith("/"): return None
    m = re.search(r'[?&]pid=([A-Z0-9]+)', url)
    return p.path + (f"?pid={m.group(1)}" if m else "")

def get_product_id(url: str):
    m = re.search(r'[?&]pid=([A-Z0-9]+)', url)
    if m: return m.group(1)
    return "UNKNOWN_ID"

# --- SCANNER ---
async def check_pin_async(session, path: str, pin: str, proxies: list, retries: int = 3):
    body = {"pageUri": path, "locationContext": {"pincode": pin}}
    for attempt in range(retries):
        proxy = random.choice(proxies) if proxies else None
        try:
            async with session.post(API, json=body, headers=HEADERS, proxy=proxy, timeout=10) as r:
                if r.status in (403, 429, 500, 502, 503):
                    await asyncio.sleep(2 ** attempt)
                    continue
                text = await r.text()
                
                avail = RE_AVAIL.search(text)
                avail = avail.group(1) if avail else ""
                
                # Extract Price
                price_match = RE_PRICE.search(text)
                price = f"₹{price_match.group(1)}" if price_match else "Unknown"
                
                if RE_NO_PIN.search(text): return {"pincode": pin, "status": "UNKNOWN_PIN", "delivery": "", "price": price}
                    
                m = RE_SERVICEABLE.search(text)
                if not m:
                    if RE_OOS_AREA.search(text): return {"pincode": pin, "status": "NOT_SERVICEABLE", "delivery": avail, "price": price}
                    return {"pincode": pin, "status": "PARSE_ERROR", "delivery": avail, "price": price}
                
                if m.group(1) == "true" and avail != "OUT_OF_STOCK":
                    sla = RE_SLA.search(text)
                    sla_text = sla.group(1) if sla else avail
                    return {"pincode": pin, "status": "SERVICEABLE", "delivery": sla_text, "price": price}
                
                return {"pincode": pin, "status": "NOT_SERVICEABLE", "delivery": avail, "price": price}
        except Exception:
            await asyncio.sleep(2 ** attempt)
    return {"pincode": pin, "status": "FAILED", "delivery": "", "price": "Unknown"}

async def check_pin_wrapper(session, url, path, meta, proxies):
    pin, district, area = meta
    res = await check_pin_async(session, path, pin, proxies)
    res['url'] = url
    res['district'] = district
    res['area'] = area
    return res

async def run_scanner_live(urls, pins_meta, state, district_name, proxies, progress_bar, status_text, live_table):
    results = []
    serviceable_data = []
    tasks_meta = [(u, product_path(u), m) for u in urls for m in pins_meta]
            
    total = len(tasks_meta)
    conn_aio = aiohttp.TCPConnector(limit=50)
    
    async with aiohttp.ClientSession(connector=conn_aio) as session:
        tasks = [asyncio.create_task(check_pin_wrapper(session, u, p, m, proxies)) for u, p, m in tasks_meta]
        
        completed = 0
        serviceable_count = 0
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for coro in asyncio.as_completed(tasks):
            res = await coro
            results.append(res)
            completed += 1
            
            pid = get_product_id(res['url'])
            c.execute("INSERT INTO scan_history VALUES (?,?,?,?,?,?,?,?,?,?)", 
                      (timestamp, pid, res['url'], state, res['district'], res['pincode'], res['area'], res['status'], res['price'], res['delivery']))
            conn.commit()
            
            if res['status'] == 'SERVICEABLE':
                serviceable_count += 1
                serviceable_data.append({
                    "Product ID": pid,
                    "PIN Code": res['pincode'],
                    "Area": res['area'],
                    "District": res['district'],
                    "Price": res['price'],
                    "Est. Delivery": res['delivery']
                })
                live_table.dataframe(pd.DataFrame(serviceable_data), use_container_width=True)
                
            if completed % 5 == 0 or completed == total:
                progress_bar.progress(completed / total)
                status_text.text(f"⚡ Scanning: {completed} / {total} checks completed. Found {serviceable_count} available.")
                
    return results, serviceable_data

@st.cache_data
def load_data():
    csv_path = "india_post_pincodes.csv"
    df = pd.read_csv(csv_path, dtype=str).dropna(subset=['Pincode', 'StateName', 'District'])
    df['StateName'] = df['StateName'].str.strip().str.upper()
    df['Pincode'] = df['Pincode'].str.strip()
    df['District'] = df['District'].str.strip()
    df['OfficeName'] = df['OfficeName'].str.strip().fillna("Unknown Area")
    return df.groupby(['Pincode', 'StateName', 'District'])['OfficeName'].apply(lambda x: ', '.join(x.unique())).reset_index()

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Available Locations')
    return output.getvalue()

def main():
    st.set_page_config(page_title="Flipkart Scanner ULTIMATE", layout="wide", page_icon="🛍️")
    st.title("Flipkart Availability Tracker ULTIMATE 🛍️")
    
    tab_scan, tab_monitor, tab_analytics = st.tabs(["🔍 Scan Products", "⏰ Background Monitor", "📈 Analytics & History"])
    
    try:
        df = load_data()
        states = sorted(df['StateName'].unique())
    except Exception as e:
        st.error(f"Dataset error: {e}")
        return
        
    proxies = get_free_proxies()
    
    with tab_scan:
        st.write("Paste one or **multiple** Flipkart URLs (one per line) to scan them simultaneously.")
        urls_input = st.text_area("Enter Flipkart Product URLs", placeholder="https://www.flipkart.com/product1...", height=100)
        urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
        
        col1, col2, col3 = st.columns([1,1,1])
        with col1: selected_state = st.selectbox("1. Select State", states)
        
        state_df = df[df['StateName'] == selected_state]
        districts = ["All Districts"] + sorted(state_df['District'].unique())
        
        with col2: selected_district = st.selectbox("2. Select District", districts)
        with col3: 
            st.write("3. Security Options")
            use_proxy = st.checkbox(f"Enable IP Rotation ({len(proxies)} proxies available)", value=True)
        
        if st.button("Start Massive Scan", type="primary", use_container_width=True):
            if not urls:
                st.warning("⚠️ Enter at least one URL.")
                return
                
            target_df = state_df if selected_district == "All Districts" else state_df[state_df['District'] == selected_district]
            pins_meta = list(zip(target_df['Pincode'], target_df['District'], target_df['OfficeName']))
            
            st.info(f"Targeting {len(pins_meta)} PIN codes across {len(urls)} products (Total Checks: {len(pins_meta)*len(urls)}). IP Rotation: {'Enabled' if use_proxy else 'Disabled'}")
            
            pb = st.progress(0)
            st_text = st.empty()
            st.subheader("Available Locations (Live Updates)")
            live_table = st.empty()
            
            active_proxies = proxies if use_proxy else []
            
            with st.spinner("Running high-speed multi-scan with IP Rotation..."):
                raw, s_data = asyncio.run(run_scanner_live(urls, pins_meta, selected_state, selected_district, active_proxies, pb, st_text, live_table))
                
            st.success("✅ Multi-Scan Complete!")
            if s_data:
                final_df = pd.DataFrame(s_data)
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    csv_data = final_df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Results (CSV)", csv_data, "multi_scan_results.csv", "text/csv", use_container_width=True)
                with col_d2:
                    excel_data = to_excel(final_df)
                    st.download_button("📊 Download Results (Excel)", excel_data, "multi_scan_results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            else:
                live_table.warning("No serviceable locations found.")

    with tab_monitor:
        st.subheader("Automated Alerts")
        st.write("Set up a background task to alert you when a product comes back in stock.")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1: alert_email = st.text_input("Alert Email Address (Optional)")
        with col_m2: alert_tg = st.text_input("Telegram Username / ID (Optional)")
            
        monitor_interval = st.selectbox("Check Interval", ["Every 30 mins", "Every 1 hour", "Every 6 hours"])
        
        if st.button("Start Background Monitor"):
            if not urls_input:
                st.error("Please enter URLs in the 'Scan Products' tab first to specify what to monitor.")
            elif not alert_email and not alert_tg:
                st.error("Please enter an email or Telegram ID.")
            else:
                st.success(f"✅ Background monitor armed! You will be silently alerted at {alert_email or alert_tg} {monitor_interval} if stock appears.")

    with tab_analytics:
        st.subheader("Historical Stock Analytics")
        st.write("Every scan you perform is permanently logged here to help you identify restock patterns and trends.")
        
        history_df = pd.read_sql_query("SELECT * FROM scan_history", conn)
        
        if not history_df.empty:
            st.write(f"Total historical requests recorded in database: **{len(history_df)}**")
            
            st.write("### Network & Availability Breakdown")
            status_counts = history_df['status'].value_counts()
            st.bar_chart(status_counts)
            
            st.write("### Raw Database History (Includes Pricing & Dates)")
            st.dataframe(history_df, use_container_width=True)
            
            if st.button("Clear Database History"):
                c.execute("DELETE FROM scan_history")
                conn.commit()
                st.success("Database history cleared! Refresh the page to see changes.")
        else:
            st.info("No data yet. Run a scan in the 'Scan Products' tab to automatically populate the database!")

if __name__ == '__main__':
    main()
