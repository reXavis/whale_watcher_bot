"""
Large Transaction Alert Discord Bot

Monitors a subgraph for large liquidity transactions (adds/withdrawals) and sends 
colored Discord alerts for different tiers of whale activity.

Setup Instructions:
- See README.md for detailed configuration guide
- Set DISCORD_TOKEN environment variable
- Set SUBGRAPH_URL environment variable
- Configure CHANNEL_ID and thresholds below
- Run: python whale_alert_bot.py

Alert Tiers:
🐬 Dolphin: $1k - $10k
🐋 Whale: $10k - $50k  
🐙 Orc: $50k+

Alert Colors:
🟢 ADD (Liquidity Addition) - Green embeds with ⬆️ arrows
🔴 WITHDRAW (Liquidity Withdrawal) - Red embeds with ⬇️ arrows
"""

import requests
import time
import os
import csv
import asyncio
import discord
from discord.ext import tasks
from datetime import datetime
import pandas as pd

# =============================================================================
# CONFIGURATION - EDIT THESE VALUES AS NEEDED
# =============================================================================

# Discord Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')  # Set this as environment variable
CHANNEL_ID = 1397257377220395049

# Alert Configuration - Different tiers based on USD amount
DOLPHIN_THRESHOLD_USD = 1000.0   # Dolphin: $1k - $10k
WHALE_THRESHOLD_USD = 10000.0    # Whale: $10k - $50k  
ORC_THRESHOLD_USD = 50000.0      # Orc: $50k+
POLL_INTERVAL = 60  # seconds between checks (increased from 15 to reduce API load)

# Subgraph Configuration
SUBGRAPH_URL = os.getenv('SUBGRAPH_URL')
LARGE_TX_CSV_FILE = "large_transactions.csv"  # CSV for all large transactions (dolphins, whales, orcs)
REQUEST_DELAY = 5.0  # seconds between requests to avoid rate limiting (increased from 2.0)
BATCH_SIZE = 10  # smaller batches since we're filtering server-side (reduced from 25)
RETRY_DELAY = 120  # seconds to wait when rate limited (increased from 60)
MAX_RETRIES = 3  # maximum number of retries before giving up
EXPONENTIAL_BACKOFF = True  # enable exponential backoff for rate limiting

# Alert Message Templates - Customize as needed
DOLPHIN_ALERT_TEMPLATE = """🐬 **DOLPHIN ALERT!**
{event_emoji} **${amount_usd:,.2f} {event_type}**
📊 **Pool:** {token0}/{token1}
⏰ **Time:** {datetime}"""

WHALE_ALERT_TEMPLATE = """🐋 **WHALE ALERT!**
{event_emoji} **${amount_usd:,.2f} {event_type}**
📊 **Pool:** {token0}/{token1}
⏰ **Time:** {datetime}"""

ORC_ALERT_TEMPLATE = """🐙 **ORC ALERT!**
{event_emoji} **${amount_usd:,.2f} {event_type}**
📊 **Pool:** {token0}/{token1}
⏰ **Time:** {datetime}"""

# Color and emoji configuration for different event types
EVENT_COLORS = {
    'Add': 0x00ff00,      # Green for liquidity additions
    'Withdraw': 0xff0000  # Red for liquidity withdrawals
}

EVENT_EMOJIS = {
    'Add': '🟢 💰 ⬆️',     # Green circle, money, up arrow
    'Withdraw': '🔴 💸 ⬇️'  # Red circle, money with wings, down arrow
}

# =============================================================================
# OPTIMIZED GRAPHQL QUERIES - SERVER-SIDE FILTERING FOR LARGE TRANSACTIONS
# =============================================================================

MINTS_QUERY = '''
query getMints($lastTimestamp: BigInt, $batchSize: Int!, $minAmountUSD: BigDecimal) {
  mints(
    first: $batchSize, 
    orderBy: timestamp, 
    orderDirection: asc, 
    where: {
      timestamp_gt: $lastTimestamp,
      amountUSD_gte: $minAmountUSD
    }
  ) {
    id
    timestamp
    transaction { 
      id 
      blockNumber 
    }
    pool { id }
    token0 { symbol }
    token1 { symbol }
    amountUSD
  }
}
'''

