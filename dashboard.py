import streamlit as st
import asyncio
import aiohttp
import plotly.graph_objects as go
from datetime import datetime, timezone
import pandas as pd
import time

# Import existing core logic from your app.py
from app import LiveDataFetcher, DeterministicRiskEngine, ForexAIEngine, TWELVE_DATA_API_KEY, GEMINI_API_KEY

# ---------------------------------------------------------
# Streamlit Page Setup
# ---------------------------------------------------------
st.set_page_config(
    page_title="Forex Risk Engine Dashboard",
    page_icon="🛡️",
    layout="wide"
)

# Custom CSS for dark trading interface aesthetic
st.markdown("""
    <style>
    .metric-card {
        background-color: #1e222d;
        border: 1px solid #2a2e39;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
    }
    .stStatusWidget { font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("🛡️ Autonomous Forex Risk & Sentiment Dashboard")

# Initialize persistent session state for historical chart data
if "price_history" not in st.session_state:
    st.session_state.price_history = pd.DataFrame(columns=["Timestamp", "Price", "SL", "TP"])

# ---------------------------------------------------------
# Sidebar Controls & Parameters
# ---------------------------------------------------------
st.sidebar.header("⚙️ Execution Parameters")

symbol = st.sidebar.text_input("Currency Pair", value="EUR/USD")
trade_type = st.sidebar.selectbox("Position Type", ["BUY", "SELL"])
entry_price = st.sidebar.number_input("Entry Price", value=1.08500, format="%.5f", step=0.00010)

st.sidebar.subheader("🎯 Risk Thresholds")
stop_loss_pips = st.sidebar.number_input("Stop Loss (Pips)", value=30.0, step=1.0)
take_profit_pips = st.sidebar.number_input("Take Profit (Pips)", value=60.0, step=1.0)

st.sidebar.subheader("🔄 Auto-Refresh")
auto_refresh = st.sidebar.checkbox("Enable Real-time Stream", value=True)
refresh_interval = st.sidebar.slider("Refresh Interval (Seconds)", min_value=3, max_value=30, value=5)

# ---------------------------------------------------------
# Engine Execution Helper
# ---------------------------------------------------------
async def run_monitoring_cycle():
    risk_engine = DeterministicRiskEngine(
        entry_price=entry_price,
        trade_type=trade_type,
        stop_loss_pips=stop_loss_pips,
        take_profit_pips=take_profit_pips
    )
    fetcher = LiveDataFetcher(TWELVE_DATA_API_KEY, symbol)
    ai_engine = ForexAIEngine(GEMINI_API_KEY)
    
    async with aiohttp.ClientSession() as session:
        price = await fetcher.get_latest_price(session)
        risk_evaluation = risk_engine.evaluate_risk(price)
        
        # Async sentiment query to Gemini API
        sentiment = await ai_engine.analyze_market_sentiment(symbol, price)
        
        return price, risk_evaluation, sentiment, risk_engine

# Run single iteration
try:
    current_price, risk_data, ai_analysis, engine_inst = asyncio.run(run_monitoring_cycle())
    
    # Store history for real-time charting
    new_entry = {
        "Timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "Price": current_price,
        "SL": engine_inst.stop_loss_price,
        "TP": engine_inst.take_profit_price
    }
    st.session_state.price_history = pd.concat(
        [st.session_state.price_history, pd.DataFrame([new_entry])], 
        ignore_index=True
    ).tail(30) # Keep last 30 data points for performance
    
except Exception as e:
    st.error(f"Execution Error: {e}")
    st.stop()

# ---------------------------------------------------------
# Top Metrics Bar
# ---------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)

m1.metric("Live Price", f"{current_price:.5f}", delta=f"{risk_data['pips']:.1f} pips")
m2.metric("Unrealized PnL", f"{risk_data['gain_loss_pct']:.3f}%")
m3.metric("Stop Loss Level", f"{engine_inst.stop_loss_price:.5f}")
m4.metric("Take Profit Level", f"{engine_inst.take_profit_price:.5f}")

st.markdown("---")

# ---------------------------------------------------------
# Status Alerts & AI Macro Sentiment
# ---------------------------------------------------------
col_status, col_ai = st.columns([1, 1])

with col_status:
    st.subheader("🚨 Risk Engine Status")
    status = risk_data["status"]
    
    if status == "NORMAL":
        st.success("🟢 STATUS: MONITORING ACTIVE (Within Risk Tolerances)")
    elif status == "STOP_LOSS_TRIGGERED":
        st.error("🔴 EMERGENCY RISK TRIGGER: STOP-LOSS HIT! EXECUTE IMMEDIATE CLOSE.")
    elif status == "TAKE_PROFIT_TRIGGERED":
        st.info("🎯 TARGET REACHED: TAKE-PROFIT HIT! LOCK IN GAINS.")

with col_ai:
    st.subheader("🤖 Gemini AI Macro Sentiment")
    st.warning(f"**Macro Outlook**: {ai_analysis}")

# ---------------------------------------------------------
# Real-Time Auto-Refreshing Chart
# ---------------------------------------------------------
st.subheader("📈 Live Market Tracking & Threshold Overlay")

fig = go.Figure()

# Plot Live Price Line
fig.add_trace(go.Scatter(
    x=st.session_state.price_history["Timestamp"],
    y=st.session_state.price_history["Price"],
    mode="lines+markers",
    name="Market Price",
    line=dict(color="#00F0FF", width=3)
))

# Plot Stop Loss Level Line
fig.add_trace(go.Scatter(
    x=st.session_state.price_history["Timestamp"],
    y=st.session_state.price_history["SL"],
    mode="lines",
    name="Stop Loss",
    line=dict(color="#FF4B4B", width=2, dash="dash")
))

# Plot Take Profit Level Line
fig.add_trace(go.Scatter(
    x=st.session_state.price_history["Timestamp"],
    y=st.session_state.price_history["TP"],
    mode="lines",
    name="Take Profit",
    line=dict(color="#00CC66", width=2, dash="dash")
))

fig.update_layout(
    template="plotly_dark",
    height=400,
    margin=dict(l=20, r=20, t=30, b=20),
    xaxis_title="Time (UTC)",
    yaxis_title="Price",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# Auto-Refresh Logic Loop
# ---------------------------------------------------------
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()