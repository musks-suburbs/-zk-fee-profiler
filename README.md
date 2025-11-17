# README.md
# zk-fee-profiler

## Overview
zk-fee-profiler is a small command-line tool that profiles recent gas behavior on an Ethereum-style network using web3.py.  

It is designed for engineers working on:
- ZK rollups
- Soundness-critical verification systems
- Projects like Aztec, Zama, or other proof-based architectures

The script samples recent blocks, computes percentiles for:
- Base fee (EIP-1559)
- Effective gas price
- Priority tip (approximate)

Then it suggests EIP-1559 gas settings:
- maxPriorityFeePerGas (Gwei)
- maxFeePerGas (Gwei)

These suggested values can be used as conservative parameters for L1 posting transactions, state updates, or proofs where predictable fees are important for system soundness.

## Files
1. app.py — main script (entry point).
2. README.md — documentation and usage instructions.

## Requirements
- Python 3.10 or newer
- Internet access to reach an Ethereum-compatible RPC
- A working RPC endpoint (Infura, Alchemy, your own node, etc.)

## Installation
1. Ensure Python is installed:
   - python3 --version

2. Install dependencies:
   - pip install web3

3. Set the RPC URL (recommended):
   - Export an environment variable RPC_URL with your endpoint.
   - If RPC_URL is not set, the script uses a placeholder Infura URL:
     https://mainnet.infura.io/v3/your_api_key

4. Optionally configure defaults via environment variables:
   - ZK_FEE_BLOCKS  number of recent blocks to scan (default 180)
   - ZK_FEE_STEP    sampling step (default 3, meaning every 3rd block)
   - ZK_FEE_TARGET_PCT  target percentile between 0.0 and 1.0 (default 0.8)

## Usage
Basic run with defaults:
   python app.py

Specify a custom RPC:
   python app.py --rpc https://your-node:8545

Increase or decrease the analysis window:
   python app.py --blocks 360 --step 5

Target a different percentile (for more conservative or more aggressive gas settings):
   python app.py --percentile 0.9

Anchor the analysis at a specific head block:
   python app.py --head 18000000

Machine-friendly JSON output:
   python app.py --json > fee_profile.json

## Output (human-readable mode)
When run without the --json flag, the script prints:
- Detected network name and chainId
- Head block, block window, sampling step, and runtime
- Target percentile used (e.g. 80 percent)
- Base fee statistics in Gwei:
  - p50 (median)
  - pTarget (user-defined percentile)
  - min and max across the sampled window
- Tip (priority fee) statistics in Gwei:
  - p50
  - pTarget
- Suggested EIP-1559 settings for ZK and soundness-critical transactions:
  - maxPriorityFeePerGas (recommended upper bound in Gwei)
  - maxFeePerGas (computed from base fee percentile plus recommended tip)

These values are intended as a helpful heuristic, not an absolute guarantee. They are particularly useful for:
- Batch proof publication
- Rollup state root submissions
- Aztec-compatible system calls
- Zama or FHE-backed systems where on-chain data publishing must stay within predictable fee bounds

## Output (JSON mode)
With the --json flag, the script prints a structured JSON document containing:
- mode                always "zk_fee_profile"
- generatedAtUtc      timestamp when the profile was generated
- data.chainId        numeric chain ID
- data.network        human-readable network name
- data.head           head block used for analysis
- data.sampledBlocks  number of blocks sampled
- data.blockWindow    window size requested by --blocks
- data.step           sampling step requested by --step
- data.targetPercentile           percentile used for fee suggestions
- data.timingSec      time taken in seconds
- data.baseFeeGwei    stats object with p50, pTarget, min, max
- data.medianEffectivePriceGwei   median effective gas price across blocks
- data.medianTipGwei  stats object with p50 and pTarget
- data.recommendedForZK           object with:
  - maxPriorityFeeGwei
  - maxFeePerGasGwei

This output can be used to feed dashboards, CI checks, or automatic gas policy tuning in ZK rollup infrastructure.

## Expected Results
A typical run produces:
- A summary of the recent base fee distribution
- Approximate priority fee behavior
- Suggested EIP-1559 parameters tuned to the selected percentile

For example, on a relatively stable network, you might see:
- Base fee p50 around 10–20 Gwei
- Tip p50 around 1–3 Gwei
- Recommended maxPriorityFeePerGas slightly above that, with maxFeePerGas aligning with your target percentile plus margin

## Notes
- This script is a heuristic tool and does not guarantee inclusion in any specific number of blocks.
- For critical production systems, you should combine this data with your own risk analysis and monitoring.
- The profiler is network-agnostic and works with any EVM-compatible chain that exposes EIP-1559 fields where applicable.
- For privacy-conscious deployments and soundness-sensitive protocols (Aztec-style systems, Zama-based flows, etc.), consider running the profiler against your own full node to avoid third-party RPC trust issues.
- If your RPC does not support baseFeePerGas or EIP-1559 fields, results may be partially degraded but still useful for legacy-style gas price behavior.
