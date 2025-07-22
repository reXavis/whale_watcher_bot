# 🌊 Large Transaction Alert Discord Bot

A Discord bot that monitors blockchain liquidity transactions from subgraphs and sends real-time alerts for large transactions across different tiers.

## ✨ Features

- **Multi-tier Alerts**: Categorizes transactions into Dolphin, Whale, and Orc tiers
- **Real-time Monitoring**: Polls subgraph every 15 seconds for new transactions  
- **Discord Integration**: Sends clean, formatted alerts to Discord channels
- **CSV Logging**: Saves all large transactions with detailed metadata
- **Rate Limit Protection**: Handles API rate limiting gracefully
- **Configurable Thresholds**: Easy to adjust alert tiers and settings

## 🐋 Alert Tiers

- 🐬 **Dolphin**: $1,000 - $9,999
- 🐋 **Whale**: $10,000 - $49,999  
- 🐙 **Orc**: $50,000+

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
POLL_INTERVAL = 15               # Seconds between checks
REQUEST_DELAY = 2.0              # Delay between API calls
```

## 📊 Sample Alert

```
🐋 WHALE ALERT!
💰 $25,340.50 MINT
📊 Pool: ETH/USDC  
⏰ Time: 2025-07-22 19:30:45 UTC
```

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
Adjust these settings if experiencing API issues by editing `whale_alert_bot.py`:
```python
REQUEST_DELAY = 2.0    # Seconds between requests
RETRY_DELAY = 60       # Seconds to wait when rate limited
BATCH_SIZE = 25        # Transactions per request
```

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
- Rate limiting notifications
- Error messages

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## ⚠️ Disclaimer

This bot is for informational purposes only. Always verify transaction data independently before making any financial decisions. 
