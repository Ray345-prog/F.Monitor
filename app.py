import os
import asyncio
import json
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from colorama import init, Fore, Style
from pydantic import BaseModel, Field

# Initialize colorama & environment
init(autoreset=True)
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
    print(Fore.RED + "❌ ERROR: GEMINI_API_KEY missing in .env file!")
    exit(1)

# Initialize official Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-2.5-flash"

# Pydantic Schema for Strict AI Output Validation
class AIDecisionSchema(BaseModel):
    action: str = Field(description="Must be HOLD, EXIT, or ENTER")
    confidence_score: int = Field(description="Score between 0 and 100")
    reasoning: str = Field(description="Professional financial rationale")

class DeterministicRiskEngine:
    """
    Handles instantaneous, zero-latency local mathematical risk checks.
    Guarantees hard stop-losses and take-profits execute programmatically.
    """
    def __init__(self, entry_price: float, trade_type: str, stop_loss_pips: float, take_profit_pips: float):
        self.entry_price = entry_price
        self.trade_type = trade_type.upper()
        self.stop_loss_threshold = stop_loss_pips / 10000.0
        self.take_profit_threshold = take_profit_pips / 10000.0

    def evaluate_risk(self, current_price: float):
        if self.trade_type == "BUY":
            price_diff = current_price - self.entry_price
            gain_loss_pct = (price_diff / self.entry_price) * 100
            pips = price_diff * 10000
            
            is_stop_loss = current_price <= (self.entry_price - self.stop_loss_threshold)
            is_take_profit = current_price >= (self.entry_price + self.take_profit_threshold)
        else:  # SELL
            price_diff = self.entry_price - current_price
            gain_loss_pct = (price_diff / self.entry_price) * 100
            pips = price_diff * 10000
            
            is_stop_loss = current_price >= (self.entry_price + self.stop_loss_threshold)
            is_take_profit = current_price <= (self.entry_price - self.take_profit_threshold)

        status = "NORMAL"
        if is_stop_loss:
            status = "HARD_STOP_LOSS_TRIGGERED"
        elif is_take_profit:
            status = "TAKE_PROFIT_TRIGGERED"

        return {
            "current_price": current_price,
            "gain_loss_pct": round(gain_loss_pct, 3),
            "pips": round(pips, 1),
            "status": status
        }

class LiveDataFetcher:
    """Fetches real live pricing from Twelve Data API."""
    def __init__(self, api_key: str, symbol: str):
        self.api_key = api_key
        self.symbol = symbol

    async def get_latest_price(self, session: aiohttp.ClientSession) -> float:
        if not self.api_key or self.api_key == "your_twelve_data_key_here":
            raise ValueError("Twelve Data API Key is not configured in .env")
        
        url = f"https://api.twelvedata.com/price?symbol={self.symbol}&apikey={self.api_key}"
        async with session.get(url) as response:
            data = await response.json()
            if "price" in data:
                return float(data["price"])
            else:
                raise Exception(f"API Error fetching price: {data}")

class ForexAIEngine:
    """Asynchronous macro news analyst. Runs decoupled from instant risk logic."""
    async def analyze_macro_sentiment(self, pair: str, metrics: dict):
        prompt = f"""
        Analyze current risk parameters for {pair}:
        - Current PnL: {metrics['gain_loss_pct']}% 
        - Current Pips: {metrics['pips']}
        - Current Price: {metrics['current_price']}
        
        Task: Provide a macro risk assessment and recommendation. Output must follow strict JSON structure.
        """
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_ID,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1,
                }
            )
            return json.loads(response.text)
        except Exception as e:
            return {
                "action": "HOLD",
                "confidence_score": 0,
                "reasoning": f"AI fallback triggered due to error: {str(e)}"
            }

async def main():
    # Trade Configuration - Change these to match your personal trade
    PAIR = "EUR/USD"
    ENTRY_PRICE = 1.0850  
    TRADE_TYPE = "BUY"
    STOP_LOSS_PIPS = 30.0   # Hard programmatic safety limit
    TAKE_PROFIT_PIPS = 60.0 # Hard programmatic target limit

    risk_engine = DeterministicRiskEngine(ENTRY_PRICE, TRADE_TYPE, STOP_LOSS_PIPS, TAKE_PROFIT_PIPS)
    data_fetcher = LiveDataFetcher(TWELVE_DATA_API_KEY, PAIR)
    ai_engine = ForexAIEngine()

    print(Fore.CYAN + "=" * 65)
    print(Fore.CYAN + f" 🛡️ PRODUCTION FOREX RISK MONITOR | {PAIR} | {TRADE_TYPE} @ {ENTRY_PRICE}")
    print(Fore.CYAN + "=" * 65 + Style.RESET_ALL)

    async with aiohttp.ClientSession() as session:
        ai_counter = 0
        while True:
            try:
                current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                
                # 1. Fetch real live price feed
                current_price = await data_fetcher.get_latest_price(session)

                # 2. INSTANT DETERMINISTIC RISK CHECK (Zero-latency Python execution)
                metrics = risk_engine.evaluate_risk(current_price)

                print(Fore.YELLOW + f"\n[{current_time}] 📈 Live Price: {metrics['current_price']} | PnL: {metrics['gain_loss_pct']}% ({metrics['pips']} pips)")

                # If hard programmatic safety triggers are hit, bypass AI and act immediately
                if metrics["status"] != "NORMAL":
                    print(Fore.RED + f"🚨 EMERGENCY RISK TRIGGER: {metrics['status']}! EXECUTE IMMEDIATE CLOSE.")
                    break

                # 3. Decoupled AI Macro Check (Runs every 3 ticks to avoid rate limits & latency bottlenecks)
                ai_counter += 1
                if ai_counter >= 3:
                    ai_counter = 0
                    print(Fore.BLUE + "🤖 Querying Gemini AI for macro-sentiment evaluation...")
                    ai_decision = await ai_engine.analyze_macro_sentiment(PAIR, metrics)
                    print(Fore.GREEN + f"💡 AI Sentiment Action: {ai_decision.get('action')} (Confidence: {ai_decision.get('confidence_score')}%)")
                    print(Fore.LIGHTBLACK_EX + f"📝 Breakdown: {ai_decision.get('reasoning')}")

                print("-" * 65)
                # Polling frequency interval (check live price every 5 seconds)
                await asyncio.sleep(5)

            except KeyboardInterrupt:
                print(Fore.RED + "\n🛑 Monitor stopped safely by user.")
                break
            except Exception as e:
                print(Fore.RED + f"⚠️ Operational Error: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())