# RFQ Probe

A tool for probing and testing market maker quote coverage on Injective Protocol's Request-For-Quote (RFQ) system.

## Overview

This utility allows you to systematically test market maker responsiveness across multiple derivative markets on Injective Protocol. It sends RFQ requests and collects quotes to analyze which markets a specific maker is providing liquidity for.

## Features

- 📊 **Multi-market probing**: Test quote coverage across all configured derivative markets
- 🎯 **Maker-specific tracking**: Monitor a specific maker's quote responses
- ⚡ **Real-time price feeds**: Uses Injective's oracle price streams for accurate pricing
- 📈 **Detailed reporting**: Tabular output showing market coverage and maker responsiveness
- 🔧 **Configurable parameters**: Adjust direction, sizes, and timeouts

## Prerequisites

- Python 3.8 or higher
- Git
- An Injective wallet with a private key
- Access to Injective testnet or mainnet

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/fabricemlili/rfq_probe.git
cd rfq_probe
```

### 2. Clone the Injective RFQ Toolkit (required dependency)

```bash
git clone https://github.com/InjectiveLabs/injective-rfq-toolkit
```

### 3. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Environment Variables

Create a `.env` file in the project root:

```bash
# Specify which environment to use
RFQ_ENV=TESTNET  # or MAINNET or LOCAL

# Testnet credentials
TESTNET_PRIVATE_KEY=your_private_key_here
# or
TESTNET_ARB_PRIVATE_KEY=your_private_key_here

# Mainnet credentials (if using mainnet)
MAINNET_PRIVATE_KEY=your_private_key_here
```

### 2. Market Configuration

Edit `config.yaml` to define market groups and edge basis points:

```yaml
crypto_large_cap:
  tickers:
  - ETH/USDC PERP
  - BTC/USDC PERP
  - BNB/USDC PERP
  edge_bps: 40

crypto_mid_cap:
  tickers:
  - DOGE/USDC PERP
  - SOL/USDC PERP
  - LINK/USDC PERP
  edge_bps: 40
```

## Usage

### Basic Usage

Test a maker's quote coverage with default parameters:

```bash
python probe_maker_coverage.py --maker inj1ntzp6egl4z6e7gfmvsc63mh8ee5h4m2xqhn3lk
```

or

```bash
.venv/bin/python probe_maker_coverage.py --maker inj1ntzp6egl4z6e7gfmvsc63mh8ee5h4m2xqhn3lk
```

### Advanced Usage

Customize the probe parameters:

```bash
python probe_maker_coverage.py \
  --maker inj1ntzp6egl4z6e7gfmvsc63mh8ee5h4m2xqhn3lk \
  --direction long \
  --size 5000 \
  --timeout 10.0 \
  --delay 0.25 \
  --env TESTNET
```

### Command-Line Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--maker` | Yes | - | Injective address of the maker to monitor |
| `--direction` | No | `long` | Trade direction: `long` or `short` |
| `--size` | No | `5.0` | Notional size in USDC |
| `--timeout` | No | `10.0` | Quote collection timeout per market (seconds) |
| `--delay` | No | `0.25` | Delay between markets (seconds) |
| `--env` | No | From `.env` | Override RFQ_ENV (TESTNET/MAINNET/LOCAL) |

### Example with Higher Size (Notional)

```bash
.venv/bin/python probe_maker_coverage.py \
  --maker inj1ntzp6egl4z6e7gfmvsc63mh8ee5h4m2xqhn3lk \
  --size 4000 \
  --direction long
```

## Output

The tool produces a tabular report showing:

- **Ticker**: Market identifier (e.g., ETH/USDC PERP)
- **Market ID**: Abbreviated market ID
- **Mark Price**: Current oracle price
- **RFQ ID**: Request identifier
- **Total Quotes**: Number of quotes received
- **Maker Response**: Whether the target maker responded
- **Maker Price**: Price quoted by the maker (if responded)
- **All Makers**: List of all makers who responded
- **Error**: Any errors encountered

Example output:
```
Ticker           Market ID    Mark Price    RFQ ID  Total Quotes    Maker Response    Maker Price    All Makers
-------------  -----------  ------------  --------  --------------  ----------------  -------------  ------------
ETH/USDC PERP  0x1234...         3500.00    12345              3  ✓                      3501.20    [inj1..., ...]
BTC/USDC PERP  0x5678...        65000.00    12346              2  ✗                      -          [inj1..., ...]
```

## Project Structure

```
rfq_probe/
├── probe_maker_coverage.py    # Main probe script
├── config.yaml                 # Market configuration
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (create this)
├── README.md                   # This file
├── rfq_utils/                  # Utility modules
│   ├── __init__.py
│   ├── injective_price_stream.py
│   ├── balance_fetcher.py
│   └── price_csv_logger.py
└── injective-rfq-toolkit/      # Cloned toolkit (required)
```

## Troubleshooting

### Import Errors

If you encounter import errors from `rfq_test`:
- Ensure you've cloned the `injective-rfq-toolkit` repository
- Verify `requirements.txt` is installed correctly
- Check that the virtual environment is activated

### Connection Issues

If the script fails to connect:
- Verify your `RFQ_ENV` setting matches your private key
- Check your internet connection
- Ensure Injective network endpoints are accessible

### No Quotes Received

If no quotes are received:
- The market may have no active makers
- Try increasing the `--timeout` parameter
- Check that the market is active on the specified network

## Development

### Additional Utilities

The `rfq_utils/` directory contains helper modules:

- `injective_price_stream.py`: Real-time oracle price streaming
- `balance_fetcher.py`: Account balance queries
- `price_csv_logger.py`: Price data logging to CSV

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

See LICENSE file for details.

## Resources

- [Injective Protocol Documentation](https://docs.injective.network/)
- [Injective RFQ Toolkit](https://github.com/InjectiveLabs/injective-rfq-toolkit)
- [PyInjective SDK](https://github.com/InjectiveLabs/sdk-python)

## Support

For questions or issues:
- Open an issue on GitHub
- Check the Injective Protocol documentation
- Join the Injective community channels