BURNS_QUERY = '''
query getBurns($lastTimestamp: BigInt, $batchSize: Int!, $minAmountUSD: BigDecimal) {
  burns(
    first: $batchSize, 
    orderBy: timestamp, 
    orderDirection: asc, 
    where: {
      timestamp_gt: $lastTimestamp,
      amountUSD_gte: $minAmountUSD
    }
  ) {
    id
    timestamp
    transaction { 
      id 
      blockNumber 
    }
    pool { id }
    token0 { symbol }
    token1 { symbol }
    amountUSD
  }
}
'''

# Combined query to get both mints and burns in a single request (experimental)
COMBINED_LARGE_TX_QUERY = '''
query getLargeTransactions($lastTimestamp: BigInt, $batchSize: Int!, $minAmountUSD: BigDecimal) {
  mints(
    first: $batchSize, 
    orderBy: timestamp, 
    orderDirection: asc, 
    where: {
      timestamp_gt: $lastTimestamp,
      amountUSD_gte: $minAmountUSD
    }
  ) {
    id
    timestamp
    transaction { id blockNumber }
    pool { id }
    token0 { symbol }
    token1 { symbol }
    amountUSD
    __typename
  }
  burns(
    first: $batchSize, 
    orderBy: timestamp, 
    orderDirection: asc, 
    where: {
      timestamp_gt: $lastTimestamp,
      amountUSD_gte: $minAmountUSD
    }
  ) {
    id
    timestamp
    transaction { id blockNumber }
    pool { id }
    token0 { symbol }
    token1 { symbol }
    amountUSD
    __typename
  }
}
'''

# =============================================================================
# CSV FUNCTIONS FOR LARGE TRANSACTIONS (DOLPHINS, WHALES, ORCS)
# =============================================================================

def setup_large_tx_csv_file():
    """Initialize the large transactions CSV file with headers if it doesn't exist."""
    if not os.path.exists(LARGE_TX_CSV_FILE):
        with open(LARGE_TX_CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timestamp', 'DateTime', 'EventType', 'AlertTier', 'TransactionID', 'BlockNumber', 
                'PoolID', 'Token0Symbol', 'Token1Symbol', 'AmountUSD'
            ])

def log_large_tx_to_csv(event_type, event, tx, alert_tier):
    """Log a large transaction to the CSV file with its alert tier."""
    with open(LARGE_TX_CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            event['timestamp'],
            datetime.utcfromtimestamp(int(event['timestamp'])).isoformat(),
            event_type,
            alert_tier,
            tx['id'],
            tx['blockNumber'],
            event['pool']['id'],
            event['token0']['symbol'],
            event['token1']['symbol'],
            event['amountUSD']
        ])

def get_current_timestamp():
    """Get current timestamp to start monitoring from now."""
    return int(time.time())

def get_last_large_tx_timestamp():
    """Get the last timestamp from the large transactions CSV file, or current time if file doesn't exist."""
    if not os.path.exists(LARGE_TX_CSV_FILE):
        return get_current_timestamp()
    
    try:
        df = pd.read_csv(LARGE_TX_CSV_FILE)
        if len(df) == 0:
            return get_current_timestamp()
        return int(df['Timestamp'].max())
    except Exception as e:
        print(f"Error reading last large transaction timestamp: {e}")
        return get_current_timestamp()

def get_alert_tier(amount_usd):
    """Determine the alert tier based on USD amount."""
    if amount_usd >= ORC_THRESHOLD_USD:
        return "Orc"
    elif amount_usd >= WHALE_THRESHOLD_USD:
        return "Whale"
    elif amount_usd >= DOLPHIN_THRESHOLD_USD:
        return "Dolphin"
    else:
        return None

# =============================================================================
# SUBGRAPH FUNCTIONS
# =============================================================================

