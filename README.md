# 🌊 Large Transaction Alert Discord Bot

A Discord bot that monitors blockchain liquidity transactions from subgraphs and sends real-time **colored alerts** for large transactions across different tiers.

## ✨ Features

- **Multi-tier Alerts**: Categorizes transactions into Dolphin, Whale, and Orc tiers
- **Colored Visual Alerts**: Green embeds for ADDs, red embeds for WITHDRAWs
- **Server-side Filtering**: Only fetches large transactions (≥$1000) from subgraph
- **Rate-limit Optimized**: Reduces API calls by ~90% vs naive approaches
- **Real-time Monitoring**: Conservative polling every 60 seconds for sustainability
- **Discord Integration**: Sends clean, formatted alerts to Discord channels
- **CSV Logging**: Saves all large transactions with essential metadata
- **Advanced Error Handling**: Exponential backoff and smart retry logic
- **Configurable Thresholds**: Easy to adjust alert tiers and settings

## ⚡ Rate-Limit Optimizations

This bot is specifically designed to work within subgraph API limits:

- **🎯 Server-side Filtering**: GraphQL queries include `amountUSD_gte: $1000` to filter small transactions at the API level
- **⏱️ Conservative Polling**: 60-second intervals (vs aggressive 15s) to reduce request frequency  
- **📦 Smaller Batches**: 10 transactions per request (vs 25) since we're pre-filtering
- **🔄 Smart Delays**: 5-second delays between mint/burn requests
- **⚠️ Exponential Backoff**: Intelligent retry logic with increasing delays
- **🗂️ Minimal Fields**: Only fetches essential data (removed gas, ticks, etc.)
- **📊 Combined Efficiency**: Reduces total API load by approximately 90%

## 🐋 Alert Tiers

- 🐬 **Dolphin**: $1,000 - $9,999
- 🐋 **Whale**: $10,000 - $49,999  
- 🐙 **Orc**: $50,000+

## 🎨 Alert Colors

- 🟢 **ADD (Liquidity Addition)**: Green Discord embeds with ⬆️ arrows
- 🔴 **WITHDRAW (Liquidity Withdrawal)**: Red Discord embeds with ⬇️ arrows

Visual indicators help you instantly recognize whether liquidity is being added to or removed from pools!

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables
```bash
# Linux/Mac
export DISCORD_TOKEN='your_bot_token_here'
export SUBGRAPH_URL='your_subgraph_endpoint_here'

# Windows
set DISCORD_TOKEN=your_bot_token_here
set SUBGRAPH_URL=your_subgraph_endpoint_here
```

### 3. Configure Settings
Edit the configuration section in `whale_alert_bot.py`:
- `CHANNEL_ID`: Your Discord channel ID
- Adjust thresholds and polling intervals as needed

### 4. Run the Bot
```bash
python whale_alert_bot.py
```

## 📋 Prerequisites

### Discord Bot Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Navigate to "Bot" section
4. Copy the bot token
5. Invite bot to your server with "Send Messages" permission

### Channel ID
1. Enable Developer Mode in Discord settings
2. Right-click your target channel → "Copy Channel ID"

## ⚙️ Configuration

### Environment Variables

**Required:**
- `DISCORD_TOKEN`: Your Discord bot token
- `SUBGRAPH_URL`: The subgraph endpoint URL to monitor

**Optional (.env file):**
```bash
# Discord Bot Token (required)
DISCORD_TOKEN=your_discord_bot_token_here

# Subgraph URL (required)
SUBGRAPH_URL=https://api.goldsky.com/api/public/your_subgraph_endpoint
```

### Bot Settings

Edit these values in `whale_alert_bot.py`:

```python
# Discord Configuration
CHANNEL_ID = 1234567890123456789  # Your Discord channel ID

# Alert Thresholds
DOLPHIN_THRESHOLD_USD = 1000.0   # Minimum for dolphin alerts
WHALE_THRESHOLD_USD = 10000.0    # Minimum for whale alerts  
ORC_THRESHOLD_USD = 50000.0      # Minimum for orc alerts

# Polling Settings
POLL_INTERVAL = 60               # Seconds between checks (optimized)
REQUEST_DELAY = 5.0              # Delay between API calls (optimized)
BATCH_SIZE = 10                  # Transactions per request (optimized)
```

## �� Sample Alerts

### 🟢 Liquidity Addition (Green Embed)
```
🐋 WHALE ALERT!
🟢 💰 ⬆️ Transaction
$25,340.50 ADD

📊 Pool: ETH/USDC
🔗 Transaction: 0x1a2b3c4d5e...
📦 Block: #18945623
⏰ Timestamp: 2025-07-22 19:30:45 UTC
```

### 🔴 Liquidity Withdrawal (Red Embed)
```
🐙 ORC ALERT!
🔴 💸 ⬇️ Transaction
$87,250.00 WITHDRAW

📊 Pool: WBTC/ETH
🔗 Transaction: 0x9f8e7d6c5b...
📦 Block: #18945681
⏰ Timestamp: 2025-07-22 19:35:12 UTC
```

The colored embeds make it easy to distinguish between liquidity being added (🟢 green) vs. removed (🔴 red) from pools at a glance!

## 📁 Output Files

- **`large_transactions.csv`**: Contains all large transactions with metadata
  - Includes AlertTier, Transaction details, Pool info, USD amounts

## 🛠️ Advanced Configuration

### Subgraph URL
The bot monitors a specific subgraph endpoint. Set this via environment variable:
```bash
export SUBGRAPH_URL="https://api.goldsky.com/api/public/your_subgraph_endpoint"
```

### Rate Limiting
The bot is now heavily optimized for API efficiency. Adjust these settings only if needed:

```python
# Optimized settings (current defaults)
POLL_INTERVAL = 60             # Seconds between checks (increased from 15)
REQUEST_DELAY = 5.0            # Delay between API calls (increased from 2.0)  
BATCH_SIZE = 10                # Transactions per request (reduced from 25)
RETRY_DELAY = 120              # Initial retry delay (increased from 60)
MAX_RETRIES = 3                # Maximum retry attempts (new)
EXPONENTIAL_BACKOFF = True     # Enable exponential backoff (new)
```

**Server-side Filtering**: The bot now includes `amountUSD_gte: "1000"` in GraphQL queries, so only large transactions are fetched. This dramatically reduces API load compared to client-side filtering.

## 🚦 Error Handling

The bot includes robust error handling for:
- Missing environment variables (Discord token, subgraph URL)
- Discord connection issues
- Subgraph API rate limits  
- Network timeouts
- Invalid configuration

## 📝 Logs

Console output shows:
- Connection status
- Alert summaries: `"📈 Scanned 50 transactions → 3 alerts (1 🐬, 2 🐋)"`  
- Individual alerts with color indicators: `"🚨 Whale alert sent: $25,340.50 Add 🟢"`
- Rate limiting notifications
- Error messages

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## ⚠️ Disclaimer
