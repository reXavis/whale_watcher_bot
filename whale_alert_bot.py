"""
Large Transaction Alert Discord Bot

Monitors a subgraph for large liquidity transactions (adds/withdrawals) and sends 
Discord alerts for different tiers of whale activity.

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
POLL_INTERVAL = 15  # seconds between checks (increased to avoid rate limits)

# Subgraph Configuration
SUBGRAPH_URL = os.getenv('SUBGRAPH_URL')
LARGE_TX_CSV_FILE = "large_transactions.csv"  # CSV for all large transactions (dolphins, whales, orcs)
REQUEST_DELAY = 2.0  # seconds between requests to avoid rate limiting (increased)
BATCH_SIZE = 25  # smaller batches for frequent polling (reduced)
RETRY_DELAY = 60  # seconds to wait when rate limited

# Alert Message Templates - Customize as needed
DOLPHIN_ALERT_TEMPLATE = """🐬 **DOLPHIN ALERT!**
💰 **${amount_usd:,.2f} {event_type}**
📊 **Pool:** {token0}/{token1}
⏰ **Time:** {datetime}"""

WHALE_ALERT_TEMPLATE = """🐋 **WHALE ALERT!**
💰 **${amount_usd:,.2f} {event_type}**
📊 **Pool:** {token0}/{token1}
⏰ **Time:** {datetime}"""

ORC_ALERT_TEMPLATE = """🐙 **ORC ALERT!**
💰 **${amount_usd:,.2f} {event_type}**
📊 **Pool:** {token0}/{token1}
⏰ **Time:** {datetime}"""

# =============================================================================
# GRAPHQL QUERIES
# =============================================================================

MINTS_QUERY = '''
query getMints($lastTimestamp: BigInt, $batchSize: Int!) {
  mints(first: $batchSize, orderBy: timestamp, orderDirection: asc, where: {timestamp_gt: $lastTimestamp}) {
    id
    transaction { id blockNumber timestamp gasLimit gasPrice }
    timestamp
    pool { id }
    token0 { symbol }
    token1 { symbol }
    owner
    sender
    origin
    amount
    amount0
    amount1
    amountUSD
    tickLower
    tickUpper
    logIndex
  }
}
'''

BURNS_QUERY = '''
query getBurns($lastTimestamp: BigInt, $batchSize: Int!) {
  burns(first: $batchSize, orderBy: timestamp, orderDirection: asc, where: {timestamp_gt: $lastTimestamp}) {
    id
    transaction { id blockNumber timestamp gasLimit gasPrice }
    timestamp
    pool { id }
    token0 { symbol }
    token1 { symbol }
    owner
    origin
    amount
    amount0
    amount1
    amountUSD
    tickLower
    tickUpper
    logIndex
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
                'PoolID', 'Token0Symbol', 'Token1Symbol', 'Amount', 'Amount0', 'Amount1', 
                'AmountUSD', 'Owner', 'Sender', 'Origin', 'TickLower', 'TickUpper', 
                'LogIndex', 'GasLimit', 'GasPrice'
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
            event['amount'],
            event['amount0'],
            event['amount1'],
            event['amountUSD'],
            event.get('owner', ''),
            event.get('sender', ''),
            event.get('origin', ''),
            event['tickLower'],
            event['tickUpper'],
            event['logIndex'],
            tx.get('gasLimit', ''),
            tx.get('gasPrice', '')
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

async def fetch_events_batch(query, last_timestamp, event_type):
    """Fetch a batch of events from the subgraph with rate limit handling."""
    try:
        response = requests.post(
            SUBGRAPH_URL,
            json={"query": query, "variables": {"lastTimestamp": last_timestamp, "batchSize": BATCH_SIZE}},
            timeout=30
        )
        
        # Handle rate limiting
        if response.status_code == 429:
            print(f"⚠️ Rate limited! Waiting {RETRY_DELAY} seconds before retry...")
            await asyncio.sleep(RETRY_DELAY)  # Use async sleep
            return []  # Return empty to skip this cycle, will retry next cycle
        
        response.raise_for_status()
        data = response.json()
        
        if 'errors' in data:
            print(f"GraphQL errors: {data['errors']}")
            return []
            
        return data['data'][event_type.lower() + 's']
    except requests.exceptions.HTTPError as e:
        if '429' in str(e):
            print(f"⚠️ Rate limited (HTTPError)! Waiting {RETRY_DELAY} seconds...")
            await asyncio.sleep(RETRY_DELAY)  # Use async sleep
        else:
            print(f"HTTP error: {e}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
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
        print(f"Polling every {POLL_INTERVAL} seconds (rate-limit friendly)")
        print(f"Request delay: {REQUEST_DELAY}s between API calls")
        print(f"Batch size: {BATCH_SIZE} transactions per request")
        print(f"Large transactions will be saved to: {LARGE_TX_CSV_FILE}")
        
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
            elif alert_tier == "Whale":
                template = WHALE_ALERT_TEMPLATE
            elif alert_tier == "Dolphin":
                template = DOLPHIN_ALERT_TEMPLATE
            else:
                return
            
            # Format the alert message
            message = template.format(
                amount_usd=amount_usd,
                event_type=event_type.upper(),
                token0=event['token0']['symbol'],
                token1=event['token1']['symbol'],
                datetime=datetime.utcfromtimestamp(int(event['timestamp'])).strftime('%Y-%m-%d %H:%M:%S UTC')
            )
            
            await self.channel.send(message)
            print(f"🚨 {alert_tier} alert sent: ${amount_usd:,.2f} {event_type}")
            
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
            
            # Fetch new liquidity additions (mints)
            mint_events = await fetch_events_batch(MINTS_QUERY, self.last_mint_timestamp, 'Mint')
            for mint in mint_events:
                total_transactions += 1
                
                # Check if large transaction - only process dolphins/whales/orcs
                amount_usd = float(mint['amountUSD'])
                alert_tier = get_alert_tier(amount_usd)
                
                if alert_tier:
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
            
            # Delay between liquidity addition and withdrawal requests to respect rate limits
            if mint_events:
                print(f"🔍 Found {len(mint_events)} new liquidity additions, waiting {REQUEST_DELAY}s before checking withdrawals...")
                await asyncio.sleep(REQUEST_DELAY)
            
            # Fetch new liquidity withdrawals (burns)
            burn_events = await fetch_events_batch(BURNS_QUERY, self.last_burn_timestamp, 'Burn')
            for burn in burn_events:
                total_transactions += 1
                
                # Check if large transaction - only process dolphins/whales/orcs
                amount_usd = float(burn['amountUSD'])
                alert_tier = get_alert_tier(amount_usd)
                
                if alert_tier:
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
                
                print(f"📈 Scanned {total_transactions} transactions → {large_tx_alerts} alerts ({', '.join(tier_breakdown)})")
            elif mint_events or burn_events:
                print(f"🔍 Checked {len(mint_events)} additions + {len(burn_events)} withdrawals → no large transactions")
            
        except Exception as e:
            print(f"Error in monitor_transactions: {e}")
            # Wait a bit longer if there's an error
            await asyncio.sleep(5)

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
    print(f"Poll Interval: {POLL_INTERVAL} seconds (rate-limit friendly)")
    print(f"Request Delay: {REQUEST_DELAY}s between API calls")
    print(f"Large Transactions CSV: {LARGE_TX_CSV_FILE}")
    print("=" * 50)
    print("ℹ️  Bot will only save LARGE transactions (dolphins/whales/orcs) to CSV")
    print("ℹ️  Regular transactions are scanned but not saved")
    print("ℹ️  Conservative timing to avoid API rate limits")
    print("=" * 50)
    
    # Create and run the bot
    bot = LargeTxAlertBot()
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main() 