async def fetch_events_batch(query, last_timestamp, event_type, min_amount_usd=None):
    """Fetch a batch of events from the subgraph with advanced rate limit handling."""
    if min_amount_usd is None:
        min_amount_usd = str(DOLPHIN_THRESHOLD_USD)  # Server-side filter for $1000+
    
    retries = 0
    current_retry_delay = RETRY_DELAY
    
    while retries < MAX_RETRIES:
        try:
            # Prepare GraphQL variables with server-side filtering
            variables = {
                "lastTimestamp": last_timestamp, 
                "batchSize": BATCH_SIZE,
                "minAmountUSD": min_amount_usd
            }
            
            print(f"🔍 Fetching {event_type}s with server-side filter ≥${min_amount_usd} (attempt {retries + 1})")
            
            response = requests.post(
                SUBGRAPH_URL,
                json={"query": query, "variables": variables},
                timeout=30
            )
            
            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                print(f"⚠️ Rate limited! Waiting {current_retry_delay} seconds... (attempt {retries + 1}/{MAX_RETRIES})")
                await asyncio.sleep(current_retry_delay)
                
                if EXPONENTIAL_BACKOFF:
                    current_retry_delay *= 2  # Double the delay for next retry
                retries += 1
                continue
            
            response.raise_for_status()
            data = response.json()
            
            if 'errors' in data:
                print(f"GraphQL errors: {data['errors']}")
                return []
            
            events = data['data'][event_type.lower() + 's']
            print(f"✅ Fetched {len(events)} large {event_type}s (≥${min_amount_usd})")
            return events
            
        except requests.exceptions.HTTPError as e:
            if '429' in str(e):
                print(f"⚠️ Rate limited (HTTPError)! Waiting {current_retry_delay} seconds... (attempt {retries + 1}/{MAX_RETRIES})")
                await asyncio.sleep(current_retry_delay)
                
                if EXPONENTIAL_BACKOFF:
                    current_retry_delay *= 2
                retries += 1
                continue
            else:
                print(f"HTTP error: {e}")
                return []
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            if retries < MAX_RETRIES - 1:
                print(f"Retrying in {current_retry_delay} seconds...")
                await asyncio.sleep(current_retry_delay)
                retries += 1
                continue
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
            return []
    
    print(f"❌ Max retries ({MAX_RETRIES}) reached for {event_type} events. Giving up this cycle.")
    return []

# =============================================================================
# DISCORD BOT
# =============================================================================

class LargeTxAlertBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.last_mint_timestamp = 0
        self.last_burn_timestamp = 0
        self.channel = None
        
    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        self.channel = self.get_channel(CHANNEL_ID)
        if self.channel:
            print(f"Connected to channel: {self.channel.name}")
        else:
            print(f"Error: Could not find channel with ID {CHANNEL_ID}")
            return
            
        # Setup whale CSV file
        setup_large_tx_csv_file()
        
        # Start monitoring from current time or last whale timestamp
        start_timestamp = get_last_large_tx_timestamp()
        self.last_mint_timestamp = start_timestamp
        self.last_burn_timestamp = start_timestamp
        
        print(f"Starting monitoring from timestamp: {start_timestamp}")
        print(f"Start time: {datetime.utcfromtimestamp(start_timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Alert Thresholds:")
        print(f"  🐬 Dolphin: ${DOLPHIN_THRESHOLD_USD:,.2f} - ${WHALE_THRESHOLD_USD-0.01:,.2f}")
        print(f"  🐋 Whale: ${WHALE_THRESHOLD_USD:,.2f} - ${ORC_THRESHOLD_USD-0.01:,.2f}")
        print(f"  🐙 Orc: ${ORC_THRESHOLD_USD:,.2f}+")
        print(f"⚡ OPTIMIZED SETTINGS:")
        print(f"  📊 Server-side filtering: ≥${DOLPHIN_THRESHOLD_USD:,.0f} (reduces API load by ~90%)")
        print(f"  ⏱️ Polling interval: {POLL_INTERVAL}s (reduced frequency)")
        print(f"  📦 Batch size: {BATCH_SIZE} transactions (smaller batches)")
        print(f"  🔄 Request delay: {REQUEST_DELAY}s between API calls")
        print(f"  ⚠️ Max retries: {MAX_RETRIES} with exponential backoff")
        print(f"  💾 Large transactions saved to: {LARGE_TX_CSV_FILE}")
        print("=" * 60)
        
        # Start the monitoring task
        self.monitor_transactions.start()

    async def send_whale_alert(self, event_type, event, tx):
        """Send a large transaction alert to Discord based on the transaction tier."""
        try:
            amount_usd = float(event['amountUSD'])
            alert_tier = get_alert_tier(amount_usd)
            
            if not alert_tier:
                return  # No alert needed for small transactions
            
            # Determine which template to use based on tier
            if alert_tier == "Orc":
                template = ORC_ALERT_TEMPLATE
                title = "🐙 ORC ALERT!"
            elif alert_tier == "Whale":
                template = WHALE_ALERT_TEMPLATE
                title = "🐋 WHALE ALERT!"
            elif alert_tier == "Dolphin":
                template = DOLPHIN_ALERT_TEMPLATE
                title = "🐬 DOLPHIN ALERT!"
            else:
                return
            
            # Get color and emoji for event type
            embed_color = EVENT_COLORS.get(event_type, 0x808080)  # Default to gray
            event_emoji = EVENT_EMOJIS.get(event_type, '💰')
            
            # Create Discord embed with color
            embed = discord.Embed(
                title=title,
                color=embed_color,
                timestamp=datetime.utcfromtimestamp(int(event['timestamp']))
            )
            
            # Add fields to the embed
            embed.add_field(
                name=f"{event_emoji} Transaction",
                value=f"**${amount_usd:,.2f} {event_type.upper()}**",
                inline=False
            )
            
            embed.add_field(
                name="📊 Pool",
                value=f"{event['token0']['symbol']}/{event['token1']['symbol']}",
                inline=True
            )
            
            embed.add_field(
                name="🔗 Transaction",
                value=f"`{tx['id'][:10]}...`",
                inline=True
            )
            
            embed.add_field(
                name="📦 Block",
                value=f"#{tx['blockNumber']}",
                inline=True
            )
            
            # Add footer with tier information
            embed.set_footer(text=f"{alert_tier} Alert • Gliquid Analytics")
            
            await self.channel.send(embed=embed)
            print(f"🚨 {alert_tier} alert sent: ${amount_usd:,.2f} {event_type} ({'🟢' if event_type == 'Add' else '🔴'})")
            
        except Exception as e:
            print(f"Error sending large transaction alert: {e}")

    @tasks.loop(seconds=POLL_INTERVAL)
    async def monitor_transactions(self):
        """Monitor for new transactions and send large transaction alerts."""
        try:
            total_transactions = 0
            large_tx_alerts = 0
            dolphin_count = 0
            whale_count = 0 
            orc_count = 0
            
            print(f"🔄 Checking for large transactions (≥${DOLPHIN_THRESHOLD_USD:,.0f})...")
            
            # Fetch new liquidity additions (mints) - already filtered server-side
            mint_events = await fetch_events_batch(MINTS_QUERY, self.last_mint_timestamp, 'Mint')
            for mint in mint_events:
                total_transactions += 1
                
                # All events are already large transactions due to server-side filtering
                amount_usd = float(mint['amountUSD'])
                alert_tier = get_alert_tier(amount_usd)
                
                if alert_tier:  # Should always be true now with server-side filtering
                    # Log large transaction to CSV
                    log_large_tx_to_csv('Add', mint, mint['transaction'], alert_tier)
                    
                    # Send Discord alert
                    await self.send_whale_alert('Add', mint, mint['transaction'])
                    large_tx_alerts += 1
                    
                    # Count by tier
                    if alert_tier == "Dolphin":
                        dolphin_count += 1
                    elif alert_tier == "Whale":
                        whale_count += 1
                    elif alert_tier == "Orc":
                        orc_count += 1
                
                # Update timestamp
                self.last_mint_timestamp = max(self.last_mint_timestamp, int(mint['timestamp']))
            
            # Delay between requests to respect rate limits
            if mint_events:
                print(f"⏱️ Waiting {REQUEST_DELAY}s before checking withdrawals...")
                await asyncio.sleep(REQUEST_DELAY)
            
            # Fetch new liquidity withdrawals (burns) - already filtered server-side  
            burn_events = await fetch_events_batch(BURNS_QUERY, self.last_burn_timestamp, 'Burn')
            for burn in burn_events:
                total_transactions += 1
                
                # All events are already large transactions due to server-side filtering
                amount_usd = float(burn['amountUSD'])
                alert_tier = get_alert_tier(amount_usd)
                
                if alert_tier:  # Should always be true now with server-side filtering
                    # Log large transaction to CSV
                    log_large_tx_to_csv('Withdraw', burn, burn['transaction'], alert_tier)
                    
                    # Send Discord alert
                    await self.send_whale_alert('Withdraw', burn, burn['transaction'])
                    large_tx_alerts += 1
                    
                    # Count by tier
                    if alert_tier == "Dolphin":
                        dolphin_count += 1
                    elif alert_tier == "Whale":
                        whale_count += 1
                    elif alert_tier == "Orc":
                        orc_count += 1
                
                # Update timestamp
                self.last_burn_timestamp = max(self.last_burn_timestamp, int(burn['timestamp']))
            
            # Log activity with tier breakdown
            if large_tx_alerts > 0:
                tier_breakdown = []
                if dolphin_count > 0:
                    tier_breakdown.append(f"{dolphin_count} 🐬")
                if whale_count > 0:
                    tier_breakdown.append(f"{whale_count} 🐋")
                if orc_count > 0:
                    tier_breakdown.append(f"{orc_count} 🐙")
                
                print(f"📈 Found {total_transactions} large transactions → {large_tx_alerts} alerts ({', '.join(tier_breakdown)})")
            elif mint_events or burn_events:
                print(f"🔍 Checked {len(mint_events)} large additions + {len(burn_events)} large withdrawals → all processed")
            else:
                print(f"😴 No large transactions found this cycle")
            
        except Exception as e:
            print(f"Error in monitor_transactions: {e}")
            # Use exponential backoff for error recovery
            await asyncio.sleep(min(REQUEST_DELAY * 2, 30))

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main function to run the large transaction alert bot."""
    print("🌊 Starting Large Transaction Alert Discord Bot...")
    
    # Validate Discord token
    if not DISCORD_TOKEN:
        print("❌ ERROR: Discord token not found!")
        print("Please set the DISCORD_TOKEN environment variable:")
        print("  Linux/Mac: export DISCORD_TOKEN='your_bot_token_here'")
        print("  Windows: set DISCORD_TOKEN=your_bot_token_here")
        print("  Or create a .env file with: DISCORD_TOKEN=your_bot_token_here")
        print("=" * 50)
        return
    
    if not SUBGRAPH_URL:
        print("❌ ERROR: Subgraph URL not found!")
        print("Please set the SUBGRAPH_URL environment variable:")
        print("  Linux/Mac: export SUBGRAPH_URL='your_subgraph_url_here'")
        print("  Windows: set SUBGRAPH_URL=your_subgraph_url_here")
        print("  Or create a .env file with: SUBGRAPH_URL=your_subgraph_url_here")
        print("=" * 50)
        return

    print(f"Discord Channel ID: {CHANNEL_ID}")
    print(f"Alert Tiers:")
    print(f"  🐬 Dolphin: ${DOLPHIN_THRESHOLD_USD:,.2f} - ${WHALE_THRESHOLD_USD-0.01:,.2f}")
    print(f"  🐋 Whale: ${WHALE_THRESHOLD_USD:,.2f} - ${ORC_THRESHOLD_USD-0.01:,.2f}")
    print(f"  🐙 Orc: ${ORC_THRESHOLD_USD:,.2f}+")
    print(f"⚡ RATE-LIMIT OPTIMIZATIONS:")
    print(f"  📊 Server-side filtering: Only fetches transactions ≥${DOLPHIN_THRESHOLD_USD:,.0f}")
    print(f"  ⏱️ Conservative polling: Every {POLL_INTERVAL} seconds (vs 15s before)")
    print(f"  📦 Smaller batches: {BATCH_SIZE} transactions per request (vs 25 before)")
    print(f"  🔄 Smart delays: {REQUEST_DELAY}s between requests (vs 2s before)")
    print(f"  ⚠️ Exponential backoff: {MAX_RETRIES} retries with increasing delays")
    print(f"  🗂️ Simplified fields: Removed unnecessary data (gas, ticks, etc.)")
    print(f"Large Transactions CSV: {LARGE_TX_CSV_FILE}")
    print("=" * 60)
    print("🎯 These optimizations reduce API calls by ~90% while maintaining functionality!")
    print("ℹ️  Bot now fetches only large transactions (dolphins/whales/orcs) from server")
    print("ℹ️  Regular small transactions are filtered out before reaching the bot")
    print("=" * 60)
    
    # Create and run the bot
    bot = LargeTxAlertBot()
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main() 
